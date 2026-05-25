/**
 * Sandbox UI: server-owned state; Phaser adapter is view-only (see docs/SANDBOX.md).
 * Three-column shell matches Workflow Editor (palette + canvas + inspector).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ChevronLeft,
    FolderPlus,
    Loader2,
    Maximize2,
    PanelLeft,
    PanelRight,
    Pause,
    Play,
    Plus,
    Save,
    StepForward,
    ZoomIn,
    ZoomOut,
} from 'lucide-react';

import { ApiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type {
    BoardProject,
    CreatureDefinitionRead,
    FixtureDefinitionRead,
    ItemDefinitionRead,
    RegionDefinitionRead,
    TerrainDefinitionRead,
    WorkflowDefinition,
    WorkflowDefinitionListItem,
    WorkflowProject,
    WorkflowRunResult,
} from '../api/types';
import type { BoardDefinitionJson, SandboxBoardJson, SandboxCreatureJson, SandboxEnvelopeJson } from '../domain/sandbox/types';
import { SANDBOX_FACING_VALUES, sandboxStateFromBoardDefinition } from '../domain/sandbox/types';
import {
    boardsInProject,
    boardCountForProject,
    isDeletableBoardProject,
    nextBoardIdAfterDelete,
    sharedBoardProjectIdFromProjects,
    sortBoardsForList,
} from '../domain/boardProjectMembership';
import {
    projectsWithSandboxCreatureBrains,
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
import { buildSandboxItemRenderCatalog } from '../sandbox/sandboxItemRender';
import type { SandboxGridCellJson } from '../domain/sandbox/types';
import type { SandboxCellInteraction } from '../sandbox/sandboxCellInteractions';
import {
    mergeCollectedUserActions,
    planCreatureUserActionPrompts,
} from '../sandbox/sandboxTickUserActions';
import type { CreatureUserActionsMap, SandboxCreatureUserAction } from '../sandbox/sandboxPromptUserAction';
import { sandboxErrorHintForMessage } from '../sandbox/sandboxLastErrorHint';
import {
    mergeSandboxWorkflowRuns,
} from '../sandbox/sandboxWorkflowRunMerge';
import {
    filterNestedWorkflowRunsForCreature,
    mergeSandboxNestedWorkflowRuns,
    nestedWorkflowRunKey,
    sandboxTickTranscriptSummaryWithNested,
} from '../sandbox/sandboxNestedWorkflowRunMerge';
import { collectSandboxVisibleErrors } from '../sandbox/sandboxSimulationErrors';
import type { SandboxNestedWorkflowRunJson } from '../domain/sandbox/types';
import {
    collectBroadcastSegmentsFromRuns,
    parseBroadcastSegmentsFromEffects,
    type BroadcastSegment,
} from '../domain/broadcastMessage';
import { BroadcastMessageModal } from './workflow/BroadcastMessageModal';
import { SandboxCellActionModal } from './SandboxCellActionModal';
import { SandboxDefinitionsView } from './sandbox/SandboxDefinitionsView';
import { SandboxUserActionModal } from './sandbox/SandboxUserActionModal';
import { SandboxCreatureInventorySection } from './sandbox/SandboxCreatureInventorySection';
import { SandboxItemInspectorSection } from './sandbox/SandboxItemInspectorSection';
import { SandboxFixtureInspectorSection } from './sandbox/SandboxFixtureInspectorSection';
import { SandboxRegionInspectorSection } from './sandbox/SandboxRegionInspectorSection';
import { BoardDeleteControl } from './sandbox/BoardDeleteControl';
import { BoardProjectDeleteControl } from './sandbox/BoardProjectDeleteControl';
import { filterNamesByPrefix } from './workflow-editor/workflowListFilter';
import { addBoardCreatureInventoryEntry } from '../sandbox/sandboxCreatureInventory';
import { parseSandboxFavoriteColors } from '../sandbox/sandboxFavoriteColors';
import { isFixtureItem, isRegionItem } from '../sandbox/sandboxCellOccupants';
import {
    sortItemsForCellInspector,
    type SandboxInspectorDefinitionContext,
} from '../sandbox/sandboxItemInspectorDisplay';
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
import { normalizeBoardName, shouldCommitBoardRename } from '../sandbox/sandboxBoardRename';
import {
    isSandboxStateVersionMismatchError,
    parseTickRateMsInput,
    tickRateMsFromPlayback,
} from '../sandbox/sandboxTickRate';

const SANDBOX_PANEL_WIDTHS_KEY = 'sandbox_panel_widths';

type MainTab = 'simulation' | 'builder' | 'definitions';

const MAIN_TAB_LABELS: Record<MainTab, string> = {
    simulation: 'Simulation',
    builder: 'Board Builder',
    definitions: 'Definitions',
};

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

function nestedRunNodeLabels(meta: SandboxNestedWorkflowRunJson['meta']): Map<string, string> {
    return new Map(Object.entries(meta.node_labels ?? {}));
}

export const SandboxView: React.FC = () => {
    const { user } = useAuth();
    const sandboxFavoriteColors = React.useMemo(
        () => parseSandboxFavoriteColors(user?.settings as Record<string, unknown> | undefined),
        [user?.settings],
    );
    const containerRef = useRef<HTMLDivElement>(null);
    const adapterRef = useRef<PhaserSandboxAdapter | null>(null);
    const sandboxFitKeyRef = useRef<string | null>(null);
    const envelopeRef = useRef<SandboxEnvelopeJson | null>(null);

    const [mainTab, setMainTab] = useState<MainTab>('simulation');
    const [envelope, setEnvelope] = useState<SandboxEnvelopeJson | null>(null);
    const [documentId, setDocumentId] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [catalogLoaded, setCatalogLoaded] = useState(false);
    const [paused, setPaused] = useState(true);
    const [tickRateMs, setTickRateMs] = useState(DEFAULT_TICK_RATE_MS);
    const [tickRateMsInput, setTickRateMsInput] = useState(DEFAULT_TICK_RATE_MS);
    const [gridWidthInput, setGridWidthInput] = useState(SANDBOX_GRID_DEFAULT_WIDTH);
    const [gridHeightInput, setGridHeightInput] = useState(SANDBOX_GRID_DEFAULT_HEIGHT);
    const [gridResizeError, setGridResizeError] = useState<string | null>(null);
    const [tickError, setTickError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [workflowProjects, setWorkflowProjects] = useState<WorkflowProject[]>([]);
    const [itemDefinitions, setItemDefinitions] = useState<ItemDefinitionRead[]>([]);
    const [terrainDefinitions, setTerrainDefinitions] = useState<TerrainDefinitionRead[]>([]);
    const [fixtureDefinitions, setFixtureDefinitions] = useState<FixtureDefinitionRead[]>([]);
    const [creatureDefinitions, setCreatureDefinitions] = useState<CreatureDefinitionRead[]>([]);
    const [regionDefinitions, setRegionDefinitions] = useState<RegionDefinitionRead[]>([]);
    const renderCatalog = React.useMemo(
        () => buildSandboxItemRenderCatalog(itemDefinitions),
        [itemDefinitions],
    );
    const [boards, setBoards] = useState<SandboxBoardJson[]>([]);
    const [boardProjects, setBoardProjects] = useState<BoardProject[]>([]);
    const [selectedBoardProjectId, setSelectedBoardProjectId] = useState<string | null>(null);
    const [boardListSort, setBoardListSort] = useState<'updated' | 'name'>('updated');
    const [boardNameFilter, setBoardNameFilter] = useState('');
    const [newBoardProjectNameDraft, setNewBoardProjectNameDraft] = useState('');
    const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
    const [builderBoardId, setBuilderBoardId] = useState<string | null>(null);
    const [builderBoardName, setBuilderBoardName] = useState('Untitled Board');
    const [localBoardDef, setLocalBoardDef] = useState<BoardDefinitionJson>(() =>
        createEmptyBoardDefinition(SANDBOX_GRID_DEFAULT_WIDTH, SANDBOX_GRID_DEFAULT_HEIGHT),
    );
    const [builderDirty, setBuilderDirty] = useState(false);
    const [simulationBoardNameDraft, setSimulationBoardNameDraft] = useState('');

    const [inspectorTab, setInspectorTab] = useState<'explorer' | 'logs'>('explorer');
    const [lastWorkflowRuns, setLastWorkflowRuns] = useState<Record<string, WorkflowRunResult | null>>({});
    const [lastNestedWorkflowRuns, setLastNestedWorkflowRuns] = useState<SandboxNestedWorkflowRunJson[]>([]);
    const [selectedCreatureId, setSelectedCreatureId] = useState<string | null>(null);
    const [creatureWorkflow, setCreatureWorkflow] = useState<WorkflowDefinition | null>(null);
    const [tickTranscript, setTickTranscript] = useState<string[]>([]);
    const [broadcastPromptSegments, setBroadcastPromptSegments] = useState<BroadcastSegment[]>([]);

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
    const [userActionPrompt, setUserActionPrompt] = useState<{
        creatures: SandboxCreatureJson[];
        collected: CreatureUserActionsMap;
        index: number;
        pendingInteractions: unknown[];
    } | null>(null);
    const [inspectedCell, setInspectedCell] = useState<SandboxGridCellJson | null>(null);
    const restorePausedAfterCellActionRef = useRef(true);
    const restorePausedAfterUserActionRef = useRef(true);
    const busyRef = useRef(busy);
    busyRef.current = busy;
    const pausedRef = useRef(paused);
    pausedRef.current = paused;
    const cellActionModalOpenRef = useRef(false);
    cellActionModalOpenRef.current = cellActionCell !== null || userActionPrompt !== null || broadcastPromptSegments.length > 0;
    const mainTabRef = useRef(mainTab);
    mainTabRef.current = mainTab;
    const pendingSimulationBoardReloadIdRef = useRef<string | null>(null);

    useEffect(() => {
        envelopeRef.current = envelope;
    }, [envelope]);

    const broadcastPromptOpenRef = useRef(false);
    broadcastPromptOpenRef.current = broadcastPromptSegments.length > 0;

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

    const refreshBoardCatalog = useCallback(async () => {
        const [boardList, projects] = await Promise.all([
            ApiClient.listSandboxBoards(),
            ApiClient.getBoardProjects().catch(() => [] as BoardProject[]),
        ]);
        setBoards(boardList.boards);
        setBoardProjects(projects);
        return { boards: boardList.boards, projects };
    }, []);

    const refreshDefinitionCatalog = useCallback(async () => {
        const [items, terrain, fixtures, creatures, regions] = await Promise.all([
            ApiClient.listItemDefinitions().catch(() => [] as ItemDefinitionRead[]),
            ApiClient.listTerrainDefinitions().catch(() => [] as TerrainDefinitionRead[]),
            ApiClient.listFixtureDefinitions().catch(() => [] as FixtureDefinitionRead[]),
            ApiClient.listCreatureDefinitions().catch(() => [] as CreatureDefinitionRead[]),
            ApiClient.listRegionDefinitions().catch(() => [] as RegionDefinitionRead[]),
        ]);
        setItemDefinitions(items);
        setTerrainDefinitions(terrain);
        setFixtureDefinitions(fixtures);
        setCreatureDefinitions(creatures);
        setRegionDefinitions(regions);
    }, []);

    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const [wfs, projs, catalog, created] = await Promise.all([
                    ApiClient.getWorkflows(),
                    ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]),
                    refreshBoardCatalog(),
                    ApiClient.createSandboxSession(),
                ]);
                if (cancelled) return;
                setWorkflows(wfs);
                setWorkflowProjects(projs);
                setBoards(catalog.boards);
                setBoardProjects(catalog.projects);
                await refreshDefinitionCatalog();
                if (cancelled) return;
                setCatalogLoaded(true);
                setDocumentId(created.document_id);
                setEnvelope(created.envelope);
                const initialTickRate = tickRateMsFromPlayback(created.envelope.playback);
                setTickRateMs(initialTickRate);
                setTickRateMsInput(initialTickRate);
                setSelectedBoardId(created.envelope.board_id ?? null);
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [refreshBoardCatalog, refreshDefinitionCatalog]);

    useEffect(() => {
        if (!catalogLoaded || mainTab === 'definitions') return;
        const el = containerRef.current;
        if (!el) return;
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(el);
        adapterRef.current = adapter;
        return () => {
            adapter.destroy();
            adapterRef.current = null;
            sandboxFitKeyRef.current = '';
        };
    }, [catalogLoaded, mainTab]);

    useEffect(() => {
        const adapter = adapterRef.current;
        if (!adapter || mainTab === 'definitions') return;

        const fitKey =
            mainTab === 'simulation' ? `sim:${documentId ?? ''}` : `builder:${builderBoardId ?? ''}`;

        let stateUpdated = false;
        if (mainTab === 'simulation' && envelope) {
            adapter.setState(envelope.sandbox, { selectedCreatureId, renderCatalog });
            stateUpdated = true;
        } else if (mainTab === 'builder') {
            adapter.setState(sandboxStateFromBoardDefinition(localBoardDef), {
                selectedCreatureId,
                renderCatalog,
            });
            stateUpdated = true;
        }

        if (stateUpdated && sandboxFitKeyRef.current !== fitKey) {
            sandboxFitKeyRef.current = fitKey;
            requestAnimationFrame(() => adapter.fitToView());
        }
    }, [mainTab, envelope, localBoardDef, selectedCreatureId, documentId, builderBoardId, renderCatalog]);

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

    const sharedBoardProjectId = React.useMemo(
        () => sharedBoardProjectIdFromProjects(boardProjects),
        [boardProjects],
    );

    const displayedBoardProjects = React.useMemo(
        () =>
            [...boardProjects].sort(
                (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
            ),
        [boardProjects],
    );

    const selectedBoardProject = React.useMemo(
        () =>
            selectedBoardProjectId
                ? boardProjects.find(p => p.id === selectedBoardProjectId) ?? null
                : null,
        [boardProjects, selectedBoardProjectId],
    );

    const boardsInCurrentProject = React.useMemo(() => {
        if (!selectedBoardProjectId) return [];
        return boardsInProject(selectedBoardProjectId, sharedBoardProjectId, boards);
    }, [boards, selectedBoardProjectId, sharedBoardProjectId]);

    const displayedBoardsInProject = React.useMemo(() => {
        const sorted = sortBoardsForList(boardsInCurrentProject, boardListSort);
        return filterNamesByPrefix(sorted, boardNameFilter);
    }, [boardsInCurrentProject, boardListSort, boardNameFilter]);

    const systemBoards = React.useMemo(() => boards.filter(b => b.is_system), [boards]);

    const resolveBoardProjectIdForCreate = useCallback((): string | null => {
        return selectedBoardProjectId ?? sharedBoardProjectId;
    }, [selectedBoardProjectId, sharedBoardProjectId]);

    const selectedBoardProjectDeleteBoardCount = React.useMemo(() => {
        if (!selectedBoardProjectId) return 0;
        return boardsInProject(selectedBoardProjectId, sharedBoardProjectId, boards).length;
    }, [selectedBoardProjectId, sharedBoardProjectId, boards]);

    const creatureBrainProjects = React.useMemo(
        () => projectsWithSandboxCreatureBrains(workflowProjects, sharedProjectId, workflows),
        [workflowProjects, sharedProjectId, workflows],
    );

    const selectedCreature = React.useMemo(() => {
        if (!selectedCreatureId || !envelope) return null;
        return envelope.sandbox.creatures.find(c => c.id === selectedCreatureId) ?? null;
    }, [selectedCreatureId, envelope]);

    const selectedCreatureRun = selectedCreatureId ? (lastWorkflowRuns[selectedCreatureId] ?? null) : null;
    const visibleNestedRuns = filterNestedWorkflowRunsForCreature(lastNestedWorkflowRuns, selectedCreatureId);
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
        async (
            interactions: unknown[],
            creatureUserActions?: Record<string, { action: string; item_type?: string }>,
        ) => {
            const doc = documentId;
            const env = envelopeRef.current;
            if (!doc || !env) return;
            setBusy(true);
            setTickError(null);
            try {
                const res = await ApiClient.tickSandbox(doc, {
                    interactions,
                    state_version: env.state_version,
                    ...(creatureUserActions && Object.keys(creatureUserActions).length > 0
                        ? { creature_user_actions: creatureUserActions }
                        : {}),
                });
                setEnvelope(res.envelope);
                if (res.simulation_effects?.force_pause) {
                    setPaused(true);
                }
                setLastWorkflowRuns(prev =>
                    mergeSandboxWorkflowRuns(
                        prev,
                        res.last_workflow_runs,
                        res.envelope.sandbox.creatures.map(c => c.id),
                    ),
                );
                setLastNestedWorkflowRuns(prev =>
                    mergeSandboxNestedWorkflowRuns(prev, res.nested_workflow_runs ?? []),
                );
                const runs = Object.values(res.last_workflow_runs).filter(
                    (run): run is WorkflowRunResult => run != null,
                );
                const effectSegments = parseBroadcastSegmentsFromEffects(
                    res.simulation_effects?.broadcast_messages,
                );
                const fallbackSegments = collectBroadcastSegmentsFromRuns(runs);
                const broadcastSegments =
                    effectSegments.length > 0 ? effectSegments : fallbackSegments;
                if (broadcastSegments.length > 0) {
                    setBroadcastPromptSegments(broadcastSegments);
                    setPaused(true);
                }
                setTickTranscript(prev => {
                    const tick = res.envelope.sandbox.tick;
                    const runSummary = sandboxTickTranscriptSummaryWithNested(
                        res.last_workflow_runs,
                        res.nested_workflow_runs ?? [],
                    );
                    return [...prev, `Tick ${tick}: ${runSummary}`].slice(-120);
                });
                setTickError(null);
            } catch (e) {
                if (isSandboxStateVersionMismatchError(e)) {
                    try {
                        const refreshed = await ApiClient.getSandboxSession(doc);
                        setEnvelope(refreshed.envelope);
                        setTickError(null);
                    } catch (refreshError) {
                        setLoadError(refreshError instanceof Error ? refreshError.message : String(refreshError));
                    }
                } else {
                    setTickError(e instanceof Error ? e.message : String(e));
                }
            } finally {
                setBusy(false);
            }
        },
        [documentId],
    );

    const runTickWithUserActions = useCallback(
        async (interactions: unknown[]) => {
            const env = envelopeRef.current;
            if (!env || mainTabRef.current !== 'simulation') {
                await runTick(interactions);
                return;
            }
            setBusy(true);
            setTickError(null);
            try {
                const { needing } = await planCreatureUserActionPrompts(env.sandbox.creatures);
                if (needing.length === 0) {
                    await runTick(interactions);
                    return;
                }
                restorePausedAfterUserActionRef.current = pausedRef.current;
                setPaused(true);
                setUserActionPrompt({
                    creatures: needing,
                    collected: {},
                    index: 0,
                    pendingInteractions: interactions,
                });
            } catch (e) {
                setTickError(e instanceof Error ? e.message : String(e));
            } finally {
                setBusy(false);
            }
        },
        [runTick],
    );

    const handleUserActionConfirm = useCallback(
        (action: SandboxCreatureUserAction) => {
            setUserActionPrompt(prev => {
                if (!prev) return null;
                const creature = prev.creatures[prev.index];
                const collected = { ...prev.collected, [creature.id]: action };
                const nextIndex = prev.index + 1;
                if (nextIndex >= prev.creatures.length) {
                    const restorePaused = restorePausedAfterUserActionRef.current;
                    void runTick(
                        prev.pendingInteractions,
                        mergeCollectedUserActions(collected),
                    ).finally(() => {
                        setPaused(restorePaused);
                    });
                    return null;
                }
                return { ...prev, collected, index: nextIndex };
            });
        },
        [runTick],
    );

    const handleUserActionDismiss = useCallback(() => {
        setUserActionPrompt(null);
        setPaused(true);
    }, []);

    const startSessionFromBoard = useCallback(async (boardId: string) => {
        setBusy(true);
        setLoadError(null);
        try {
            const created = await ApiClient.createSandboxSession({ board_id: boardId });
            setDocumentId(created.document_id);
            setEnvelope(created.envelope);
            const sessionTickRate = tickRateMsFromPlayback(created.envelope.playback);
            setTickRateMs(sessionTickRate);
            setTickRateMsInput(sessionTickRate);
            setSelectedBoardId(boardId);
            setLastWorkflowRuns({});
            setLastNestedWorkflowRuns([]);
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

    const commitTickRateMsInput = useCallback(() => {
        const parsed = parseTickRateMsInput(String(tickRateMsInput), tickRateMs);
        if (parsed === null) {
            setTickRateMsInput(tickRateMs);
            return;
        }
        setTickRateMs(parsed);
        setTickRateMsInput(parsed);
    }, [tickRateMsInput, tickRateMs]);

    const revertTickRateMsInput = useCallback(() => {
        setTickRateMsInput(tickRateMs);
    }, [tickRateMs]);

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

    const handleCreateBoardProject = useCallback(async () => {
        const name = newBoardProjectNameDraft.trim();
        if (!name) return;
        setBusy(true);
        try {
            const created = await ApiClient.createBoardProject({ name });
            setNewBoardProjectNameDraft('');
            await refreshBoardCatalog();
            setSelectedBoardProjectId(created.id);
            setBoardNameFilter('');
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [newBoardProjectNameDraft, refreshBoardCatalog]);

    const moveBoardToProject = useCallback(
        async (boardId: string, projectId: string): Promise<boolean> => {
            setBusy(true);
            try {
                await ApiClient.updateSandboxBoard(boardId, { project_id: projectId });
                await refreshBoardCatalog();
                return true;
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
                return false;
            } finally {
                setBusy(false);
            }
        },
        [refreshBoardCatalog],
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
                project_id: resolveBoardProjectIdForCreate(),
            });
            await refreshBoardCatalog();
            setSelectedBoardId(board.id);
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [documentId, refreshBoardCatalog, resolveBoardProjectIdForCreate]);

    const handleUpdateSourceBoard = useCallback(async () => {
        const doc = documentId;
        const env = envelopeRef.current;
        if (!doc || !env?.board_id) return;
        setBusy(true);
        try {
            await ApiClient.saveSandboxSessionAsBoard(doc, { mode: 'update_source' });
            await refreshBoardCatalog();
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [documentId, refreshBoardCatalog]);

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
            let savedBoardId = builderBoardId;
            if (builderBoardId) {
                await ApiClient.updateSandboxBoard(builderBoardId, {
                    name: builderBoardName,
                    definition: localBoardDef as unknown as Record<string, unknown>,
                });
            } else {
                const created = await ApiClient.createSandboxBoard({
                    name: builderBoardName,
                    definition: localBoardDef as unknown as Record<string, unknown>,
                    project_id: resolveBoardProjectIdForCreate(),
                });
                savedBoardId = created.id;
                setBuilderBoardId(created.id);
                setSelectedBoardId(created.id);
            }
            if (savedBoardId) {
                pendingSimulationBoardReloadIdRef.current = savedBoardId;
            }
            setBuilderDirty(false);
            await refreshBoardCatalog();
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [builderBoardId, builderBoardName, localBoardDef, refreshBoardCatalog, resolveBoardProjectIdForCreate]);

    const handleMainTabChange = useCallback(
        (tab: MainTab) => {
            if (tab === 'simulation') {
                const reloadBoardId = pendingSimulationBoardReloadIdRef.current;
                if (reloadBoardId) {
                    pendingSimulationBoardReloadIdRef.current = null;
                    void startSessionFromBoard(reloadBoardId);
                    return;
                }
            }
            setMainTab(tab);
        },
        [startSessionFromBoard],
    );

    const activeBoardId = mainTab === 'simulation' ? selectedBoardId : builderBoardId;
    const activeBoard = boards.find(b => b.id === activeBoardId) ?? null;
    const isActiveSystemBoard = activeBoard?.is_system ?? false;
    const canEditToolbarBoardName =
        mainTab === 'builder' ? !isActiveSystemBoard : Boolean(selectedBoardId && !isActiveSystemBoard);
    const canDeleteActiveBoard = Boolean(activeBoard && !isActiveSystemBoard);
    const toolbarBoardNameValue = mainTab === 'builder' ? builderBoardName : simulationBoardNameDraft;
    const toolbarBoardNameDisplay =
        mainTab === 'simulation'
            ? activeBoard?.name ?? 'Simulation session'
            : builderBoardName || 'Untitled Board';

    const handleDeleteBoardProject = useCallback(async () => {
        if (!selectedBoardProjectId || !selectedBoardProject) return;
        const boardCount = selectedBoardProjectDeleteBoardCount;
        try {
            await ApiClient.deleteBoardProject(selectedBoardProjectId, {
                deleteBoards: boardCount > 0,
            });
            if (
                activeBoardId &&
                boardsInProject(selectedBoardProjectId, sharedBoardProjectId, boards).some(
                    b => b.id === activeBoardId,
                )
            ) {
                if (mainTab === 'simulation') {
                    setDocumentId(null);
                    setEnvelope(null);
                    setSelectedBoardId(null);
                } else {
                    handleNewBoard();
                }
            }
            setSelectedBoardProjectId(null);
            setBoardNameFilter('');
            await refreshBoardCatalog();
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e));
            throw e;
        }
    }, [
        activeBoardId,
        boards,
        handleNewBoard,
        mainTab,
        refreshBoardCatalog,
        selectedBoardProject,
        selectedBoardProjectDeleteBoardCount,
        selectedBoardProjectId,
        sharedBoardProjectId,
    ]);

    const handleDeleteBoard = useCallback(
        async (boardId: string) => {
            const board = boards.find(b => b.id === boardId);
            if (!board || board.is_system) return;

            const projectId =
                selectedBoardProjectId ?? board.project_id ?? sharedBoardProjectId;
            const projectBoards = projectId
                ? sortBoardsForList(
                      boardsInProject(projectId, sharedBoardProjectId, boards),
                      boardListSort,
                  )
                : [];
            const sortedIds = filterNamesByPrefix(projectBoards, boardNameFilter).map(b => b.id);
            const nextId = nextBoardIdAfterDelete(sortedIds, boardId);
            const wasActive = activeBoardId === boardId;

            if (projectId) {
                setSelectedBoardProjectId(projectId);
            }

            setBusy(true);
            try {
                await ApiClient.deleteSandboxBoard(boardId);
                await refreshBoardCatalog();

                if (!wasActive) return;

                if (nextId) {
                    if (mainTab === 'builder') {
                        await loadBoardIntoBuilder(nextId);
                    } else {
                        await startSessionFromBoard(nextId);
                    }
                    return;
                }

                if (mainTab === 'simulation') {
                    setDocumentId(null);
                    setEnvelope(null);
                    setSelectedBoardId(null);
                } else {
                    handleNewBoard();
                }
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
                throw e;
            } finally {
                setBusy(false);
            }
        },
        [
            activeBoardId,
            boardListSort,
            boardNameFilter,
            boards,
            handleNewBoard,
            loadBoardIntoBuilder,
            mainTab,
            refreshBoardCatalog,
            selectedBoardProjectId,
            sharedBoardProjectId,
            startSessionFromBoard,
        ],
    );

    useEffect(() => {
        if (mainTab !== 'simulation') return;
        setSimulationBoardNameDraft(activeBoard?.name ?? '');
    }, [mainTab, selectedBoardId, activeBoard?.name]);

    const revertToolbarBoardName = useCallback(() => {
        if (mainTab === 'builder') {
            setBuilderBoardName(activeBoard?.name ?? 'Untitled Board');
            return;
        }
        setSimulationBoardNameDraft(activeBoard?.name ?? '');
    }, [mainTab, activeBoard?.name]);

    const handleToolbarBoardNameChange = useCallback(
        (value: string) => {
            if (mainTab === 'builder') {
                setBuilderBoardName(value);
                setBuilderDirty(true);
                return;
            }
            setSimulationBoardNameDraft(value);
        },
        [mainTab],
    );

    const handleToolbarBoardNameCommit = useCallback(async () => {
        if (mainTab === 'builder') {
            const fallback = activeBoard?.name ?? 'Untitled Board';
            const normalized = normalizeBoardName(toolbarBoardNameValue, fallback);
            if (normalized !== builderBoardName) {
                setBuilderBoardName(normalized);
                setBuilderDirty(true);
            }
            return;
        }

        if (!selectedBoardId || isActiveSystemBoard) return;
        const currentName = activeBoard?.name ?? '';
        if (
            !shouldCommitBoardRename({
                currentName,
                draftName: simulationBoardNameDraft,
                isSystem: isActiveSystemBoard,
            })
        ) {
            setSimulationBoardNameDraft(currentName);
            return;
        }

        const normalized = normalizeBoardName(simulationBoardNameDraft, currentName);
        setBusy(true);
        setLoadError(null);
        try {
            await ApiClient.updateSandboxBoard(selectedBoardId, { name: normalized });
            setSimulationBoardNameDraft(normalized);
            await refreshBoardCatalog();
        } catch (e) {
            setSimulationBoardNameDraft(currentName);
            setLoadError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    }, [
        mainTab,
        activeBoard?.name,
        builderBoardName,
        isActiveSystemBoard,
        refreshBoardCatalog,
        selectedBoardId,
        simulationBoardNameDraft,
        toolbarBoardNameValue,
    ]);

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
            const doc = documentId;
            const env = envelopeRef.current;
            if (!doc || !env) return;
            setBusy(true);
            setLoadError(null);
            try {
                const res = await ApiClient.applySandboxInteractions(doc, {
                    interactions: [interaction],
                    state_version: env.state_version,
                });
                setEnvelope(res.envelope);
            } catch (e) {
                setLoadError(e instanceof Error ? e.message : String(e));
            } finally {
                setBusy(false);
                setPaused(restorePausedAfterCellActionRef.current);
            }
        },
        [mainTab, documentId],
    );

    useEffect(() => {
        if (!catalogLoaded || mainTab === 'definitions') return;
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
    }, [catalogLoaded, mainTab]);

    useEffect(() => {
        if (mainTab !== 'simulation' || paused || !documentId) return;
        const id = window.setInterval(() => {
            if (busyRef.current || broadcastPromptOpenRef.current) return;
            void runTickWithUserActions([]);
        }, tickRateMs);
        return () => clearInterval(id);
    }, [mainTab, paused, tickRateMs, documentId, runTickWithUserActions]);

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

    const inspectorDefinitionContext = React.useMemo<SandboxInspectorDefinitionContext>(
        () => ({
            itemDefinitions,
            terrainDefinitions,
            fixtureDefinitions,
            workflows,
        }),
        [itemDefinitions, terrainDefinitions, fixtureDefinitions, workflows],
    );

    const inspectedCellItems = React.useMemo(
        () => sortItemsForCellInspector(inspectedOccupants?.items ?? []),
        [inspectedOccupants?.items],
    );

    const visibleErrors = collectSandboxVisibleErrors(envelope, selectedCreatureId);
    const activeBoardName =
        boards.find(b => b.id === (mainTab === 'simulation' ? selectedBoardId : builderBoardId))?.name ?? null;

    if (loadError) {
        return (
            <div className="h-full flex items-center justify-center text-mw-error text-sm px-6 text-center">
                {loadError}
            </div>
        );
    }

    if (!catalogLoaded) {
        return (
            <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                <Loader2 className="animate-spin" size={24} />
                <span>Loading sandbox…</span>
            </div>
        );
    }

    const mainTabSwitcher = (
        <div
            role="tablist"
            aria-label="Sandbox mode"
            className="flex rounded-lg border border-mw-border bg-mw-page p-0.5 gap-0.5 shrink-0"
        >
            {(['simulation', 'builder', 'definitions'] as const).map(tab => (
                <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={mainTab === tab}
                    onClick={() => handleMainTabChange(tab)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                        mainTab === tab
                            ? 'bg-mw-primary-muted text-mw-primary'
                            : 'text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card'
                    }`}
                >
                    {MAIN_TAB_LABELS[tab]}
                </button>
            ))}
        </div>
    );

    if (mainTab === 'definitions') {
        return (
            <div className="flex flex-col h-full overflow-hidden bg-mw-page">
                <div className="h-12 border-b border-mw-border bg-mw-card flex items-center px-4 gap-3 shrink-0">
                    {mainTabSwitcher}
                </div>
                <div className="flex-1 min-h-0">
                    <SandboxDefinitionsView
                        workflows={workflows}
                        workflowProjects={workflowProjects}
                        sharedProjectId={sharedProjectId}
                        sandboxFavoriteColors={sandboxFavoriteColors}
                        onDefinitionsChange={refreshDefinitionCatalog}
                    />
                </div>
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
                    <div className="p-3 border-b border-mw-border shrink-0 space-y-3">
                        <h2 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">
                            Boards
                        </h2>
                        {systemBoards.length > 0 ? (
                            <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                {systemBoards.map(board => {
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
                                            <span className="shrink-0 text-[10px] text-mw-text-secondary uppercase">
                                                System
                                            </span>
                                        </button>
                                    );
                                })}
                            </div>
                        ) : null}
                        {!selectedBoardProjectId ? (
                            <>
                                <div className="flex gap-1">
                                    <input
                                        type="text"
                                        value={newBoardProjectNameDraft}
                                        onChange={e => setNewBoardProjectNameDraft(e.target.value)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter') void handleCreateBoardProject();
                                        }}
                                        placeholder="New project…"
                                        aria-label="New board project name"
                                        className="min-w-0 flex-1 px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => void handleCreateBoardProject()}
                                        className="shrink-0 p-1 text-mw-primary hover:bg-mw-primary-muted rounded transition-colors"
                                        title="Create project"
                                    >
                                        <FolderPlus size={14} />
                                    </button>
                                </div>
                                <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                    {displayedBoardProjects.map(p => (
                                        <button
                                            key={p.id}
                                            type="button"
                                            onClick={() => {
                                                setSelectedBoardProjectId(p.id);
                                                setBoardNameFilter('');
                                            }}
                                            className="w-full flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded-lg text-left text-mw-text-primary hover:bg-mw-card transition-colors"
                                        >
                                            <span className="truncate font-medium">{p.name}</span>
                                            <span className="shrink-0 text-xs text-mw-text-secondary tabular-nums">
                                                {boardCountForProject(p, sharedBoardProjectId, boards)}
                                            </span>
                                        </button>
                                    ))}
                                    {displayedBoardProjects.length === 0 && (
                                        <div className="text-xs text-mw-text-secondary text-center py-2">
                                            No projects yet
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="flex items-center gap-1 min-w-0">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setSelectedBoardProjectId(null);
                                            setBoardNameFilter('');
                                        }}
                                        className="shrink-0 p-1 rounded text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card"
                                        title="All projects"
                                    >
                                        <ChevronLeft size={16} />
                                    </button>
                                    <span
                                        className="text-xs font-semibold text-mw-text-primary truncate min-w-0 flex-1"
                                        title={selectedBoardProject?.name ?? ''}
                                    >
                                        {selectedBoardProject?.name ?? 'Project'}
                                    </span>
                                    {selectedBoardProject ? (
                                        <BoardProjectDeleteControl
                                            projectName={selectedBoardProject.name}
                                            boardCount={selectedBoardProjectDeleteBoardCount}
                                            disabled={!isDeletableBoardProject(selectedBoardProject)}
                                            onConfirmDelete={handleDeleteBoardProject}
                                        />
                                    ) : null}
                                </div>
                                <div
                                    role="group"
                                    aria-label="Board list sort"
                                    className="flex rounded-lg border border-mw-border bg-mw-page p-0.5 gap-0.5"
                                >
                                    {(
                                        [
                                            ['updated', 'Last updated'],
                                            ['name', 'Name A–Z'],
                                        ] as const
                                    ).map(([key, label]) => (
                                        <button
                                            key={key}
                                            type="button"
                                            onClick={() => setBoardListSort(key)}
                                            className={`flex-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md transition-colors ${
                                                boardListSort === key
                                                    ? 'bg-mw-primary-muted text-mw-primary'
                                                    : 'text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card'
                                            }`}
                                        >
                                            {label}
                                        </button>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    value={boardNameFilter}
                                    onChange={e => setBoardNameFilter(e.target.value)}
                                    placeholder="Filter…"
                                    aria-label="Filter boards by name prefix"
                                    className="w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                                />
                                <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                    {displayedBoardsInProject.map(board => {
                                        const activeId =
                                            mainTab === 'simulation' ? selectedBoardId : builderBoardId;
                                        return (
                                            <div key={board.id} className="flex items-stretch gap-1 min-w-0">
                                                <button
                                                    type="button"
                                                    disabled={busy}
                                                    onClick={() => void handleBoardListSelect(board.id)}
                                                    className={`flex flex-1 min-w-0 items-center gap-2 px-2 py-1.5 text-sm rounded-lg text-left transition-colors disabled:opacity-50 ${
                                                        activeId === board.id
                                                            ? 'bg-mw-primary-muted text-mw-primary font-medium'
                                                            : 'text-mw-text-primary hover:bg-mw-card'
                                                    }`}
                                                >
                                                    <span className="truncate font-medium">{board.name}</span>
                                                </button>
                                                <div className="flex items-center gap-0.5 shrink-0">
                                                    <select
                                                        value={board.project_id ?? sharedBoardProjectId ?? ''}
                                                        aria-label={`Move ${board.name} to project`}
                                                        disabled={busy}
                                                        onClick={e => e.stopPropagation()}
                                                        onChange={e => {
                                                            e.stopPropagation();
                                                            const v = e.target.value;
                                                            if (v) void moveBoardToProject(board.id, v);
                                                        }}
                                                        className="max-w-[5rem] text-[10px] border border-mw-border bg-mw-card text-mw-text-primary rounded px-1 py-0.5"
                                                    >
                                                        {displayedBoardProjects.map(p => (
                                                            <option key={p.id} value={p.id}>
                                                                {p.name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <BoardDeleteControl
                                                        boardName={board.name}
                                                        disabled={busy}
                                                        onConfirmDelete={() => handleDeleteBoard(board.id)}
                                                    />
                                                </div>
                                            </div>
                                        );
                                    })}
                                    {displayedBoardsInProject.length === 0 && (
                                        <div className="text-xs text-mw-text-secondary text-center py-2">
                                            No boards in this project
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                    <div className="p-3 text-[10px] text-mw-text-secondary leading-relaxed space-y-1.5">
                        {mainTab === 'simulation' ? (
                            <>
                                <p>
                                    System boards are always available at the top. Open a project to browse your saved
                                    boards, or select one to start a new simulation session.
                                </p>
                                <p>Pause to edit cells, resize the grid, or save the session back to a board.</p>
                            </>
                        ) : (
                            <>
                                <p>
                                    Drill into a project to open a board for editing, or use New Board in the toolbar
                                    (saved into the open project).
                                </p>
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
                    {mainTabSwitcher}
                    {mainTab === 'simulation' ? (
                        <>
                            <button
                                type="button"
                                disabled={busy || !envelope}
                                onClick={() => setPaused(p => !p)}
                                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-mw-primary text-white text-xs font-medium disabled:opacity-50"
                            >
                                {paused ? <Play size={14} /> : <Pause size={14} />}
                                {paused ? 'Play' : 'Pause'}
                            </button>
                            <button
                                type="button"
                                disabled={busy || !envelope}
                                onClick={() => void runTickWithUserActions([])}
                                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-mw-card border border-mw-border text-xs"
                            >
                                <StepForward size={14} />
                                Step
                            </button>
                            {tickError ? (
                                <p className="text-xs text-mw-error max-w-xs truncate" role="alert" title={tickError}>
                                    {tickError}
                                </p>
                            ) : null}
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
                                disabled={busy || (builderBoardId !== null && isActiveSystemBoard)}
                                onClick={() => void handleSaveBuilderBoard()}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-primary text-white text-xs font-medium disabled:opacity-50"
                                title={
                                    builderBoardId !== null && isActiveSystemBoard
                                        ? 'System boards cannot be saved'
                                        : undefined
                                }
                            >
                                <Save size={14} />
                                Save{builderDirty ? ' *' : ''}
                            </button>
                        </>
                    )}
                    {canEditToolbarBoardName ? (
                        <input
                            type="text"
                            value={toolbarBoardNameValue}
                            disabled={busy}
                            onChange={e => handleToolbarBoardNameChange(e.target.value)}
                            onBlur={() => void handleToolbarBoardNameCommit()}
                            onKeyDown={e => {
                                if (e.key === 'Enter') {
                                    e.currentTarget.blur();
                                } else if (e.key === 'Escape') {
                                    revertToolbarBoardName();
                                    e.currentTarget.blur();
                                }
                            }}
                            placeholder={mainTab === 'builder' ? 'Board name' : 'Board name'}
                            aria-label="Board name"
                            className="text-xs font-medium text-mw-text-primary truncate min-w-0 max-w-[12rem] sm:max-w-xs flex-1 bg-transparent border border-transparent hover:border-mw-border focus:border-mw-primary rounded px-2 py-1 transition-colors focus:outline-none focus:ring-1 focus:ring-mw-primary disabled:opacity-50"
                        />
                    ) : (
                        <span className="text-xs text-mw-text-secondary truncate min-w-0 max-w-[12rem] sm:max-w-xs">
                            {toolbarBoardNameDisplay}
                        </span>
                    )}
                    {canDeleteActiveBoard && activeBoard ? (
                        <BoardDeleteControl
                            boardName={activeBoard.name}
                            variant="toolbar"
                            disabled={busy}
                            onConfirmDelete={() => handleDeleteBoard(activeBoard.id)}
                        />
                    ) : null}
                </div>
                {mainTab === 'simulation' && visibleErrors.length > 0 && (
                    <div className="px-4 py-2 text-xs text-mw-error bg-mw-error-muted border-b border-mw-border shrink-0 space-y-1">
                        {visibleErrors.map(({ key, message, source, creatureId }) => (
                            <div key={key}>
                                <span className="font-semibold uppercase text-[10px] mr-1">
                                    {source === 'brain'
                                        ? 'Brain'
                                        : source === 'fixture'
                                          ? 'Fixture'
                                          : 'Region'}
                                </span>
                                {selectedCreatureId && creatureId === selectedCreatureId ? null : creatureId ? (
                                    <span className="font-mono text-[10px] mr-1">{creatureId.slice(0, 8)}:</span>
                                ) : null}
                                {message}
                            </div>
                        ))}
                        {(() => {
                            const hint = visibleErrors
                                .map(({ message }) => sandboxErrorHintForMessage(message))
                                .find((h): h is string => h != null);
                            return hint ? (
                                <div className="text-mw-text-secondary font-normal">{hint}</div>
                            ) : null;
                        })()}
                    </div>
                )}
                <div className="flex-1 min-h-0 overflow-hidden relative bg-mw-page p-2">
                    <div
                        ref={containerRef}
                        className="absolute inset-2 rounded-lg border border-mw-border overflow-hidden touch-none"
                    />
                    {mainTab === 'simulation' && !envelope ? (
                        <div className="absolute inset-2 z-[5] flex items-center justify-center rounded-lg border border-dashed border-mw-border bg-mw-page/80 text-sm text-mw-text-secondary px-6 text-center">
                            Select a board from the sidebar to start a simulation session.
                        </div>
                    ) : null}
                    <div
                        className="sandbox-board-controls absolute bottom-4 right-4 z-10 flex flex-col overflow-hidden rounded-lg border border-mw-border bg-mw-card shadow-sm"
                        role="toolbar"
                        aria-label="Board zoom controls"
                    >
                        <button
                            type="button"
                            className="sandbox-board-controls-button"
                            aria-label="Zoom in"
                            title="Zoom in"
                            onClick={() => adapterRef.current?.zoomIn()}
                        >
                            <ZoomIn size={16} aria-hidden />
                        </button>
                        <button
                            type="button"
                            className="sandbox-board-controls-button"
                            aria-label="Zoom out"
                            title="Zoom out"
                            onClick={() => adapterRef.current?.zoomOut()}
                        >
                            <ZoomOut size={16} aria-hidden />
                        </button>
                        <button
                            type="button"
                            className="sandbox-board-controls-button"
                            aria-label="Fit board to view"
                            title="Fit to view"
                            onClick={() => adapterRef.current?.fitToView()}
                        >
                            <Maximize2 size={16} aria-hidden />
                        </button>
                    </div>
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
                                                        <div className="mt-3">
                                                            <SandboxCreatureInventorySection
                                                                creature={creature}
                                                                readOnly={mainTab === 'simulation'}
                                                                itemDefinitions={itemDefinitions}
                                                                onBoardChange={
                                                                    mainTab === 'builder'
                                                                        ? updater => {
                                                                              setLocalBoardDef(prev => updater(prev));
                                                                              setBuilderDirty(true);
                                                                          }
                                                                        : undefined
                                                                }
                                                                onAddEntry={
                                                                    mainTab === 'builder'
                                                                        ? type => {
                                                                              setLocalBoardDef(prev =>
                                                                                  addBoardCreatureInventoryEntry(
                                                                                      prev,
                                                                                      creature.id,
                                                                                      type,
                                                                                  ),
                                                                              );
                                                                              setBuilderDirty(true);
                                                                          }
                                                                        : undefined
                                                                }
                                                            />
                                                        </div>
                                                    </InspectorSection>
                                                ))}
                                                {inspectedCellItems.map(it =>
                                                    isRegionItem(it) ? (
                                                        <SandboxRegionInspectorSection
                                                            key={it.id}
                                                            item={it}
                                                            readOnly={mainTab !== 'builder'}
                                                            favoriteColors={sandboxFavoriteColors}
                                                            workflows={workflows}
                                                            workflowProjects={workflowProjects}
                                                            sharedProjectId={sharedProjectId}
                                                            onItemChange={(itemId, patch) => {
                                                                setLocalBoardDef(prev =>
                                                                    updateBoardItemMetadata(prev, itemId, patch),
                                                                );
                                                                setBuilderDirty(true);
                                                            }}
                                                        />
                                                    ) : isFixtureItem(it) ? (
                                                        <SandboxFixtureInspectorSection
                                                            key={it.id}
                                                            item={it}
                                                            definitionContext={inspectorDefinitionContext}
                                                        />
                                                    ) : (
                                                        <SandboxItemInspectorSection
                                                            key={it.id}
                                                            item={it}
                                                            readOnly={mainTab !== 'builder'}
                                                            definitionContext={inspectorDefinitionContext}
                                                            onItemChange={(itemId, patch) => {
                                                                setLocalBoardDef(prev =>
                                                                    updateBoardItemMetadata(prev, itemId, patch),
                                                                );
                                                                setBuilderDirty(true);
                                                            }}
                                                        />
                                                    ),
                                                )}
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
                                                disabled={busy || isActiveSystemBoard}
                                                onChange={e => {
                                                    setBuilderBoardName(e.target.value);
                                                    setBuilderDirty(true);
                                                }}
                                                className="px-2 py-1 rounded border border-mw-border bg-mw-page text-mw-text-primary disabled:opacity-50"
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
                                                value={Number.isFinite(tickRateMsInput) ? tickRateMsInput : ''}
                                                onChange={e => {
                                                    const raw = e.target.value;
                                                    if (raw === '') {
                                                        setTickRateMsInput(NaN);
                                                        return;
                                                    }
                                                    setTickRateMsInput(Number(raw));
                                                }}
                                                onBlur={commitTickRateMsInput}
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') {
                                                        e.currentTarget.blur();
                                                    } else if (e.key === 'Escape') {
                                                        revertTickRateMsInput();
                                                        e.currentTarget.blur();
                                                    }
                                                }}
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
                                {visibleNestedRuns.length > 0 ? (
                                    <div className="space-y-3">
                                        <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">
                                            Triggered workflows
                                        </h3>
                                        {visibleNestedRuns.map(entry => {
                                            const labels = nestedRunNodeLabels(entry.meta);
                                            return (
                                                <div
                                                    key={nestedWorkflowRunKey(entry.meta)}
                                                    className="space-y-2 border border-mw-border rounded-lg p-3 bg-mw-card"
                                                >
                                                    <div className="flex items-center justify-between gap-2">
                                                        <span className="text-xs font-semibold text-mw-text-primary">
                                                            {entry.meta.label}
                                                        </span>
                                                        <span
                                                            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                                                entry.run.status === 'ok'
                                                                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                                                                    : entry.run.status === 'partial'
                                                                      ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                                                                      : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                                                            }`}
                                                        >
                                                            {entry.run.status.toUpperCase()}
                                                        </span>
                                                    </div>
                                                    <WorkflowRunLogsNodeResultsList
                                                        node_results={entry.run.node_results}
                                                        getNodeLabel={id => labels.get(id) ?? id}
                                                        userSettings={
                                                            user?.settings as Record<string, unknown> | undefined
                                                        }
                                                    />
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>
            {userActionPrompt && envelope ? (
                <SandboxUserActionModal
                    creature={userActionPrompt.creatures[userActionPrompt.index]}
                    sandboxState={envelope.sandbox}
                    creatureIndex={userActionPrompt.index}
                    creatureTotal={userActionPrompt.creatures.length}
                    onConfirm={handleUserActionConfirm}
                    onDismiss={handleUserActionDismiss}
                    itemDefinitions={itemDefinitions}
                />
            ) : null}
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
                    sandboxFavoriteColors={sandboxFavoriteColors}
                    itemDefinitions={itemDefinitions}
                    terrainDefinitions={terrainDefinitions}
                    fixtureDefinitions={fixtureDefinitions}
                    regionDefinitions={regionDefinitions}
                    creatureDefinitions={creatureDefinitions}
                    onDismiss={dismissCellActionModal}
                    onComplete={interaction => {
                        void completeCellAction(interaction);
                    }}
                    onInspect={completeCellInspect}
                />
            ) : null}
            {broadcastPromptSegments.length > 0 ? (
                <BroadcastMessageModal
                    segments={broadcastPromptSegments}
                    onContinue={() => setBroadcastPromptSegments([])}
                />
            ) : null}
        </div>
    );
};
