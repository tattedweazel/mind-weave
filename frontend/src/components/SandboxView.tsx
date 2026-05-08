/**
 * Sandbox UI: server-owned state; Phaser adapter is view-only (see docs/SANDBOX.md).
 * Three-column shell matches Workflow Editor (palette + canvas + inspector).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    FolderPlus,
    Loader2,
    PanelLeft,
    PanelRight,
    Pause,
    Play,
    StepForward,
} from 'lucide-react';

import { ApiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { WorkflowDefinition, WorkflowDefinitionListItem, WorkflowProject, WorkflowRunResult } from '../api/types';
import type { SandboxEnvelopeJson } from '../domain/sandbox/types';
import { getHandleColor } from './workflow-editor/constants';
import { filterNamesByPrefix } from './workflow-editor/workflowListFilter';
import { WorkflowPaletteWorkflowRow } from './workflow-editor/WorkflowPaletteWorkflowRow';
import { DEFAULT_PALETTE_COLORS } from '../domain/paletteDefaults';
import {
    DEFAULT_TICK_RATE_MS,
    SANDBOX_GRID_DEFAULT_HEIGHT,
    SANDBOX_GRID_DEFAULT_WIDTH,
    SANDBOX_GRID_MAX_SIZE,
    SANDBOX_GRID_MIN_SIZE,
} from '../sandbox/sandboxVisualDefaults';
import {
    CENTER_PANEL_MIN_PX,
    clampPanelWidths,
    DEFAULT_LEFT_PANEL_WIDTH_PX,
    DEFAULT_RIGHT_PANEL_WIDTH_PX,
    PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS,
} from '../sandbox/SandboxLayoutConstants';
import { PhaserSandboxAdapter } from '../sandbox/runtime/phaserSandboxAdapter';
import type { SandboxGridCellJson } from '../domain/sandbox/types';
import type { SandboxCellInteraction } from '../sandbox/sandboxCellInteractions';
import { collectUserMessagesFromNodeResults } from '../sandbox/userMessageFromRun';
import { SANDBOX_DECISION_ERROR_HINT, shouldShowSandboxDecisionHint } from '../sandbox/sandboxLastErrorHint';
import { SandboxCellActionModal } from './SandboxCellActionModal';
import { useCompactViewport } from '../hooks/useCompactViewport';
import { InspectorSection } from './workflow-editor/InspectorSection';
import { WorkflowRunLogsNodeResultsList } from './workflow-editor/WorkflowRunLogsNodeResultsList';
import { cellHasInspectableContent, getCellOccupants } from '../sandbox/sandboxCellOccupants';

const SANDBOX_PANEL_WIDTHS_KEY = 'sandbox_panel_widths';

function readStoredSandboxPanelWidths(): { left: number; right: number } | null {
    try {
        const raw = localStorage.getItem(SANDBOX_PANEL_WIDTHS_KEY);
        if (!raw) return null;
        const p = JSON.parse(raw) as { left?: number; right?: number };
        if (typeof p.left !== 'number' || typeof p.right !== 'number') return null;
        return { left: p.left, right: p.right };
    } catch {
        return null;
    }
}

function writeStoredSandboxPanelWidths(left: number, right: number) {
    try {
        localStorage.setItem(SANDBOX_PANEL_WIDTHS_KEY, JSON.stringify({ left, right }));
    } catch {
        /* ignore */
    }
}

function nodeIdToLabel(graph: WorkflowDefinition['graph']): Map<string, string> {
    const m = new Map<string, string>();
    const nodes = (graph?.nodes ?? []) as { id?: string; label?: string; data?: { label?: string } }[];
    for (const n of nodes) {
        const id = n.id;
        if (!id) continue;
        const label = n.data?.label ?? n.label ?? id;
        m.set(id, String(label));
    }
    return m;
}

function formatIntent(intent: Record<string, unknown> | null): string {
    if (!intent) return '—';
    const action = intent.action;
    const status = intent.status;
    const reason = intent.reason;
    const parts = [`${String(action ?? '?')}`, `(${String(status ?? '?')})`];
    if (reason) parts.push(`— ${String(reason)}`);
    return parts.join(' ');
}

