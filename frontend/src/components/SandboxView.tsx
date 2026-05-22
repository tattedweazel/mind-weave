/**
 * Sandbox UI: server-owned state; Phaser adapter is view-only (see docs/SANDBOX.md).
 * Three-column shell matches Workflow Editor (palette + canvas + inspector).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    Loader2,
    PanelLeft,
    PanelRight,
    Pause,
    Play,
    Plus,
    Save,
    StepForward,
} from 'lucide-react';

import { ApiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { WorkflowDefinition, WorkflowDefinitionListItem, WorkflowProject, WorkflowRunResult } from '../api/types';
import type { BoardDefinitionJson, SandboxBoardJson, SandboxEnvelopeJson } from '../domain/sandbox/types';
import { SANDBOX_FACING_VALUES, sandboxStateFromBoardDefinition } from '../domain/sandbox/types';
import {
    projectsWithCreatureBrains,
    sharedProjectIdFromProjects,
} from '../domain/workflowProjectMembership';
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
import {
    mergeSandboxWorkflowRuns,
    sandboxTickTranscriptSummary,
} from '../sandbox/sandboxWorkflowRunMerge';
import { SandboxCellActionModal } from './SandboxCellActionModal';
import { SandboxItemInspectorSection } from './sandbox/SandboxItemInspectorSection';
import { useCompactViewport } from '../hooks/useCompactViewport';
import { InspectorSection } from './workflow-editor/InspectorSection';
import { WorkflowRunLogsNodeResultsList } from './workflow-editor/WorkflowRunLogsNodeResultsList';
import { cellHasInspectableContent, getCellOccupants, getCellOccupantsFromSandboxState } from '../sandbox/sandboxCellOccupants';
import {
    applyBoardBuilderInteraction,
    createEmptyBoardDefinition,
    resizeBoardDefinition,
    updateBoardItemMetadata,
    updateBoardCreatureFacing,
} from '../sandbox/boardBuilderLocalEdits';

const SANDBOX_PANEL_WIDTHS_KEY = 'sandbox_panel_widths';

type MainTab = 'simulation' | 'builder';

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

function formatRecentAction(
    creatureId: string,
    recentActions: SandboxEnvelopeJson['sandbox']['recent_actions'],
): string {
    const latest = [...recentActions].reverse().find(a => a.creature_id === creatureId);
    if (!latest) return '—';
    return latest.reason ? `${latest.action} — ${latest.reason}` : latest.action;
}

function collectVisibleErrors(
    lastErrors: Record<string, string | null> | undefined,
    selectedCreatureId: string | null,
): { creatureId: string; message: string }[] {
    if (!lastErrors) return [];
    const entries = Object.entries(lastErrors).filter((entry): entry is [string, string] => Boolean(entry[1]));
    if (selectedCreatureId) {
        const selected = entries.filter(([id]) => id === selectedCreatureId);
        if (selected.length > 0) return selected.map(([creatureId, message]) => ({ creatureId, message }));
    }
    return entries.map(([creatureId, message]) => ({ creatureId, message }));
}

export const SandboxView: React.FC = () => {
    const { user } = useAuth();
    const containerRef = useRef<HTMLDivElement>(null);
    const adapterRef = useRef<PhaserSandboxAdapter | null>(null);
    const envelopeRef = useRef<SandboxEnvelopeJson | null>(null);

    const [mainTab, setMainTab] = useState<MainTab>('simulation');
    const [envelope, setEnvelope] = useState<SandboxEnvelopeJson | null>(null);
    const [documentId, setDocumentId] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [catalogLoaded, setCatalogLoaded] = useState(false);
    const [paused, setPaused] = useState(true);
    const [tickRateMs, setTickRateMs] = useState(DEFAULT_TICK_RATE_MS);
    const [gridWidthInput, setGridWidthInput] = useState(SANDBOX_GRID_DEFAULT_WIDTH);
    const [gridHeightInput, setGridHeightInput] = useState(SANDBOX_GRID_DEFAULT_HEIGHT);
    const [gridResizeError, setGridResizeError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [workflowProjects, setWorkflowProjects] = useState<WorkflowProject[]>([]);
    const [boards, setBoards] = useState<SandboxBoardJson[]>([]);
    const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
    const [builderBoardId, setBuilderBoardId] = useState<string | null>(null);
    const [builderBoardName, setBuilderBoardName] = useState('Untitled Board');
    const [localBoardDef, setLocalBoardDef] = useState<BoardDefinitionJson>(() =>
        createEmptyBoardDefinition(SANDBOX_GRID_DEFAULT_WIDTH, SANDBOX_GRID_DEFAULT_HEIGHT),
    );
    const [builderDirty, setBuilderDirty] = useState(false);

    const [inspectorTab, setInspectorTab] = useState<'explorer' | 'logs'>('explorer');
    const [lastWorkflowRuns, setLastWorkflowRuns] = useState<Record<string, WorkflowRunResult | null>>({});
    const [selectedCreatureId, setSelectedCreatureId] = useState<string | null>(null);
    const [creatureWorkflow, setCreatureWorkflow] = useState<WorkflowDefinition | null>(null);
    const [tickTranscript, setTickTranscript] = useState<string[]>([]);
    const [runMessageToast, setRunMessageToast] = useState<string | null>(null);
    const runMessageToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    const mainTabRef = useRef(mainTab);
    mainTabRef.current = mainTab;

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

    const refreshBoards = useCallback(async () => {
        const res = await ApiClient.listSandboxBoards();
        setBoards(res.boards);
        return res.boards;
    }, []);

    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const [wfs, projs, boardList, created] = await Promise.all([
                    ApiClient.getWorkflows(),
                    ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]),
                    ApiClient.listSandboxBoards(),
                    ApiClient.createSandboxSession(),
                ]);
                if (cancelled) return;
                setWorkflows(wfs);
                setWorkflowProjects(projs);
                setBoards(boardList.boards);
                setCatalogLoaded(true);
                setDocumentId(created.document_id);
                setEnvelope(created.envelope);
                setSelectedBoardId(created.envelope.board_id ?? null);
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!catalogLoaded) return;
        const el = containerRef.current;
        if (!el) return;
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(el);
        adapterRef.current = adapter;
        return () => {
            adapter.destroy();
            adapterRef.current = null;
        };
    }, [catalogLoaded]);

    useEffect(() => {
        const adapter = adapterRef.current;
        if (!adapter) return;
        if (mainTab === 'simulation' && envelope) {
            adapter.setState(envelope.sandbox, { selectedCreatureId });
        } else if (mainTab === 'builder') {
            adapter.setState(sandboxStateFromBoardDefinition(localBoardDef), { selectedCreatureId });
        }
    }, [mainTab, envelope, localBoardDef, selectedCreatureId]);

    useEffect(() => {
        if (mainTab === 'simulation' && envelope) {
            setGridWidthInput(envelope.sandbox.world.grid.width);
            setGridHeightInput(envelope.sandbox.world.grid.height);
            setGridResizeError(null);
        } else if (mainTab === 'builder') {
            setGridWidthInput(localBoardDef.grid.width);
            setGridHeightInput(localBoardDef.grid.height);
            setGridResizeError(null);
        }
    }, [mainTab, envelope, localBoardDef.grid.width, localBoardDef.grid.height]);

    useEffect(() => {
        if (!selectedCreatureId || !envelope) {
            setCreatureWorkflow(null);
            return;
        }
        const creature = envelope.sandbox.creatures.find(c => c.id === selectedCreatureId);
        if (!creature?.workflow_id) {
            setCreatureWorkflow(null);
            return;
        }
        let cancelled = false;
        void (async () => {
            try {
                const full = await ApiClient.getWorkflow(creature.workflow_id);
                if (!cancelled) setCreatureWorkflow(full);
            } catch {
                if (!cancelled) setCreatureWorkflow(null);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [selectedCreatureId, envelope]);

    const sharedProjectId = React.useMemo(
        () => sharedProjectIdFromProjects(workflowProjects),
        [workflowProjects],
    );

    const creatureBrainProjects = React.useMemo(
        () => projectsWithCreatureBrains(workflowProjects, sharedProjectId, workflows),
        [workflowProjects, sharedProjectId, workflows],
    );

    const selectedCreature = React.useMemo(() => {
        if (!selectedCreatureId || !envelope) return null;
        return envelope.sandbox.creatures.find(c => c.id === selectedCreatureId) ?? null;
    }, [selectedCreatureId, envelope]);

    const selectedCreatureRun = selectedCreatureId ? (lastWorkflowRuns[selectedCreatureId] ?? null) : null;
    const nodeLabels = creatureWorkflow ? nodeIdToLabel(creatureWorkflow.graph) : new Map<string, string>();

    const applyGridResize = useCallback(async () => {
        if (mainTab === 'builder') {
            setLocalBoardDef(prev => resizeBoardDefinition(prev, gridWidthInput, gridHeightInput));
            setBuilderDirty(true);
            setGridResizeError(null);
            return;
        }
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
    }, [mainTab, documentId, gridWidthInput, gridHeightInput]);

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
                });
                setEnvelope(res.envelope);
                setLastWorkflowRuns(prev =>
                    mergeSandboxWorkflowRuns(
                        prev,
                        res.last_workflow_runs,
                        res.envelope.sandbox.creatures.map(c => c.id),
                    ),
                );
                const runs = Object.values(res.last_workflow_runs).filter(
                    (run): run is WorkflowRunResult => run != null,
                );
                const toastSource =
                    selectedCreatureId && res.last_workflow_runs[selectedCreatureId]
                        ? res.last_workflow_runs[selectedCreatureId]
                        : runs[0] ?? null;
                const toastText = collectUserMessagesFromNodeResults(toastSource?.node_results);
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
                    const runSummary = sandboxTickTranscriptSummary(res.last_workflow_runs);
                    return [...prev, `Tick ${tick}: ${runSummary}`].slice(-120);
                });
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            } finally {
                setBusy(false);
            }
        },
        [documentId, selectedCreatureId],
    );

    const startSessionFromBoard = useCallback(async (boardId: string) => {
        setBusy(true);
        setLoadError(null);
        try {
            const created = await ApiClient.createSandboxSession({ board_id: boardId });
            setDocumentId(created.document_id);
            setEnvelope(created.envelope);
            setSelectedBoardId(boardId);
            setLastWorkflowRuns({});
            setTickTranscript([]);
            setSelectedCreatureId(null);
            setInspectedCell(null);
            setPaused(true);
            if (mainTabRef.current !== 'simulation') {
                setMainTab('simulation');
            }
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, []);

    const loadBoardIntoBuilder = useCallback(async (boardId: string) => {
        setBusy(true);
        setLoadError(null);
        try {
            const board = await ApiClient.getSandboxBoard(boardId);
            setLocalBoardDef(board.definition);
            setBuilderBoardId(board.id);
            setBuilderBoardName(board.name);
            setBuilderDirty(false);
            setSelectedBoardId(boardId);
            setSelectedCreatureId(null);
            setInspectedCell(null);
            if (mainTabRef.current !== 'builder') {
                setMainTab('builder');
            }
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, []);

    const handleBoardListSelect = useCallback(
        (boardId: string) => {
            if (mainTabRef.current === 'builder') {
                void loadBoardIntoBuilder(boardId);
            } else {
                void startSessionFromBoard(boardId);
            }
        },
        [loadBoardIntoBuilder, startSessionFromBoard],
    );

    const handleSaveSessionAsBoard = useCallback(async () => {
        const doc = documentId;
        if (!doc) return;
        const name = window.prompt('Board name', 'My Board');
        if (!name?.trim()) return;
        setBusy(true);
        try {
            const board = await ApiClient.saveSandboxSessionAsBoard(doc, {
                mode: 'save_as_new',
                name: name.trim(),
            });
            await refreshBoards();
            setSelectedBoardId(board.id);
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [documentId, refreshBoards]);

    const handleUpdateSourceBoard = useCallback(async () => {
        const doc = documentId;
        const env = envelopeRef.current;
        if (!doc || !env?.board_id) return;
        setBusy(true);
        try {
            await ApiClient.saveSandboxSessionAsBoard(doc, { mode: 'update_source' });
            await refreshBoards();
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [documentId, refreshBoards]);

    const handleNewBoard = useCallback(() => {
        setLocalBoardDef(createEmptyBoardDefinition(SANDBOX_GRID_DEFAULT_WIDTH, SANDBOX_GRID_DEFAULT_HEIGHT));
        setBuilderBoardId(null);
        setBuilderBoardName('Untitled Board');
        setBuilderDirty(false);
        setSelectedCreatureId(null);
        setInspectedCell(null);
        setGridWidthInput(SANDBOX_GRID_DEFAULT_WIDTH);
        setGridHeightInput(SANDBOX_GRID_DEFAULT_HEIGHT);
    }, []);

    const handleSaveBuilderBoard = useCallback(async () => {
        setBusy(true);
        setLoadError(null);
        try {
            if (builderBoardId) {
                await ApiClient.updateSandboxBoard(builderBoardId, {
                    name: builderBoardName,
                    definition: localBoardDef as unknown as Record<string, unknown>,
                });
            } else {
                const created = await ApiClient.createSandboxBoard({
                    name: builderBoardName,
                    definition: localBoardDef as unknown as Record<string, unknown>,
                });
                setBuilderBoardId(created.id);
                setSelectedBoardId(created.id);
            }
            setBuilderDirty(false);
            await refreshBoards();
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [builderBoardId, builderBoardName, localBoardDef, refreshBoards]);

    const dismissCellActionModal = useCallback(() => {
        setCellActionCell(null);
        if (mainTab === 'simulation') {
            setPaused(restorePausedAfterCellActionRef.current);
        }
    }, [mainTab]);

    const completeCellInspect = useCallback(() => {
        const cell = cellActionCell;
        if (!cell) return;
        setCellActionCell(null);
        if (mainTab === 'simulation') {
            setPaused(restorePausedAfterCellActionRef.current);
        }
        setInspectedCell(cell);
        setInspectorTab('explorer');
        if (mainTab === 'simulation' && envelopeRef.current) {
            const occupants = getCellOccupants(envelopeRef.current, cell);
            setSelectedCreatureId(occupants.creatures[0]?.id ?? null);
        } else {
            const occupants = getCellOccupantsFromSandboxState(sandboxStateFromBoardDefinition(localBoardDef), cell);
            setSelectedCreatureId(occupants.creatures[0]?.id ?? null);
        }
    }, [cellActionCell, mainTab, localBoardDef]);

    const completeCellAction = useCallback(
        async (interaction: SandboxCellInteraction) => {
            setCellActionCell(null);
            if (mainTab === 'builder') {
                setLocalBoardDef(prev => applyBoardBuilderInteraction(prev, interaction));
                setBuilderDirty(true);
                return;
            }
            try {
                await runTick([interaction]);
            } finally {
                setPaused(restorePausedAfterCellActionRef.current);
            }
        },
        [mainTab, runTick],
    );

    useEffect(() => {
        if (!catalogLoaded) return;
        const adapter = adapterRef.current;
        if (!adapter) return;
        adapter.setOnCellClick(cell => {
            if (busyRef.current || cellActionModalOpenRef.current) return;
            restorePausedAfterCellActionRef.current = pausedRef.current;
            if (mainTabRef.current === 'simulation') {
                setPaused(true);
            }
            setInspectedCell(null);
            setCellActionNonce(n => n + 1);
            setCellActionCell(cell);
        });
    }, [catalogLoaded]);

    useEffect(() => {
        if (mainTab !== 'simulation' || paused || !documentId) return;
        const id = window.setInterval(() => {
            void runTick([]);
        }, tickRateMs);
        return () => clearInterval(id);
    }, [mainTab, paused, tickRateMs, documentId, runTick]);

    const builderPreviewState = React.useMemo(
        () => sandboxStateFromBoardDefinition(localBoardDef),
        [localBoardDef],
    );

    const cellActionOccupants = React.useMemo(() => {
        if (!cellActionCell) return null;
        if (mainTab === 'simulation' && envelope) {
            return getCellOccupants(envelope, cellActionCell);
        }
        return getCellOccupantsFromSandboxState(builderPreviewState, cellActionCell);
    }, [mainTab, envelope, cellActionCell, builderPreviewState]);

    const modalCanInspect = cellActionOccupants ? cellHasInspectableContent(cellActionOccupants) : false;

    const inspectedOccupants = React.useMemo(() => {
        if (!inspectedCell) return null;
        if (mainTab === 'simulation' && envelope) {
            return getCellOccupants(envelope, inspectedCell);
        }
        return getCellOccupantsFromSandboxState(builderPreviewState, inspectedCell);
    }, [mainTab, envelope, inspectedCell, builderPreviewState]);

    const visibleErrors = collectVisibleErrors(envelope?.last_errors, selectedCreatureId);
    const activeBoardName =
        boards.find(b => b.id === (mainTab === 'simulation' ? selectedBoardId : builderBoardId))?.name ?? null;

    if (loadError) {
        return (
            <div className="h-full flex items-center justify-center text-mw-error text-sm px-6 text-center">
                {loadError}
            </div>
        );
    }

    if (!catalogLoaded || (mainTab === 'simulation' && (!envelope || !documentId))) {
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
            {/* Left — board list */}
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
                        <h2 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                            Boards
                        </h2>
                        <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                            {boards.map(board => {
                                const activeId = mainTab === 'simulation' ? selectedBoardId : builderBoardId;
                                return (
                                    <button
                                        key={board.id}
                                        type="button"
                                        disabled={busy}
                                        onClick={() => void handleBoardListSelect(board.id)}
                                        className={`w-full flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded-lg text-left transition-colors disabled:opacity-50 ${
                                            activeId === board.id
                                                ? 'bg-mw-primary-muted text-mw-primary'
                                                : 'text-mw-text-primary hover:bg-mw-card'
                                        }`}
                                    >
                                        <span className="truncate font-medium">{board.name}</span>
                                        {board.is_system ? (
                                            <span className="shrink-0 text-[10px] text-mw-text-secondary uppercase">
                                                System
                                            </span>
                                        ) : null}
                                    </button>
                                );
                            })}
                            {boards.length === 0 && (
                                <div className="text-xs text-mw-text-secondary text-center py-2">No boards yet</div>
                            )}
                        </div>
                    </div>
                    <div className="p-3 text-[10px] text-mw-text-secondary leading-relaxed space-y-1.5">
                        {mainTab === 'simulation' ? (
                            <>
                                <p>
                                    Select a board to start a new simulation session. Use Play / Step in the toolbar to
                                    advance ticks.
                                </p>
                                <p>Pause to edit cells, resize the grid, or save the session back to a board.</p>
                            </>
                        ) : (
                            <>
                                <p>Select a board to edit its layout, or create a new board from the toolbar.</p>
                                <p>Place walls, food, and creatures with workflow brains, then save.</p>
                            </>
                        )}
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
                <div className="h-12 border-b border-mw-border bg-mw-card flex items-center px-2 sm:px-4 gap-2 sm:gap-3 shrink-0 min-w-0 flex-wrap">
                    {compact && (
                        <>
                            <button
                                type="button"
                                className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                aria-label="Open board list"
                                title="Boards"
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
                    <div
                        role="tablist"
                        aria-label="Sandbox mode"
                        className="flex rounded-lg border border-mw-border bg-mw-page p-0.5 gap-0.5 shrink-0"
                    >
                        {(['simulation', 'builder'] as const).map(tab => (
                            <button
                                key={tab}
                                type="button"
                                role="tab"
                                aria-selected={mainTab === tab}
                                onClick={() => setMainTab(tab)}
                                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                    mainTab === tab
                                        ? 'bg-mw-primary-muted text-mw-primary'
                                        : 'text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card'
                                }`}
                            >
                                {tab === 'simulation' ? 'Simulation' : 'Board Builder'}
                            </button>
                        ))}
                    </div>
                    {mainTab === 'simulation' ? (
                        <>
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
                            {paused ? (
                                <>
                                    <button
                                        type="button"
                                        disabled={busy}
                                        onClick={() => void handleSaveSessionAsBoard()}
                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs disabled:opacity-50"
                                    >
                                        <Save size={14} />
                                        Save as Board
                                    </button>
                                    {envelope?.board_id ? (
                                        <button
                                            type="button"
                                            disabled={busy}
                                            onClick={() => void handleUpdateSourceBoard()}
                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs disabled:opacity-50"
                                        >
                                            <Save size={14} />
                                            Update Board
                                        </button>
                                    ) : null}
                                </>
                            ) : null}
                        </>
                    ) : (
                        <>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={handleNewBoard}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs disabled:opacity-50"
                            >
                                <Plus size={14} />
                                New Board
                            </button>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => void handleSaveBuilderBoard()}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-primary text-white text-xs font-medium disabled:opacity-50"
                            >
                                <Save size={14} />
                                Save{builderDirty ? ' *' : ''}
                            </button>
                        </>
                    )}
                    <span className="text-xs text-mw-text-secondary truncate min-w-0 max-w-[12rem] sm:max-w-xs">
                        {mainTab === 'simulation'
                            ? (activeBoardName ?? 'Simulation session')
                            : (builderBoardName || 'Untitled Board')}
                    </span>
                </div>
                {mainTab === 'simulation' && visibleErrors.length > 0 && (
                    <div className="px-4 py-2 text-xs text-mw-error bg-mw-error-muted border-b border-mw-border shrink-0 space-y-1">
                        {visibleErrors.map(({ creatureId, message }) => (
                            <div key={creatureId}>
                                {selectedCreatureId && creatureId === selectedCreatureId ? null : (
                                    <span className="font-mono text-[10px] mr-1">{creatureId.slice(0, 8)}:</span>
                                )}
                                {message}
                            </div>
                        ))}
                        {visibleErrors.some(({ message }) => shouldShowSandboxDecisionHint(message)) ? (
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
                        {mainTab === 'simulation' ? (
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
                                {selectedCreatureRun ? (
                                    <span
                                        className={`w-4 h-4 rounded-full shrink-0 ${
                                            selectedCreatureRun.status === 'ok'
                                                ? 'bg-green-500'
                                                : selectedCreatureRun.status === 'partial'
                                                  ? 'bg-amber-500'
                                                  : 'bg-red-500'
                                        }`}
                                    />
                                ) : null}
                            </button>
                        ) : null}
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
                                                onClick={() => {
                                                    setInspectedCell(null);
                                                    setSelectedCreatureId(null);
                                                }}
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
                                                    onClick={() => {
                                                        setInspectedCell(null);
                                                        setSelectedCreatureId(null);
                                                    }}
                                                    className="text-mw-primary hover:underline font-medium"
                                                >
                                                    Clear
                                                </button>
                                            </p>
                                        ) : (
                                            <div className="space-y-3">
                                                {inspectedOccupants.creatures.map(creature => (
                                                    <InspectorSection
                                                        key={creature.id}
                                                        title={creature.name ?? `Creature ${creature.id.slice(0, 8)}`}
                                                    >
                                                        <button
                                                            type="button"
                                                            onClick={() => setSelectedCreatureId(creature.id)}
                                                            className={`mb-2 text-[10px] font-medium ${
                                                                selectedCreatureId === creature.id
                                                                    ? 'text-mw-primary'
                                                                    : 'text-mw-text-secondary hover:text-mw-primary'
                                                            }`}
                                                        >
                                                            {selectedCreatureId === creature.id
                                                                ? 'Selected'
                                                                : 'Select creature'}
                                                        </button>
                                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                                            <div className="text-mw-text-secondary">Position</div>
                                                            <div className="text-mw-text-primary tabular-nums text-right font-mono">
                                                                ({creature.position.x}, {creature.position.y})
                                                            </div>
                                                            {mainTab === 'simulation' ? (
                                                                <>
                                                                    <div className="text-mw-text-secondary">Facing</div>
                                                                    <div className="text-mw-text-primary tabular-nums text-right font-mono">
                                                                        {creature.facing ?? 'N'}
                                                                    </div>
                                                                    <div className="text-mw-text-secondary col-span-2">
                                                                        Last action
                                                                    </div>
                                                                    <div className="text-mw-text-primary text-[11px] break-words col-span-2">
                                                                        {formatRecentAction(
                                                                            creature.id,
                                                                            envelope?.sandbox.recent_actions ?? [],
                                                                        )}
                                                                    </div>
                                                                </>
                                                            ) : (
                                                                <>
                                                                    <div className="text-mw-text-secondary">Facing</div>
                                                                    <div className="col-span-1 flex justify-end gap-1">
                                                                        {SANDBOX_FACING_VALUES.map(facing => (
                                                                            <button
                                                                                key={facing}
                                                                                type="button"
                                                                                aria-label={`Face ${facing}`}
                                                                                onClick={() => {
                                                                                    setLocalBoardDef(prev =>
                                                                                        updateBoardCreatureFacing(
                                                                                            prev,
                                                                                            creature.id,
                                                                                            facing,
                                                                                        ),
                                                                                    );
                                                                                    setBuilderDirty(true);
                                                                                }}
                                                                                className={`px-1.5 py-0.5 text-[10px] font-mono rounded border ${
                                                                                    (creature.facing ?? 'N') === facing
                                                                                        ? 'border-mw-primary text-mw-primary'
                                                                                        : 'border-mw-border text-mw-text-secondary hover:text-mw-primary'
                                                                                }`}
                                                                            >
                                                                                {facing}
                                                                            </button>
                                                                        ))}
                                                                    </div>
                                                                    <div className="text-mw-text-secondary">Workflow</div>
                                                                    <div className="text-mw-text-primary text-right font-mono text-[10px] break-all col-span-1">
                                                                        {creature.workflow_id}
                                                                    </div>
                                                                </>
                                                            )}
                                                        </div>
                                                    </InspectorSection>
                                                ))}
                                                {inspectedOccupants.items.map(it => (
                                                    <SandboxItemInspectorSection
                                                        key={it.id}
                                                        item={it}
                                                        readOnly={mainTab !== 'builder'}
                                                        onItemChange={(itemId, patch) => {
                                                            setLocalBoardDef(prev =>
                                                                updateBoardItemMetadata(prev, itemId, patch),
                                                            );
                                                            setBuilderDirty(true);
                                                        }}
                                                    />
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ) : null}
                                {mainTab === 'simulation' && envelope ? (
                                    selectedCreature ? (
                                        <div>
                                            <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                                Creature
                                            </h3>
                                            <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                                                <div className="text-mw-text-secondary">Name</div>
                                                <div className="text-mw-text-primary text-right">
                                                    {selectedCreature.name ?? selectedCreature.id.slice(0, 8)}
                                                </div>
                                                <div className="text-mw-text-secondary">Facing</div>
                                                <div className="text-mw-text-primary tabular-nums text-right font-mono">
                                                    {selectedCreature.facing}
                                                </div>
                                            </div>
                                            <p className="text-xs text-mw-text-primary break-words">
                                                {formatRecentAction(
                                                    selectedCreature.id,
                                                    envelope.sandbox.recent_actions,
                                                )}
                                            </p>
                                        </div>
                                    ) : (
                                        <div>
                                            <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                                Session
                                            </h3>
                                            <div className="grid grid-cols-2 gap-2 text-xs">
                                                <div className="text-mw-text-secondary">Tick</div>
                                                <div className="text-mw-text-primary tabular-nums text-right">
                                                    {envelope.sandbox.tick}
                                                </div>
                                                <div className="text-mw-text-secondary">Creatures</div>
                                                <div className="text-mw-text-primary tabular-nums text-right">
                                                    {envelope.sandbox.creatures.length}
                                                </div>
                                                <div className="text-mw-text-secondary">Board</div>
                                                <div className="text-mw-text-primary text-right truncate">
                                                    {activeBoardName ?? envelope.board_id ?? '—'}
                                                </div>
                                            </div>
                                        </div>
                                    )
                                ) : null}
                                <div>
                                    <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                        {mainTab === 'simulation' ? 'Simulation' : 'Board'}
                                    </h3>
                                    {mainTab === 'builder' ? (
                                        <label className="flex flex-col gap-1 text-xs text-mw-text-secondary mb-3">
                                            Board name
                                            <input
                                                type="text"
                                                value={builderBoardName}
                                                onChange={e => {
                                                    setBuilderBoardName(e.target.value);
                                                    setBuilderDirty(true);
                                                }}
                                                className="px-2 py-1 rounded border border-mw-border bg-mw-page text-mw-text-primary"
                                            />
                                        </label>
                                    ) : null}
                                    {mainTab === 'simulation' ? (
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
                                    ) : null}
                                    <div className="flex flex-wrap items-end gap-2 mb-3">
                                        <label className="flex flex-col gap-0.5 text-xs text-mw-text-secondary">
                                            Width
                                            <input
                                                type="number"
                                                min={SANDBOX_GRID_MIN_SIZE}
                                                max={SANDBOX_GRID_MAX_SIZE}
                                                value={gridWidthInput}
                                                disabled={mainTab === 'simulation' ? !paused || busy : busy}
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
                                                disabled={mainTab === 'simulation' ? !paused || busy : busy}
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
                                            disabled={mainTab === 'simulation' ? !paused || busy : busy}
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
                                    {mainTab === 'simulation' && !paused ? (
                                        <p className="text-[10px] text-mw-text-secondary mb-2">
                                            Pause playback to resize the grid.
                                        </p>
                                    ) : null}
                                    {mainTab === 'builder' ? (
                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                            <div className="text-mw-text-secondary">Items</div>
                                            <div className="text-mw-text-primary tabular-nums text-right">
                                                {localBoardDef.items.length}
                                            </div>
                                            <div className="text-mw-text-secondary">Creatures</div>
                                            <div className="text-mw-text-primary tabular-nums text-right">
                                                {localBoardDef.creatures.length}
                                            </div>
                                        </div>
                                    ) : null}
                                </div>
                                {mainTab === 'simulation' && envelope && !selectedCreature ? (
                                    <div>
                                        <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                            Creatures
                                        </h3>
                                        {envelope.sandbox.creatures.length === 0 ? (
                                            <p className="text-xs text-mw-text-secondary">No creatures on the board.</p>
                                        ) : (
                                            <ul className="space-y-1">
                                                {envelope.sandbox.creatures.map(creature => (
                                                    <li key={creature.id}>
                                                        <button
                                                            type="button"
                                                            onClick={() => setSelectedCreatureId(creature.id)}
                                                            className={`w-full text-left px-2 py-1.5 rounded-lg text-xs transition-colors ${
                                                                selectedCreatureId === creature.id
                                                                    ? 'bg-mw-primary-muted text-mw-primary'
                                                                    : 'hover:bg-mw-card text-mw-text-primary'
                                                            }`}
                                                        >
                                                            {creature.name ?? creature.id.slice(0, 8)}
                                                        </button>
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                ) : null}
                                {mainTab === 'simulation' && envelope && selectedCreature ? (
                                    <div>
                                        <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">
                                            Recent actions
                                        </h3>
                                        {envelope.sandbox.recent_actions?.length ? (
                                            <ul className="text-[10px] text-mw-text-secondary space-y-1">
                                                {[...envelope.sandbox.recent_actions]
                                                    .reverse()
                                                    .filter(
                                                        a =>
                                                            !a.creature_id ||
                                                            a.creature_id === selectedCreature.id,
                                                    )
                                                    .slice(0, 5)
                                                    .map((a, i) => (
                                                        <li key={`${a.tick}-${a.action}-${i}`}>
                                                            t{a.tick}: {a.action}
                                                            {a.reason ? ` — ${a.reason}` : ''}
                                                        </li>
                                                    ))}
                                            </ul>
                                        ) : (
                                            <p className="text-xs text-mw-text-secondary">No recent actions.</p>
                                        )}
                                    </div>
                                ) : null}
                            </div>
                        ) : mainTab === 'simulation' ? (
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
                                {!selectedCreatureId ? (
                                    <div className="text-center text-xs text-mw-text-secondary mt-4">
                                        Select a creature in Explorer to view its workflow run logs.
                                    </div>
                                ) : !selectedCreatureRun ? (
                                    <div className="text-center text-xs text-mw-text-secondary mt-4">
                                        Run a tick when this creature&apos;s brain executes (Play/Step) to see node logs.
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between bg-mw-card-alt px-3 py-2 rounded-lg border border-mw-border">
                                            <span className="text-xs font-semibold text-mw-text-primary">
                                                {selectedCreature?.name ?? 'Creature'} brain run
                                            </span>
                                            <span
                                                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                                    selectedCreatureRun.status === 'ok'
                                                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                                                        : selectedCreatureRun.status === 'partial'
                                                          ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                                                          : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                                                }`}
                                            >
                                                {selectedCreatureRun.status.toUpperCase()}
                                            </span>
                                        </div>
                                        <WorkflowRunLogsNodeResultsList
                                            node_results={selectedCreatureRun.node_results}
                                            getNodeLabel={id => nodeLabels.get(id) ?? id}
                                            userSettings={user?.settings as Record<string, unknown> | undefined}
                                        />
                                    </div>
                                )}
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>
            {cellActionCell ? (
                <SandboxCellActionModal
                    key={`${cellActionCell.x}-${cellActionCell.y}-${cellActionNonce}`}
                    cell={cellActionCell}
                    occupants={cellActionOccupants ?? { items: [], creatures: [] }}
                    canInspect={modalCanInspect}
                    allowCreatureActions
                    workflowProjects={creatureBrainProjects}
                    workflows={workflows}
                    sharedProjectId={sharedProjectId}
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