export const SandboxView: React.FC = () => {
    const { user } = useAuth();
    const containerRef = useRef<HTMLDivElement>(null);
    const adapterRef = useRef<PhaserSandboxAdapter | null>(null);
    const envelopeRef = useRef<SandboxEnvelopeJson | null>(null);
    const runTickRef = useRef<(interactions: unknown[]) => Promise<void>>(async () => {});

    const [envelope, setEnvelope] = useState<SandboxEnvelopeJson | null>(null);
    const [documentId, setDocumentId] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [paused, setPaused] = useState(true);
    const [tickRateMs, setTickRateMs] = useState(DEFAULT_TICK_RATE_MS);
    const [gridWidthInput, setGridWidthInput] = useState(SANDBOX_GRID_DEFAULT_WIDTH);
    const [gridHeightInput, setGridHeightInput] = useState(SANDBOX_GRID_DEFAULT_HEIGHT);
    const [gridResizeError, setGridResizeError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [workflowProjects, setWorkflowProjects] = useState<WorkflowProject[]>([]);
    const [catalogLoaded, setCatalogLoaded] = useState(false);
    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
    const [workflowNameFilter, setWorkflowNameFilter] = useState('');
    const [workflowListSort, setWorkflowListSort] = useState<'updated' | 'name'>('updated');
    const [isWorkflowsOpen, setIsWorkflowsOpen] = useState(true);
    const [newProjectNameDraft, setNewProjectNameDraft] = useState('');
    const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDefinition | null>(null);
    const [moveProjectPickerFor, setMoveProjectPickerFor] = useState<string | null>(null);

    const [inspectorTab, setInspectorTab] = useState<'explorer' | 'logs'>('explorer');
    const [lastWorkflowRun, setLastWorkflowRun] = useState<WorkflowRunResult | null>(null);
    const [tickTranscript, setTickTranscript] = useState<string[]>([]);
    const [runMessageToast, setRunMessageToast] = useState<string | null>(null);
    const runMessageToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const wfRowColor = getHandleColor(DEFAULT_PALETTE_COLORS, 'workflow');

    const compact = useCompactViewport();
    const [compactPaletteOpen, setCompactPaletteOpen] = useState(false);
    const [compactExplorerOpen, setCompactExplorerOpen] = useState(false);

    useEffect(() => {
        if (!compact) {
            setCompactPaletteOpen(false);
            setCompactExplorerOpen(false);
        }
    }, [compact]);

    const [panelWidths, setPanelWidths] = useState(() => {
        const w = typeof window !== 'undefined' ? window.innerWidth : 1200;
        const stored = typeof window !== 'undefined' ? readStoredSandboxPanelWidths() : null;
        if (stored) {
            return clampPanelWidths(w, stored.left, stored.right, true);
        }
        return clampPanelWidths(w, DEFAULT_LEFT_PANEL_WIDTH_PX, DEFAULT_RIGHT_PANEL_WIDTH_PX, true);
    });
    const panelWidthsRef = useRef(panelWidths);
    panelWidthsRef.current = panelWidths;
    const leftResizeDragRef = useRef<{ pointerId: number; startX: number; startW: number } | null>(null);
    const rightResizeDragRef = useRef<{ pointerId: number; startX: number; startW: number } | null>(null);

    const [cellActionCell, setCellActionCell] = useState<SandboxGridCellJson | null>(null);
    const [cellActionNonce, setCellActionNonce] = useState(0);
    const [inspectedCell, setInspectedCell] = useState<SandboxGridCellJson | null>(null);
    const restorePausedAfterCellActionRef = useRef(true);
    const busyRef = useRef(busy);
    busyRef.current = busy;
    const pausedRef = useRef(paused);
    pausedRef.current = paused;
    const cellActionModalOpenRef = useRef(false);
    cellActionModalOpenRef.current = cellActionCell !== null;

    useEffect(() => {
        envelopeRef.current = envelope;
    }, [envelope]);

    useEffect(() => {
        return () => {
            if (runMessageToastTimerRef.current) {
                clearTimeout(runMessageToastTimerRef.current);
            }
        };
    }, []);

    useEffect(() => {
            const onResize = () => {
            const w = window.innerWidth;
            setPanelWidths(prev => clampPanelWidths(w, prev.left, prev.right, true));
        };
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    const onLeftPanelResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
        e.preventDefault();
        leftResizeDragRef.current = {
            pointerId: e.pointerId,
            startX: e.clientX,
            startW: panelWidthsRef.current.left,
        };
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.userSelect = 'none';
    };

    const onLeftPanelResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
        const drag = leftResizeDragRef.current;
        if (!drag || e.pointerId !== drag.pointerId) return;
        const nextLeft = drag.startW + (e.clientX - drag.startX);
        setPanelWidths(p => clampPanelWidths(window.innerWidth, nextLeft, p.right, true));
    };

    const onLeftPanelResizePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
        const drag = leftResizeDragRef.current;
        if (!drag || e.pointerId !== drag.pointerId) return;
        leftResizeDragRef.current = null;
        document.body.style.userSelect = '';
        try {
            e.currentTarget.releasePointerCapture(e.pointerId);
        } catch {
            /* ignore */
        }
        setPanelWidths(p => {
            writeStoredSandboxPanelWidths(p.left, p.right);
            return p;
        });
    };

    const onRightPanelResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
        e.preventDefault();
        rightResizeDragRef.current = {
            pointerId: e.pointerId,
            startX: e.clientX,
            startW: panelWidthsRef.current.right,
        };
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.userSelect = 'none';
    };

    const onRightPanelResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
        const drag = rightResizeDragRef.current;
        if (!drag || e.pointerId !== drag.pointerId) return;
        const nextRight = drag.startW + (drag.startX - e.clientX);
        setPanelWidths(p => clampPanelWidths(window.innerWidth, p.left, nextRight, true));
    };

    const onRightPanelResizePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
        const drag = rightResizeDragRef.current;
        if (!drag || e.pointerId !== drag.pointerId) return;
        rightResizeDragRef.current = null;
        document.body.style.userSelect = '';
        try {
            e.currentTarget.releasePointerCapture(e.pointerId);
        } catch {
            /* ignore */
        }
        setPanelWidths(p => {
            writeStoredSandboxPanelWidths(p.left, p.right);
            return p;
        });
    };

    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const [wfs, projs, created] = await Promise.all([
                    ApiClient.getWorkflows(),
                    ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]),
                    ApiClient.createSandboxSession(),
                ]);
                if (cancelled) return;
                setWorkflows(wfs);
                setWorkflowProjects(projs);
                setCatalogLoaded(true);
                setDocumentId(created.document_id);
                setEnvelope(created.envelope);
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!envelope || workflows.length === 0) return;
        const wfId = envelope.workflow_id;
        if (!wfId) return;
        let cancelled = false;
        void (async () => {
            try {
                const full = await ApiClient.getWorkflow(wfId);
                if (!cancelled) setSelectedWorkflow(full);
            } catch { /* workflow may have been deleted */ }
        })();
        return () => { cancelled = true; };
    }, [envelope?.workflow_id, workflows]);

    useEffect(() => {
        if (!documentId) return;
        const el = containerRef.current;
        if (!el) return;
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(el);
        adapterRef.current = adapter;
        return () => {
            adapter.destroy();
            adapterRef.current = null;
        };
    }, [documentId]);

    useEffect(() => {
        if (envelope && adapterRef.current) {
            adapterRef.current.setState(envelope.sandbox);
        }
    }, [envelope]);

    useEffect(() => {
        if (!envelope) return;
        setGridWidthInput(envelope.sandbox.world.grid.width);
        setGridHeightInput(envelope.sandbox.world.grid.height);
        setGridResizeError(null);
    }, [envelope]);

    const effectiveWorkflowId = selectedWorkflow?.id ?? envelope?.workflow_id ?? null;

    const applyGridResize = useCallback(async () => {
        const doc = documentId;
        const env = envelopeRef.current;
        if (!doc || !env) return;
        setBusy(true);
        setGridResizeError(null);
        try {
            const res = await ApiClient.resizeSandboxGrid(doc, {
                width: gridWidthInput,
                height: gridHeightInput,
                state_version: env.state_version,
            });
            setEnvelope(res.envelope);
        } catch (e) {
            setGridResizeError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [documentId, gridWidthInput, gridHeightInput]);

    const runTick = useCallback(
        async (interactions: unknown[]) => {
            const doc = documentId;
            const env = envelopeRef.current;
            if (!doc || !env) return;
            setBusy(true);
            try {
                const res = await ApiClient.tickSandbox(doc, {
                    interactions,
                    state_version: env.state_version,
                    ...(effectiveWorkflowId ? { workflow_id: effectiveWorkflowId } : {}),
                });
                setEnvelope(res.envelope);
                setLastWorkflowRun(res.last_workflow_run);
                const toastText = collectUserMessagesFromNodeResults(res.last_workflow_run?.node_results);
                if (toastText) {
                    if (runMessageToastTimerRef.current) {
                        clearTimeout(runMessageToastTimerRef.current);
                        runMessageToastTimerRef.current = null;
                    }
                    setRunMessageToast(toastText);
                    runMessageToastTimerRef.current = setTimeout(() => {
                        setRunMessageToast(null);
                        runMessageToastTimerRef.current = null;
                    }, 4500);
                }
                setTickTranscript(prev => {
                    const tick = res.envelope.sandbox.tick;
                    const line = res.last_workflow_run
                        ? `Tick ${tick}: brain ${res.last_workflow_run.status} (${res.last_workflow_run.node_results.length} nodes)`
                        : `Tick ${tick}: intent step (no workflow run)`;
                    return [...prev, line].slice(-120);
                });
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            } finally {
                setBusy(false);
            }
        },
        [documentId, effectiveWorkflowId],
    );

    runTickRef.current = runTick;

    const dismissCellActionModal = useCallback(() => {
        setCellActionCell(null);
        setPaused(restorePausedAfterCellActionRef.current);
    }, []);

    const completeCellInspect = useCallback(() => {
        const cell = cellActionCell;
        if (!cell) return;
        setCellActionCell(null);
        setPaused(restorePausedAfterCellActionRef.current);
        setInspectedCell(cell);
        setInspectorTab('explorer');
    }, [cellActionCell]);

    const completeCellAction = useCallback(
        async (interaction: SandboxCellInteraction) => {
            setCellActionCell(null);
            try {
                await runTick([interaction]);
            } finally {
                setPaused(restorePausedAfterCellActionRef.current);
            }
        },
        [runTick],
    );

    useEffect(() => {
        if (!documentId) return;
        const adapter = adapterRef.current;
        if (!adapter) return;
        adapter.setOnCellClick(cell => {
            if (busyRef.current || cellActionModalOpenRef.current) return;
            restorePausedAfterCellActionRef.current = pausedRef.current;
            setPaused(true);
            setInspectedCell(null);
            setCellActionNonce(n => n + 1);
            setCellActionCell(cell);
        });
    }, [documentId]);

    useEffect(() => {
        if (paused || !documentId) return;
        const id = window.setInterval(() => {
            void runTick([]);
        }, tickRateMs);
        return () => clearInterval(id);
    }, [paused, tickRateMs, documentId, runTick]);

    useEffect(() => {
        setMoveProjectPickerFor(null);
    }, [selectedProjectId]);

    const sharedProjectId = React.useMemo(
        () => workflowProjects.find(p => p.name === 'Shared')?.id ?? null,
        [workflowProjects],
    );

    const displayedProjects = React.useMemo(() => {
        const list = [...workflowProjects];
        list.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
        return list;
    }, [workflowProjects]);

    const workflowsInSelectedProject = React.useMemo(() => {
        if (!selectedProjectId) return [];
        if (sharedProjectId && selectedProjectId === sharedProjectId) {
            return workflows.filter(w => w.project_id === selectedProjectId || w.project_id == null);
        }
        return workflows.filter(w => w.project_id === selectedProjectId);
    }, [workflows, selectedProjectId, sharedProjectId]);

    const workflowsInProjectDrillIn = React.useMemo(
        () => workflowsInSelectedProject.filter(w => !w.expose_as_custom_skill),
        [workflowsInSelectedProject],
    );

    const filteredWorkflowsInProject = React.useMemo(() => {
        let list = filterNamesByPrefix(workflowsInProjectDrillIn, workflowNameFilter);
        if (workflowListSort === 'name') {
            list = [...list].sort((a, b) => {
                const byName = a.name.localeCompare(b.name);
                if (byName !== 0) return byName;
                return a.id.localeCompare(b.id);
            });
        } else {
            list = [...list].sort((a, b) => {
                const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                if (tb !== ta) return tb - ta;
                return a.id.localeCompare(b.id);
            });
        }
        return list;
    }, [workflowsInProjectDrillIn, workflowNameFilter, workflowListSort]);

    const selectedProject = React.useMemo(
        () =>
            selectedProjectId ? workflowProjects.find(p => p.id === selectedProjectId) ?? null : null,
        [workflowProjects, selectedProjectId],
    );

    const workflowCountForProject = (p: WorkflowProject) => {
        const inProject =
            sharedProjectId && p.id === sharedProjectId
                ? workflows.filter(w => w.project_id === p.id || w.project_id == null)
                : workflows.filter(w => w.project_id === p.id);
        return inProject.filter(w => !w.expose_as_custom_skill).length;
    };

    const handleCreateProject = async () => {
        const name = newProjectNameDraft.trim();
        if (!name) return;
        try {
            await ApiClient.createWorkflowProject({ name });
            setNewProjectNameDraft('');
            const projs = await ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]);
            setWorkflowProjects(projs);
        } catch {
            /* ignore */
        }
    };

    const moveWorkflowToProject = async (wfId: string, projectId: string): Promise<boolean> => {
        try {
            await ApiClient.updateWorkflow(wfId, { project_id: projectId });
            const wfs = await ApiClient.getWorkflows();
            setWorkflows(wfs);
            if (selectedWorkflow?.id === wfId) {
                setSelectedWorkflow(prev => prev ? { ...prev, project_id: projectId } : prev);
            }
            return true;
        } catch {
            return false;
        }
    };

    const openSandboxWorkflow = async (wf: WorkflowDefinitionListItem) => {
        setMoveProjectPickerFor(null);
        try {
            const full = await ApiClient.getWorkflow(wf.id);
            setSelectedWorkflow(full);
        } catch { /* ignore */ }
    };

    const nodeLabels = selectedWorkflow ? nodeIdToLabel(selectedWorkflow.graph) : new Map<string, string>();

    const cellActionOccupants = React.useMemo(
        () => (envelope && cellActionCell ? getCellOccupants(envelope, cellActionCell) : null),
        [envelope, cellActionCell],
    );
    const modalCanInspect = cellActionOccupants ? cellHasInspectableContent(cellActionOccupants) : false;

    const inspectedOccupants = React.useMemo(
        () => (envelope && inspectedCell ? getCellOccupants(envelope, inspectedCell) : null),
        [envelope, inspectedCell],
    );

    if (loadError) {
        return (
            <div className="h-full flex items-center justify-center text-mw-error text-sm px-6 text-center">
                {loadError}
            </div>
        );
    }

    if (!envelope || !documentId || !catalogLoaded) {
        return (
            <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                <Loader2 className="animate-spin" size={24} />
                <span>Loading sandbox…</span>
            </div>
        );
    }

    return (
        <div className="flex h-full overflow-hidden relative">
            {compact && compactPaletteOpen && (
                <button
                    type="button"
                    className="absolute inset-0 z-40 bg-black/40 border-0 p-0 cursor-default"
                    aria-label="Close palette"
                    onClick={() => setCompactPaletteOpen(false)}
                />
            )}
            {compact && compactExplorerOpen && (
                <button
                    type="button"
                    className="absolute inset-0 z-40 bg-black/40 border-0 p-0 cursor-default"
                    aria-label="Close Explorer panel"
                    onClick={() => setCompactExplorerOpen(false)}
                />
            )}
            {/* Left — workflow picker (editor parity: z-10, resize strip on canvas edge) */}
            <div
                className={
                    compact
                        ? `absolute left-0 top-0 bottom-0 z-50 flex min-w-0 transition-transform duration-200 ease-out ${
                              compactPaletteOpen ? 'translate-x-0 pointer-events-auto' : '-translate-x-full pointer-events-none'
                          }`
                        : 'relative z-10 shrink-0 flex min-w-0'
                }
                style={compact ? { width: 'min(85vw, 22rem)' } : { width: panelWidths.left }}
            >
                <div className="flex-1 min-w-0 border-r border-mw-border bg-mw-sidebar flex flex-col min-h-0 overflow-y-auto">
                    <div className="p-3 border-b border-mw-border shrink-0">
                        <div className="flex items-center justify-between mb-2">
                            <button
                                type="button"
                                onClick={() => setIsWorkflowsOpen(!isWorkflowsOpen)}
                                className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                            >
                                {isWorkflowsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Workflows
                            </button>
                        </div>
                        {isWorkflowsOpen && (
                            <>
                                {!selectedProjectId ? (
                                    <>
                                        <div className="flex gap-1 mb-2">
                                            <input
                                                type="text"
                                                value={newProjectNameDraft}
                                                onChange={e => setNewProjectNameDraft(e.target.value)}
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') void handleCreateProject();
                                                }}
                                                placeholder="New project…"
                                                aria-label="New project name"
                                                className="min-w-0 flex-1 px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => void handleCreateProject()}
                                                className="shrink-0 p-1 text-mw-primary hover:bg-mw-primary-muted rounded transition-colors"
                                                title="Create project"
                                            >
                                                <FolderPlus size={14} />
                                            </button>
                                        </div>
                                        <div
                                            className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}
                                        >
                                            {displayedProjects.map(p => (
                                                <button
                                                    key={p.id}
                                                    type="button"
                                                    onClick={() => {
                                                        setSelectedProjectId(p.id);
                                                        setWorkflowNameFilter('');
                                                    }}
                                                    className="w-full flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded-lg text-left text-mw-text-primary hover:bg-mw-card transition-colors"
                                                >
                                                    <span className="truncate font-medium">{p.name}</span>
                                                    <span className="shrink-0 text-xs text-mw-text-secondary tabular-nums">
                                                        {workflowCountForProject(p)}
                                                    </span>
                                                </button>
                                            ))}
                                            {displayedProjects.length === 0 && (
                                                <div className="text-xs text-mw-text-secondary text-center py-2">
                                                    No projects yet
                                                </div>
                                            )}
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div className="flex items-center gap-1 mb-2 min-w-0">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setSelectedProjectId(null);
                                                    setWorkflowNameFilter('');
                                                }}
                                                className="shrink-0 p-1 rounded text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card"
                                                title="All projects"
                                            >
                                                <ChevronLeft size={16} />
                                            </button>
                                            <span
                                                className="text-xs font-semibold text-mw-text-primary truncate min-w-0 flex-1"
                                                title={selectedProject?.name ?? ''}
                                            >
                                                {selectedProject?.name ?? 'Project'}
                                            </span>
                                        </div>
                                        <div
                                            role="group"
                                            aria-label="Sort workflows"
                                            className="flex rounded-lg border border-mw-border bg-mw-card p-0.5 mb-2 gap-0.5"
                                        >
                                            {(['updated', 'name'] as const).map(key => (
                                                <button
                                                    key={key}
                                                    type="button"
                                                    onClick={() => setWorkflowListSort(key)}
                                                    className={`flex-1 min-w-0 px-1.5 py-1 text-[10px] font-medium rounded-md transition-colors ${
                                                        workflowListSort === key
                                                            ? 'bg-mw-primary-muted text-mw-primary'
                                                            : 'text-mw-text-secondary hover:bg-mw-card hover:text-mw-text-primary'
                                                    }`}
                                                >
                                                    {key === 'name' ? 'Name A–Z' : 'Last updated'}
                                                </button>
                                            ))}
                                        </div>
                                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 mb-2">
                                            <input
                                                type="search"
                                                value={workflowNameFilter}
                                                onChange={e => setWorkflowNameFilter(e.target.value)}
                                                placeholder="Filter…"
                                                aria-label="Filter workflows"
                                                className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                                            />
                                        </div>
                                        <div
                                            className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}
                                        >
                                            {filteredWorkflowsInProject.map(wf => (
                                                <WorkflowPaletteWorkflowRow
                                                    key={wf.id}
                                                    workflow={wf}
                                                    wfColor={wfRowColor}
                                                    activeWorkflowId={selectedWorkflow?.id ?? null}
                                                    draggable={false}
                                                    onOpen={openSandboxWorkflow}
                                                    moveProjectPickerFor={moveProjectPickerFor}
                                                    onToggleMovePicker={id =>
                                                        setMoveProjectPickerFor(prev => (prev === id ? null : id))
                                                    }
                                                    workflowProjects={workflowProjects}
                                                    sharedProjectId={sharedProjectId}
                                                    onMoveToProject={moveWorkflowToProject}
                                                    onMoveComplete={() => setMoveProjectPickerFor(null)}
                                                />
                                            ))}
                                            {filteredWorkflowsInProject.length === 0 && (
                                                <div className="text-xs text-mw-text-secondary text-center py-2">
                                                    No workflows in this project
                                                </div>
                                            )}
                                        </div>
                                    </>
                                )}
                            </>
                        )}
                    </div>
                    <div className="p-3 text-[10px] text-mw-text-secondary leading-relaxed space-y-1.5">
                        <p>
                            Select a workflow, then use Play / Step in the toolbar. You can switch workflows while the
                            session runs—the next tick that runs the brain uses the new graph, and the choice is saved on
                            this session. If the pet is finishing a move or other intent, the new brain applies on the next{' '}
                            <span className="whitespace-nowrap">decision</span> tick.
                        </p>
                        <p>Create or edit graphs in the Workflow Editor.</p>
                    </div>
                </div>
                {!compact && (
                    <div
                        role="separator"
                        aria-orientation="vertical"
                        aria-label="Resize palette column"
                        className="w-2 shrink-0 cursor-col-resize hover:bg-mw-border/60 bg-transparent touch-none"
                        onPointerDown={onLeftPanelResizePointerDown}
                        onPointerMove={onLeftPanelResizePointerMove}
                        onPointerUp={onLeftPanelResizePointerUp}
                        onPointerCancel={onLeftPanelResizePointerUp}
                    />
                )}
            </div>

            {/* Center — toolbar + Phaser board */}
            <div
                className="relative z-0 flex-1 flex flex-col min-h-0 overflow-hidden"
                style={{ minWidth: compact ? 0 : CENTER_PANEL_MIN_PX }}
            >
                <div className="h-12 border-b border-mw-border bg-mw-card flex items-center px-2 sm:px-4 gap-2 sm:gap-3 shrink-0 min-w-0">
                    {compact && (
                        <>
                            <button
                                type="button"
                                className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                aria-label="Open workflow palette"
                                title="Palette"
                                onClick={() => {
                                    setCompactExplorerOpen(false);
                                    setCompactPaletteOpen(true);
                                }}
                            >
                                <PanelLeft size={18} />
                            </button>
                            <button
                                type="button"
                                className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                aria-label="Open Explorer"
                                title="Explorer"
                                onClick={() => {
                                    setCompactPaletteOpen(false);
                                    setCompactExplorerOpen(true);
                                }}
                            >
                                <PanelRight size={18} />
                            </button>
                        </>
                    )}
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() => setPaused(p => !p)}
                        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-mw-primary text-white text-xs font-medium disabled:opacity-50"
                    >
                        {paused ? <Play size={14} /> : <Pause size={14} />}
                        {paused ? 'Play' : 'Pause'}
                    </button>
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() => void runTick([])}
                        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs"
                    >
                        <StepForward size={14} />
                        Step
                    </button>
                    <span className="text-xs text-mw-text-secondary truncate min-w-0 max-w-[12rem] sm:max-w-xs">
                        {selectedWorkflow?.name ?? 'Default session workflow'}
                    </span>
                </div>
                {envelope.last_error && (
                    <div className="px-4 py-2 text-xs text-mw-error bg-mw-error-muted border-b border-mw-border shrink-0 space-y-1">
                        <div>{envelope.last_error}</div>
                        {shouldShowSandboxDecisionHint(envelope.last_error) ? (
                            <div className="text-mw-text-secondary font-normal">{SANDBOX_DECISION_ERROR_HINT}</div>
                        ) : null}
                    </div>
                )}
                <div className="flex-1 min-h-0 overflow-hidden flex items-center justify-center bg-mw-page p-2 relative">
                    <div
                        ref={containerRef}
                        className="rounded-lg border border-mw-border overflow-hidden shrink-0 max-w-full max-h-full touch-none"
                    />
                    {runMessageToast ? (
                        <div
                            className="pointer-events-none absolute bottom-4 left-1/2 z-20 -translate-x-1/2 max-w-[min(92vw,32rem)] px-4 py-3 rounded-lg bg-mw-card border border-mw-border shadow-lg text-sm text-mw-text-primary whitespace-pre-wrap"
                            role="status"
                            aria-live="polite"
                        >
                            {runMessageToast}
                        </div>
                    ) : null}
                </div>
            </div>

            {/* Right — Explorer / Run logs */}
            <div
                className={
                    compact
                        ? `absolute right-0 top-0 bottom-0 z-50 flex min-w-0 flex-row transition-transform duration-200 ease-out ${
                              compactExplorerOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
                          }`
                        : 'shrink-0 flex min-w-0'
                }
                style={compact ? { width: 'min(100vw, 24rem)' } : { width: panelWidths.right }}
            >
                {!compact && (
                    <div
                        role="separator"
                        aria-orientation="vertical"
                        aria-label="Resize inspector column"
                        className="w-2 shrink-0 cursor-col-resize hover:bg-mw-border/60 bg-transparent touch-none"
                        onPointerDown={onRightPanelResizePointerDown}
                        onPointerMove={onRightPanelResizePointerMove}
                        onPointerUp={onRightPanelResizePointerUp}
                        onPointerCancel={onRightPanelResizePointerUp}
                    />
                )}
                <div className="flex-1 min-w-0 border-l border-mw-border bg-mw-card flex flex-col min-h-0 overflow-hidden">
                    <div className="flex bg-mw-page border-b border-mw-border shrink-0">
                        <button
                            type="button"
                            onClick={() => setInspectorTab('explorer')}
                            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wide transition-colors ${
                                inspectorTab === 'explorer'
                                    ? 'text-mw-primary border-b-2 border-mw-primary bg-mw-card'
                                    : 'text-mw-text-secondary hover:text-mw-text-primary border-b-2 border-transparent'
                            }`}
                        >
                            Explorer
                        </button>
                        <button
                            type="button"
                            onClick={() => setInspectorTab('logs')}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold uppercase tracking-wide transition-colors ${
                                inspectorTab === 'logs'
                                    ? 'text-mw-primary border-b-2 border-mw-primary bg-mw-card'
                                    : 'text-mw-text-secondary hover:text-mw-text-primary border-b-2 border-transparent'
                            }`}
                        >
                            Run Logs
                            {lastWorkflowRun ? (
                                <span
                                    className={`w-4 h-4 rounded-full shrink-0 ${
                                        lastWorkflowRun.status === 'ok'
                                            ? 'bg-green-500'
                                            : lastWorkflowRun.status === 'partial'
                                              ? 'bg-amber-500'
                                              : 'bg-red-500'
                                    }`}
                                />
                            ) : null}
                        </button>
                    </div>
                    <div className="flex-1 min-h-0 overflow-y-auto text-sm">
                        {inspectorTab === 'explorer' ? (
                            <div className="p-4 space-y-4">
                                {inspectedCell && inspectedOccupants ? (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between gap-2">
                                            <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">
                                                Cell ({inspectedCell.x}, {inspectedCell.y})
                                            </h3>
                                            <button
                                                type="button"
                                                onClick={() => setInspectedCell(null)}
                                                className="shrink-0 text-[10px] font-medium text-mw-primary hover:underline"
                                            >
                                                Clear
                                            </button>
                                        </div>
                                        {!cellHasInspectableContent(inspectedOccupants) ? (
                                            <p className="text-xs text-mw-text-secondary">
                                                Nothing is on this cell anymore.{' '}
                                                <button
                                                    type="button"
                                                    onClick={() => setInspectedCell(null)}
                                                    className="text-mw-primary hover:underline font-medium"
                                                >
                                                    Clear
                                                </button>
                                            </p>
                                        ) : (
                                            <div className="space-y-3">
                                                {inspectedOccupants.petHere ? (
                                                    <InspectorSection title="Pet">
                                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                                            <div className="text-mw-text-secondary">Position</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right font-mono">
                                                                ({envelope.sandbox.pet.position.x},{' '}
                                                                {envelope.sandbox.pet.position.y})
                                                            </div>
                                                            <div className="text-mw-text-secondary">Hunger</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right">
                                                                {envelope.sandbox.pet.hunger}
                                                            </div>
                                                            <div className="text-mw-text-secondary">Energy</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right">
                                                                {envelope.sandbox.pet.energy}
                                                            </div>
                                                            <div className="text-mw-text-secondary">Mood</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right">
                                                                {envelope.sandbox.pet.mood}
                                                            </div>
                                                            <div className="text-mw-text-secondary col-span-2">
                                                                Intent
                                                            </div>
                                                            <div className="text-mw-text-primary text-[11px] break-words col-span-2">
                                                                {formatIntent(envelope.sandbox.pet.intent)}
                                                            </div>
                                                        </div>
                                                    </InspectorSection>
                                                ) : null}
                                                {inspectedOccupants.items.map(it => (
                                                    <InspectorSection key={it.id} title={`Item (${it.type})`}>
                                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                                            <div className="text-mw-text-secondary">Id</div>
                                                            <div className="text-mw-text-primary text-right font-mono text-[10px] break-all">
                                                                {it.id}
                                                            </div>
                                                            <div className="text-mw-text-secondary">Position</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right font-mono">
                                                                ({it.position.x}, {it.position.y})
                                                            </div>
                                                            {typeof it.energy === 'number' ? (
                                                                <>
                                                                    <div className="text-mw-text-secondary">Energy</div>
                                                                    <div className="text-mw-text-primary tabular-nums text-right">
                                                                        {it.energy}
                                                                    </div>
                                                                </>
                                                            ) : null}
                                                        </div>
                                                    </InspectorSection>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ) : null}
                                <div>
                                    <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                        Simulation
                                    </h3>
                                    <label className="flex items-center gap-2 text-xs text-mw-text-secondary mb-2">
                                        Tick ms
                                        <input
                                            type="number"
                                            min={200}
                                            max={60000}
                                            step={100}
                                            value={tickRateMs}
                                            onChange={e =>
                                                setTickRateMs(Number(e.target.value) || DEFAULT_TICK_RATE_MS)
                                            }
                                            className="w-24 px-2 py-1 rounded border border-mw-border bg-mw-page text-mw-text-primary"
                                        />
                                    </label>
                                    <div className="flex flex-wrap items-end gap-2 mb-3">
                                        <label className="flex flex-col gap-0.5 text-xs text-mw-text-secondary">
                                            Width
                                            <input
                                                type="number"
                                                min={SANDBOX_GRID_MIN_SIZE}
                                                max={SANDBOX_GRID_MAX_SIZE}
                                                value={gridWidthInput}
                                                disabled={!paused || busy}
                                                onChange={e =>
                                                    setGridWidthInput(
                                                        Math.min(
                                                            SANDBOX_GRID_MAX_SIZE,
                                                            Math.max(
                                                                SANDBOX_GRID_MIN_SIZE,
                                                                Number(e.target.value) || SANDBOX_GRID_MIN_SIZE,
                                                            ),
                                                        ),
                                                    )
                                                }
                                                className="w-16 px-2 py-1 rounded border border-mw-border bg-mw-page text-mw-text-primary disabled:opacity-50"
                                            />
                                        </label>
                                        <label className="flex flex-col gap-0.5 text-xs text-mw-text-secondary">
                                            Height
                                            <input
                                                type="number"
                                                min={SANDBOX_GRID_MIN_SIZE}
                                                max={SANDBOX_GRID_MAX_SIZE}
                                                value={gridHeightInput}
                                                disabled={!paused || busy}
                                                onChange={e =>
                                                    setGridHeightInput(
                                                        Math.min(
                                                            SANDBOX_GRID_MAX_SIZE,
                                                            Math.max(
                                                                SANDBOX_GRID_MIN_SIZE,
                                                                Number(e.target.value) || SANDBOX_GRID_MIN_SIZE,
                                                            ),
                                                        ),
                                                    )
                                                }
                                                className="w-16 px-2 py-1 rounded border border-mw-border bg-mw-page text-mw-text-primary disabled:opacity-50"
                                            />
                                        </label>
                                        <button
                                            type="button"
                                            disabled={!paused || busy}
                                            onClick={() => void applyGridResize()}
                                            className="px-2 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs text-mw-text-primary disabled:opacity-50"
                                        >
                                            Apply grid
                                        </button>
                                    </div>
                                    {gridResizeError ? (
                                        <p className="text-xs text-mw-error mb-2" role="alert">
                                            {gridResizeError}
                                        </p>
                                    ) : null}
                                    {!paused ? (
                                        <p className="text-[10px] text-mw-text-secondary mb-2">
                                            Pause playback to resize the grid.
                                        </p>
                                    ) : null}
                                    <div className="grid grid-cols-2 gap-2 text-xs">
                                        <div className="text-mw-text-secondary">Tick</div>
                                        <div className="text-mw-text-primary tabular-nums text-right">
                                            {envelope.sandbox.tick}
                                        </div>
                                        <div className="text-mw-text-secondary">Hunger</div>
                                        <div className="text-mw-text-primary tabular-nums text-right">
                                            {envelope.sandbox.pet.hunger}
                                        </div>
                                        <div className="text-mw-text-secondary">Energy</div>
                                        <div className="text-mw-text-primary tabular-nums text-right">
                                            {envelope.sandbox.pet.energy}
                                        </div>
                                        <div className="text-mw-text-secondary">Mood</div>
                                        <div className="text-mw-text-primary tabular-nums text-right">
                                            {envelope.sandbox.pet.mood}
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                        Current action
                                    </h3>
                                    <p className="text-xs text-mw-text-primary break-words">
                                        {formatIntent(envelope.sandbox.pet.intent)}
                                    </p>
                                    {envelope.sandbox.recent_actions?.length ? (
                                        <ul className="mt-2 text-[10px] text-mw-text-secondary space-y-1">
                                            {[...envelope.sandbox.recent_actions].reverse().slice(0, 5).map((a, i) => (
                                                <li key={`${a.tick}-${a.action}-${i}`}>
                                                    t{a.tick}: {a.action}
                                                    {a.reason ? ` — ${a.reason}` : ''}
                                                </li>
                                            ))}
                                        </ul>
                                    ) : null}
                                </div>
                                <div>
                                    <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                        Workflow
                                    </h3>
                                    <p className="text-xs text-mw-text-primary">{selectedWorkflow?.name ?? '—'}</p>
                                    <p className="text-[10px] text-mw-text-secondary mt-1 break-all">
                                        Persisted workflow id:{' '}
                                        <span className="font-mono">{envelope.workflow_id}</span>
                                    </p>
                                </div>
                            </div>
                        ) : (
                            <div className="p-4 space-y-4">
                                {tickTranscript.length > 0 && (
                                    <div>
                                        <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                            Tick transcript
                                        </h3>
                                        <ul className="text-[10px] font-mono text-mw-text-secondary space-y-0.5 max-h-32 overflow-y-auto border border-mw-border rounded p-2 bg-mw-page">
                                            {tickTranscript.map((line, i) => (
                                                <li key={i}>{line}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                {!lastWorkflowRun && (
                                    <div className="text-center text-xs text-mw-text-secondary mt-4">
                                        Run a tick when the brain executes (Play/Step) to see node logs. Intent-only
                                        steps do not run the workflow graph.
                                    </div>
                                )}
                                {lastWorkflowRun && (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between bg-mw-card-alt px-3 py-2 rounded-lg border border-mw-border">
                                            <span className="text-xs font-semibold text-mw-text-primary">
                                                Last brain run
                                            </span>
                                            <span
                                                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                                    lastWorkflowRun.status === 'ok'
                                                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                                                        : lastWorkflowRun.status === 'partial'
                                                          ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                                                          : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                                                }`}
                                            >
                                                {lastWorkflowRun.status.toUpperCase()}
                                            </span>
                                        </div>
                                        <WorkflowRunLogsNodeResultsList
                                            node_results={lastWorkflowRun.node_results}
                                            getNodeLabel={id => nodeLabels.get(id) ?? id}
                                            userSettings={user?.settings as Record<string, unknown> | undefined}
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
            {cellActionCell ? (
                <SandboxCellActionModal
                    key={`${cellActionCell.x}-${cellActionCell.y}-${cellActionNonce}`}
                    cell={cellActionCell}
                    canInspect={modalCanInspect}
                    onDismiss={dismissCellActionModal}
                    onComplete={interaction => {
                        void completeCellAction(interaction);
                    }}
                    onInspect={completeCellInspect}
                />
            ) : null}
        </div>
    );
};
