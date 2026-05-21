/**
 * WorkflowEditor
 * ==============
 * Visual DAG editor for WorkflowDefinitions using @xyflow/react.
 *
 * Layout:
 *   Left panel — collapsible sections (width user-resizable; min 256px, max ~50% viewport; center column min 320px). The left column uses a higher z-index than the canvas so the vertical resize strip stays above React Flow hit-testing at the shared edge; the canvas column clips overflow so edges do not steal pointer events.
 *   Below the Tailwind `lg` breakpoint (max-width 1023px), or when **immersive fullscreen** is on (app hides global nav + header), the palette and Explorer become full-height slide-over panels with a dimmed backdrop; the canvas stays full width so pan/pinch zoom remain usable (`workflowEditorOverlayPanels` combining `useCompactViewport` and `App` immersive state). In immersive mode only, **ArrowLeft** / **ArrowRight** and narrow **left/right edge taps** on the canvas (movement threshold) toggle those slide-overs like the toolbar (`workflowEditorImmersivePanelArrow.ts`).
 *     1. Workflows — project list (Shared + user projects), drill-in for non–custom-skill workflows; import/new only inside a project; segmented sort + filter; move-to-project via icon + dropdown per row; exposed defs live under Custom Skills only
 *     2–8. Flow / Primitives / Skills / Utilities / Sandbox Utilities / Controls / Annotation — step tiles from [`WorkflowPaletteStepSections`](./WorkflowPaletteStepSections.tsx) + [`workflowPaletteStepItems.ts`](./workflowPaletteStepItems.ts); per-section filter + max-h scroll (`max-h-[13.5rem]` via `PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS` in [`workflowEditorPanelLayout.ts`](./workflowEditorPanelLayout.ts))
 *   Canvas — React Flow; DAG includes Start/Stop, primitives/utilities/controls, workflow refs, and editor-only annotations (notes/regions). Minimum zoom is {@link WORKFLOW_CANVAS_MIN_ZOOM} in [`FitViewOnWorkflowCanvas`](./FitViewOnWorkflowCanvas.tsx) (React Flow default maxZoom still applies unless changed).
 *   Right panel — Explorer (node/edge/workflow metadata) and Run Logs (resizable when a workflow is open; min 320px; persistence optional)
 *   Bottom — run output drawer (opens on Run)
 *
 * Panel widths can be remembered per workflow in localStorage when `workflow_editor_remember_panel_widths` is
 * enabled in My Settings → View Settings (default on).
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    ReactFlow, Background, Controls,
    addEdge, applyEdgeChanges, applyNodeChanges, MarkerType, ConnectionMode,
    type Node, type Edge, type Connection, type NodeChange, type EdgeChange,
    type OnConnect,
    type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { ApiClient } from '../../api/client';
import { getApiErrorDetailObject } from '../../api/http';
import { useAuth } from '../../contexts/AuthContext';
import { useCopyWithFeedback, useStatusToast } from '../../contexts/ClipboardFeedbackContext';
import {
    PersonaListItem,
    Palette,
    DocumentListItem,
    Structure,
    WorkflowDefinition,
    WorkflowDefinitionListItem,
    WorkflowDefinitionListItemHydrated,
    WorkflowDefinitionCreate,
    WorkflowProject,
    WorkflowRunResult,
    NodeRunResult,
    GraphNode as AppGraphNode,
    GraphEdge as AppGraphEdge,
    RequiredInput,
    RequiredOutput,
    TtsModelRead,
    AudioFileArtifactRead,
    TranscriptionProviderItem,
    VoiceSampleListItem,
    WorkflowGraph,
    WorkflowExecutionLimitsEnvelope,
    WorkflowExecutionLimitsOverrides,
} from '../../api/types';
import {
    Plus,
    Play,
    Save,
    CheckCircle2,
    XCircle,
    Loader2,
    Mic,
    Trash2,
    ChevronDown,
    ChevronRight,
    ChevronLeft,
    Download,
    Upload,
    Copy,
    FolderPlus,
    PanelLeft,
    PanelRight,
    Maximize2,
    Minimize2,
    Ban,
} from 'lucide-react';

import { UserAvatar } from '../UserAvatar';
import { ContextHelpModal } from '../ContextHelpModal';
import { GmailQueryHelpContent } from './gmailQueryHelpContent';
import { GmailInboxCategoriesHelpContent } from './gmailInboxCategoriesHelpContent';
import { GmailListCategoryFields } from './GmailListCategoryFields';
import { GmailBoundaryDateFields } from './GmailBoundaryDateFields';
import { CalendarWindowDateTimeFields } from './CalendarWindowDateTimeFields';
import { SingleDateTimeField } from './SingleDateTimeField';
import { INSPECTOR_SURFACE_CLASS, InspectorSection } from './InspectorSection';
import { TtsBridgeOptionsTextarea } from './TtsBridgeOptionsTextarea';
import { applyForLoopEndClearOnEdgeRemoved, pairForLoopEndOnConnect } from './forLoopEndPairing';
import { JsonTreeView } from './JsonTreeView';
import { lastRunInputsPayload } from './lastRunInputsPayload';
import {
    draftValueToOverride,
    initialWizardDraftForStep,
    isValidRunWizardDraft,
    missingStartInputsForRun,
    normalizeStartInputsForRun,
    parseRunWizardAnyJson,
    parseRunWizardListOrDictJson,
} from './startRunInputHelpers';
import { nextUniqueStartSlotKey, validateStartSlotKey } from './startSlotKeyHelpers';
import { RunInputsExplorer } from './RunInputsExplorer';
import { EdgeInspectorPanel } from './EdgeInspectorPanel';
import { WorkflowExplorerWorkflowMetadata } from './WorkflowExplorerWorkflowMetadata';
import { WorkflowRunLogsNodeResultsList } from './WorkflowRunLogsNodeResultsList';
import { WorkflowNodeRunOutputBody } from './WorkflowNodeRunOutputBody';
import { isWorkflowInspectorOpen } from './workflowInspectorVisibility';
import { WorkflowImportModal } from './WorkflowImportModal';
import { OutputOverrideModal } from './OutputOverrideModal';
import {
    bundleImportExistingNames,
    executeWorkflowBundleImport,
} from '../../domain/executeWorkflowBundleImport';
import {
    assembleWorkflowBundleExport,
    planBundleImport,
    serializeWorkflowBundleExport,
    slugifyWorkflowBundleExportBasename,
    WorkflowBundleExportError,
    type WorkflowBundleExportDocument,
} from '../../domain/workflowBundleImportExport';
import {
    collectWorkflowRefIds,
    WorkflowImportError,
} from '../../domain/workflowImportExport';
import { isDeletableProject, workflowsInProject } from '../../domain/workflowProjectMembership';
import { resolveTtsPlaybackWhen, type TtsPlaybackWhen } from '../../domain/resolveAutoPlayTtsOnNodeEnd';
import { sortTtsQueuedClips, type TtsQueuedClip } from '../../domain/ttsPlaybackQueue';
import { isPlayableTtsAudioOutput, mergeLastRunNodeResult } from '../../domain/ttsPlayableOutput';
import { playTtsAudioFromBase64 } from '../../domain/ttsAudioPlayback';
import { unionLoopBodyNodeIds } from '../../domain/workflowLoopBodyNodeIds';
import { mergeWorkflowDefinitionIntoList, workflowListEntryHasGraph } from '../../domain/workflowDefinitionListMerge';
import {
    DEFAULT_PALETTE_COLORS,
    EDITOR_NODE_PALETTE_EXTRA,
    isBuiltinDefaultSystemPalette,
    normalizeWorkflowPaletteColors,
    resolveFallbackWorkflowPalette,
    resolveWorkflowPaletteColor,
    sortWorkflowPalettesForDisplay,
} from '../../domain/paletteDefaults';
import { DEFAULT_SANDBOX_DECISION_ACTION, SANDBOX_DECISION_ACTIONS } from '../../domain/sandbox/decisionActions';
import { getHandleColor } from './constants';
import {
    FitViewOnWorkflowCanvasKey,
    FitViewOnWorkflowCanvasResize,
    WORKFLOW_CANVAS_MIN_ZOOM,
} from './FitViewOnWorkflowCanvas';
import { nodeTypes } from './nodeTypes';
import { normalizeAnnotationTextAlign } from './annotationTextAlign';
import { AnnotationStackOrderControls } from './AnnotationStackOrderControls';
import {
    genId,
    appNodeToFlow,
    getSourceOutputType,
    appEdgeToFlow,
    flowNodeToApp,
    flowEdgeToApp,
    resolveWorkflowRefLabels,
    isAnnotationFlowNodeType,
    showInspectorLastRunExplorerSection,
    ANNOTATION_NOTE_DEFAULT_WIDTH,
    ANNOTATION_NOTE_DEFAULT_HEIGHT,
    ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
    ANNOTATION_NOTE_Z_INDEX_MAX,
    ANNOTATION_NOTE_Z_INDEX_MIN,
    clampAnnotationNoteZIndex,
    ANNOTATION_REGION_Z_INDEX_MAX,
    ANNOTATION_REGION_Z_INDEX_MIN,
    clampAnnotationRegionZIndex,
    normalizeUpsertDocumentRequiredInputs,
} from './graphConverters';
import { isValidWorkflowConnection } from './workflowConnectionRules';
import { resolveWorkflowTimeZone } from '../../domain/gmailRfc3339Date';
import { normalizeText, stripCommonJsonWrappers } from '../../domain/normalizeText';
import {
    CENTER_PANEL_MIN_PX,
    clampPanelWidths,
    DEFAULT_LEFT_PANEL_WIDTH_PX,
    DEFAULT_RIGHT_PANEL_WIDTH_PX,
    PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS,
    workflowEditorOverlayPanels,
} from './workflowEditorPanelLayout';
import { shouldOpenCompactExplorerForInspectorSignals } from './workflowEditorOverlayExplorer';
import { filterNamesByPrefix } from './workflowListFilter';
import { readPanelWidthsForWorkflow, writePanelWidthsForWorkflow } from './workflowEditorPanelWidthsStorage';
import { normalizeGmailInboxFocus } from '../../domain/gmailCategoryFilters';
import { enrichNodesForCanvasFlow, styleEdgesForCanvas } from './workflowCanvasEnrichment';
import { partitionCanvasSelection } from './workflowCanvasSelection';
import {
    eventTargetIsTextEntry,
    isKeyboardDeleteIntentKey,
    planCanvasNodeDeletion,
} from './workflowCanvasDeletePlanning';
import {
    IMMERSIVE_PANEL_EDGE_TAP_MOVE_THRESHOLD_PX,
    immersivePanelArrowShortcutResult,
    immersivePanelEdgeTapResult,
} from './workflowEditorImmersivePanelArrow';
import { createWorkflowGraphHistory } from './workflowGraphHistory';
import {
    reactFlowEdgeChangesSkipUndoRecord,
    reactFlowNodeChangesSkipUndoRecord,
    WorkflowGraphUndoContext,
    type WorkflowCanvasInteractionFlags,
} from './workflowGraphUndoContext';
import { WorkflowPaletteStepSections } from './WorkflowPaletteStepSections';
import { WorkflowPaletteWorkflowRow } from './WorkflowPaletteWorkflowRow';
import { WorkflowProjectDeleteControl } from './WorkflowProjectDeleteControl';
import { paletteDisplayNameForReactFlowType } from './workflowPaletteStepItems';
import { useCompactViewport } from '../../hooks/useCompactViewport';

interface Props {
    setUnsavedChanges?: (v: boolean) => void;
    requestSave?: number;
    onSaved?: () => void;
    /** Increment when Palettes modal closes so we refetch palette list (colors may have changed). */
    palettesRefreshKey?: number;
    /** App shell immersive fullscreen: hides global nav/header; palette/Explorer use slide-overs. */
    immersive?: boolean;
    onImmersiveChange?: (immersive: boolean) => void;
    /** Open My Settings (toolbar affordance while app header is hidden in immersive mode). */
    onOpenMySettings?: () => void;
    /** Workflow id from the shell URL (`/workflows/:id`), if any. */
    routeWorkflowId?: string | null;
    /** Keep the browser URL in sync when the opened workflow changes (replaceState). */
    onSyncWorkflowPath?: (workflowId: string | null) => void;
}

function nonEmptyWorkflowExecutionLimits(
    raw: WorkflowExecutionLimitsOverrides | null | undefined,
): WorkflowExecutionLimitsOverrides | undefined {
    if (raw == null || typeof raw !== 'object') return undefined;
    const out: WorkflowExecutionLimitsOverrides = {};
    for (const key of ['workflow_ttl_seconds', 'max_node_executions', 'max_loop_iterations', 'max_nested_depth'] as const) {
        const v = raw[key];
        if (typeof v === 'number' && Number.isFinite(v)) {
            const n = Math.floor(v);
            if (n >= 1) out[key] = n;
        }
    }
    return Object.keys(out).length > 0 ? out : undefined;
}

/** Compare persisted graph.execution_limits drafts (undefined = absent vs explicit null clears). */
function stableGraphLimitsSnapshot(raw: WorkflowExecutionLimitsOverrides | null | undefined): string {
    if (raw === undefined) return '__absent__';
    return JSON.stringify(raw === null ? null : nonEmptyWorkflowExecutionLimits(raw) ?? null);
}

/** Resolved #rrggbb for `<input type="color">` when the stored value is a palette key or empty. */
function resolvedHexForAnnotationAccent(
    palette: Record<string, string>,
    colorText: string,
    defaultPaletteKey: 'annotation_note' | 'annotation_region',
): string {
    const t = colorText.trim();
    if (/^#[0-9A-Fa-f]{6}$/.test(t)) return t.toLowerCase();
    const key = t !== '' ? t : defaultPaletteKey;
    const hex = resolveWorkflowPaletteColor(palette, key);
    return /^#[0-9A-Fa-f]{6}$/.test(hex) ? hex.toLowerCase() : '#64748b';
}

function FetchUrlHeadersTextarea({
    headers,
    onCommit,
    onFocusBeforeEdit,
}: {
    headers: Record<string, string> | undefined;
    onCommit: (h: Record<string, string>) => void;
    onFocusBeforeEdit: () => void;
}): React.ReactElement {
    const serialized = (() => {
        const h = headers;
        if (h && typeof h === 'object' && !Array.isArray(h)) {
            try {
                return JSON.stringify(h, null, 2);
            } catch {
                return '{}';
            }
        }
        return '{}';
    })();
    const [text, setText] = useState(serialized);
    useEffect(() => {
        setText(serialized);
    }, [serialized]);
    return (
        <textarea
            value={text}
            onFocus={onFocusBeforeEdit}
            onChange={e => setText(e.target.value)}
            onBlur={() => {
                const raw = text;
                try {
                    const parsed = JSON.parse(raw) as unknown;
                    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                        const flat: Record<string, string> = {};
                        for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
                            flat[k] = v == null ? '' : String(v);
                        }
                        onCommit(flat);
                    } else {
                        onCommit({});
                    }
                } catch {
                    onCommit({});
                }
            }}
            rows={4}
            className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card rounded-lg"
        />
    );
}

export const WorkflowEditor: React.FC<Props> = ({
    setUnsavedChanges,
    requestSave,
    onSaved,
    palettesRefreshKey = 0,
    immersive = false,
    onImmersiveChange,
    onOpenMySettings,
    routeWorkflowId = null,
    onSyncWorkflowPath,
}) => {
    const { user } = useAuth();
    // Data
    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItemHydrated[]>([]);
    const [activeWf, setActiveWf] = useState<WorkflowDefinition | null>(null);
    const [lastSavedWf, setLastSavedWf] = useState<WorkflowDefinition | null>(null);
    const customSkillWorkflows = useMemo(
        () => workflows.filter(w => Boolean(w.expose_as_custom_skill)),
        [workflows],
    );
    const [personas, setPersonas] = useState<PersonaListItem[]>([]);
    const [palettes, setPalettes] = useState<Palette[]>([]);
    /** Server `GET /palettes/resolve` for workflow + user; defensive fallback when null/unavailable. */
    const [serverResolvedWorkflowPalette, setServerResolvedWorkflowPalette] = useState<Palette | null>(null);
    const [structures, setStructures] = useState<Structure[]>([]);
    const [documents, setDocuments] = useState<DocumentListItem[]>([]);
    const [ttsModelsReady, setTtsModelsReady] = useState<TtsModelRead[]>([]);
    const [voiceSamplesList, setVoiceSamplesList] = useState<VoiceSampleListItem[]>([]);
    const [audioFileArtifacts, setAudioFileArtifacts] = useState<AudioFileArtifactRead[]>([]);

    // Canvas state
    const [nodes, setNodes] = useState<Node[]>([]);
    const stopNodeCount = useMemo(() => nodes.filter(n => n.type === 'stop').length, [nodes]);
    const { selectedCanvasNodes, explorerTargetNode: selectedNode, multiCanvasSelectActive } = useMemo(
        () => partitionCanvasSelection(nodes),
        [nodes],
    );
    const [edges, setEdges] = useState<Edge[]>([]);
    const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);

    const graphHistoryRef = useRef(createWorkflowGraphHistory());
    const isApplyingGraphHistoryRef = useRef(false);
    const workflowCanvasInteractionRef = useRef<WorkflowCanvasInteractionFlags>({
        nodeDrag: false,
        nodeResize: false,
    });
    const nodesForUndoRef = useRef<Node[]>([]);
    const edgesForUndoRef = useRef<Edge[]>([]);
    /** Clips to play in order after `workflow.completed` (SSE) when status is ok (`after_workflow` mode). */
    const ttsAfterWorkflowQueueRef = useRef<TtsQueuedClip[]>([]);
    /** Serializes all programmatic TTS autoplay (`inline` + end-of-run queue) so clips never overlap. */
    const ttsAutoplayChainRef = useRef(Promise.resolve());
    const transcribeMediaRecorderRef = useRef<MediaRecorder | null>(null);
    const transcribeMediaStreamRef = useRef<MediaStream | null>(null);
    const transcribeChunksRef = useRef<Blob[]>([]);
    const imagePrimitiveFileInputRef = useRef<HTMLInputElement | null>(null);

    // UI state
    const [runResult, setRunResult] = useState<WorkflowRunResult | null>(null);
    const [isRunning, setIsRunning] = useState(false);
    const [runningNodeIds, setRunningNodeIds] = useState(() => new Set<string>());
    const [isSaving, setIsSaving] = useState(false);
    /** Shown when Save fails (e.g. API error); cleared on success or when switching workflows. */
    const [saveError, setSaveError] = useState<string | null>(null);
    type PendingNodeDelete = { ids: string[]; skippedStart: boolean };
    const [pendingNodeDelete, setPendingNodeDelete] = useState<PendingNodeDelete | null>(null);
    const [nodeDeleteKeyboardMessage, setNodeDeleteKeyboardMessage] = useState<string | null>(null);
    const [deletingEdgeId, setDeletingEdgeId] = useState<string | null>(null);
    const [deletingWfId, setDeletingWfId] = useState<string | null>(null);
    const [inspectorTab, setInspectorTab] = useState<'node' | 'logs'>('node');

    // Last run: keyed by node_id -> NodeRunResult, cleared on new run or explicit clear.
    const [lastRunNodeData, setLastRunNodeData] = useState<Record<string, NodeRunResult>>({});
    const [lastRunId, setLastRunId] = useState<string | null>(null);
    const [isLastRunOpen, setIsLastRunOpen] = useState(false);
    /** Session-only forced outputs per node id (sent as output_overrides on run). */
    const [outputOverrides, setOutputOverrides] = useState<Record<string, unknown>>({});
    const [outputOverrideModalOpen, setOutputOverrideModalOpen] = useState(false);

    const [isDirty, setIsDirty] = useState(false);
    const [isDataLoading, setIsDataLoading] = useState(true);

    const [isWorkflowsOpen, setIsWorkflowsOpen] = useState(true);
    const [workflowProjects, setWorkflowProjects] = useState<WorkflowProject[]>([]);
    /** When non-null, left panel lists workflows inside that project; when null, lists projects. */
    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
    const [workflowNameFilter, setWorkflowNameFilter] = useState('');
    /** Sort workflows inside the selected project (drill-in only). */
    const [workflowListSort, setWorkflowListSort] = useState<'name' | 'updated'>('updated');
    /** When set, workflow list row shows project move `<select>` for that workflow id. */
    const [moveProjectPickerFor, setMoveProjectPickerFor] = useState<string | null>(null);
    const [newProjectNameDraft, setNewProjectNameDraft] = useState('');
    const [isPrimitivesOpen, setIsPrimitivesOpen] = useState(false);
    const [isSkillsOpen, setIsSkillsOpen] = useState(false);
    const [isUtilitiesOpen, setIsUtilitiesOpen] = useState(false);
    const [isSandboxUtilitiesOpen, setIsSandboxUtilitiesOpen] = useState(false);
    const [isControlsOpen, setIsControlsOpen] = useState(false);
    const [isAnnotationsOpen, setIsAnnotationsOpen] = useState(false);
    const [isFlowOpen, setIsFlowOpen] = useState(false);
    const [isCustomSkillsOpen, setIsCustomSkillsOpen] = useState(false);

    const [workflowImportModalOpen, setWorkflowImportModalOpen] = useState(false);
    const [workflowImportNotice, setWorkflowImportNotice] = useState<string | null>(null);
    const [bundleExportBusy, setBundleExportBusy] = useState(false);
    const copyWithFeedback = useCopyWithFeedback();
    const showStatusToast = useStatusToast();

    type RunInputWizardState = { queue: RequiredInput[]; index: number; overrides: Record<string, unknown> };
    const [runInputWizard, setRunInputWizard] = useState<RunInputWizardState | null>(null);
    const [runWizardStepDraft, setRunWizardStepDraft] = useState<unknown>(null);
    /** Raw textarea text for list/dictionary wizard steps (controlled); parsed on Continue/Run. */
    const [runWizardListDictRaw, setRunWizardListDictRaw] = useState('');
    const [runWizardJsonNormalizeError, setRunWizardJsonNormalizeError] = useState('');

    type TranscribeCaptureState = {
        runId: string;
        nodeId: string;
        forLoopId: string | null;
        forLoopIteration: number;
    };
    const [transcribeCapture, setTranscribeCapture] = useState<TranscribeCaptureState | null>(null);
    const [transcribeUi, setTranscribeUi] = useState<'idle' | 'recording' | 'uploading' | 'error'>('idle');
    const [transcribeError, setTranscribeError] = useState<string | null>(null);
    const [audioFileInputCapture, setAudioFileInputCapture] = useState<TranscribeCaptureState | null>(null);
    const [audioFileInputUploading, setAudioFileInputUploading] = useState(false);
    const [audioFileInputError, setAudioFileInputError] = useState<string | null>(null);
    const [transcribeFileCapture, setTranscribeFileCapture] = useState<TranscribeCaptureState | null>(null);
    const [transcribeFileUploading, setTranscribeFileUploading] = useState(false);
    const [transcribeFileError, setTranscribeFileError] = useState<string | null>(null);
    const [transcriptionProviders, setTranscriptionProviders] = useState<TranscriptionProviderItem[]>([]);
    const workflowRunAbortRef = useRef<AbortController | null>(null);
    const workflowStreamSeqRef = useRef(0);
    const [workflowExecutionEnvelope, setWorkflowExecutionEnvelope] =
        useState<WorkflowExecutionLimitsEnvelope | null>(null);
    const [runExecutionLimitsOverrides, setRunExecutionLimitsOverrides] = useState<WorkflowExecutionLimitsOverrides>(
        {},
    );

    /** Local JSON text for list/dictionary primitives so paste + Normalize work before valid parse. */
    const [listPrimitiveEditorJson, setListPrimitiveEditorJson] = useState('');
    const [dictPrimitiveEditorJson, setDictPrimitiveEditorJson] = useState('');
    const [listPrimitiveNormalizeError, setListPrimitiveNormalizeError] = useState('');
    const [dictPrimitiveNormalizeError, setDictPrimitiveNormalizeError] = useState('');

    /** Per-slot JSON text for Start list/dictionary rows (key = slot index). */
    const [startListDictEditorJson, setStartListDictEditorJson] = useState<Record<number, string>>({});
    const [startListDictNormalizeError, setStartListDictNormalizeError] = useState<Record<number, string>>({});
    const [startSlotKeyError, setStartSlotKeyError] = useState<Record<number, string>>({});

    useEffect(() => {
        nodesForUndoRef.current = nodes;
        edgesForUndoRef.current = edges;
    }, [nodes, edges]);

    const recordGraphBeforeMutation = useCallback(() => {
        if (isApplyingGraphHistoryRef.current) return;
        graphHistoryRef.current.pushSnapshot(nodesForUndoRef.current, edgesForUndoRef.current);
    }, []);

    const applyGraphHistorySnapshot = useCallback((snap: { nodes: Node[]; edges: Edge[] }) => {
        isApplyingGraphHistoryRef.current = true;
        try {
            setNodes(snap.nodes);
            setEdges(snap.edges);
            setSelectedEdge(se => (se && snap.edges.some(e => e.id === se.id) ? se : null));
            setPendingNodeDelete(null);
            setDeletingEdgeId(null);
            setNodeDeleteKeyboardMessage(null);
        } finally {
            isApplyingGraphHistoryRef.current = false;
        }
    }, []);

    const undoGraph = useCallback(() => {
        if (!graphHistoryRef.current.canUndo()) return false;
        const snap = graphHistoryRef.current.undo(nodesForUndoRef.current, edgesForUndoRef.current);
        if (!snap) return false;
        applyGraphHistorySnapshot(snap);
        return true;
    }, [applyGraphHistorySnapshot]);

    const redoGraph = useCallback(() => {
        if (!graphHistoryRef.current.canRedo()) return false;
        const snap = graphHistoryRef.current.redo(nodesForUndoRef.current, edgesForUndoRef.current);
        if (!snap) return false;
        applyGraphHistorySnapshot(snap);
        return true;
    }, [applyGraphHistorySnapshot]);

    const workflowGraphUndoContextValue = useMemo(
        () => ({
            recordBeforeGraphMutation: recordGraphBeforeMutation,
            interactionRef: workflowCanvasInteractionRef,
        }),
        [recordGraphBeforeMutation],
    );

    useEffect(() => {
        if (selectedNode?.type === 'listPrimitive') {
            setListPrimitiveEditorJson(JSON.stringify((selectedNode.data as any).data ?? [], null, 2));
            setListPrimitiveNormalizeError('');
        }
    }, [selectedNode?.id, selectedNode?.type, JSON.stringify((selectedNode?.data as any)?.data)]);

    useEffect(() => {
        if (selectedNode?.type === 'dictionaryPrimitive') {
            setDictPrimitiveEditorJson(JSON.stringify((selectedNode.data as any).data ?? {}, null, 2));
            setDictPrimitiveNormalizeError('');
        }
    }, [selectedNode?.id, selectedNode?.type, JSON.stringify((selectedNode?.data as any)?.data)]);

    const startRequiredInputsSig =
        selectedNode?.type === 'start'
            ? JSON.stringify((selectedNode.data as any)?.required_inputs ?? [])
            : '';

    useEffect(() => {
        if (selectedNode?.type !== 'start') {
            setStartListDictEditorJson({});
            setStartListDictNormalizeError({});
            return;
        }
        const raw = (selectedNode.data as any).required_inputs ?? [];
        const m: Record<number, string> = {};
        raw.forEach((inp: RequiredInput, idx: number) => {
            if (inp.type === 'list') {
                m[idx] =
                    inp.value == null
                        ? ''
                        : Array.isArray(inp.value)
                          ? JSON.stringify(inp.value, null, 2)
                          : '';
            } else if (inp.type === 'dictionary') {
                m[idx] =
                    inp.value == null
                        ? ''
                        : typeof inp.value === 'object' && !Array.isArray(inp.value)
                          ? JSON.stringify(inp.value, null, 2)
                          : '';
            } else if (inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure') {
                m[idx] = inp.value == null ? '' : JSON.stringify(inp.value, null, 2);
            }
        });
        setStartListDictEditorJson(m);
        setStartListDictNormalizeError({});
    }, [selectedNode?.id, startRequiredInputsSig]);

    useEffect(() => {
        if (selectedNode?.type !== 'start') {
            setStartSlotKeyError({});
        }
    }, [selectedNode?.id, selectedNode?.type]);

    useEffect(() => {
        if (!runInputWizard) return;
        const inp = runInputWizard.queue[runInputWizard.index];
        if (inp.type === 'list' || inp.type === 'dictionary') {
            const init = initialWizardDraftForStep(inp, runInputWizard.overrides);
            if (
                init != null &&
                ((inp.type === 'list' && Array.isArray(init)) ||
                    (inp.type === 'dictionary' &&
                        typeof init === 'object' &&
                        !Array.isArray(init)))
            ) {
                setRunWizardListDictRaw(JSON.stringify(init, null, 2));
            } else {
                setRunWizardListDictRaw('');
            }
            setRunWizardStepDraft(null);
        } else if (inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure') {
            const init = initialWizardDraftForStep(inp, runInputWizard.overrides);
            if (Object.prototype.hasOwnProperty.call(runInputWizard.overrides, inp.key)) {
                setRunWizardListDictRaw(JSON.stringify(init, null, 2));
            } else {
                setRunWizardListDictRaw('');
            }
            setRunWizardStepDraft(null);
        } else {
            setRunWizardListDictRaw('');
            setRunWizardStepDraft(initialWizardDraftForStep(inp, runInputWizard.overrides));
        }
        setRunWizardJsonNormalizeError('');
    }, [runInputWizard]);

    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const immersiveEdgeTapTrackingRef = useRef<{
        edge: 'left' | 'right';
        x: number;
        y: number;
        pointerId: number;
    } | null>(null);
    const reactFlowInstanceRef = useRef<ReactFlowInstance | null>(null);
    useEffect(() => () => {
        reactFlowInstanceRef.current = null;
    }, []);

    const inspectorOpen = isWorkflowInspectorOpen(activeWf);
    const compactViewport = useCompactViewport();
    const overlayPanels = workflowEditorOverlayPanels(compactViewport, immersive);
    const [compactPaletteOpen, setCompactPaletteOpen] = useState(false);
    const [compactExplorerOpen, setCompactExplorerOpen] = useState(false);

    useEffect(() => {
        if (!overlayPanels) {
            setCompactPaletteOpen(false);
            setCompactExplorerOpen(false);
        }
    }, [overlayPanels]);

    useEffect(() => {
        if (!inspectorOpen) setCompactExplorerOpen(false);
    }, [inspectorOpen]);

    useEffect(() => {
        if (
            !shouldOpenCompactExplorerForInspectorSignals({
                overlayPanels,
                inspectorOpen,
                hasPendingNodeDelete: pendingNodeDelete != null,
                hasPendingEdgeDelete: deletingEdgeId != null,
                hasNodeDeleteKeyboardMessage: nodeDeleteKeyboardMessage != null,
            })
        ) {
            return;
        }
        setCompactPaletteOpen(false);
        setCompactExplorerOpen(true);
    }, [
        overlayPanels,
        inspectorOpen,
        pendingNodeDelete,
        deletingEdgeId,
        nodeDeleteKeyboardMessage,
        compactExplorerOpen,
    ]);

    const rememberWorkflowPanelWidths = user?.settings?.workflow_editor_remember_panel_widths !== false;

    const [panelWidths, setPanelWidths] = useState(() => ({
        left: DEFAULT_LEFT_PANEL_WIDTH_PX,
        right: DEFAULT_RIGHT_PANEL_WIDTH_PX,
    }));

    const leftResizeDragRef = useRef<{ pointerId: number; startX: number; startW: number } | null>(null);
    const rightResizeDragRef = useRef<{ pointerId: number; startX: number; startW: number } | null>(null);
    const prevInspectorOpenRef = useRef<boolean | null>(null);
    const panelWidthsRef = useRef(panelWidths);
    panelWidthsRef.current = panelWidths;
    const workflowPrefetchInFlightRef = useRef<Set<string>>(new Set());
    /** Scroll target for inline node-delete confirmation (keyboard or Remove Node). */
    const nodeDeleteConfirmRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!activeWf?.id) return;
        const remember = user?.settings?.workflow_editor_remember_panel_widths !== false;
        const w = typeof window !== 'undefined' ? window.innerWidth : 1200;
        if (remember) {
            const stored = readPanelWidthsForWorkflow(activeWf.id);
            if (stored) {
                setPanelWidths(clampPanelWidths(w, stored.left, stored.right, inspectorOpen));
            } else {
                setPanelWidths(
                    clampPanelWidths(w, DEFAULT_LEFT_PANEL_WIDTH_PX, DEFAULT_RIGHT_PANEL_WIDTH_PX, inspectorOpen),
                );
            }
        } else {
            setPanelWidths(
                clampPanelWidths(w, DEFAULT_LEFT_PANEL_WIDTH_PX, DEFAULT_RIGHT_PANEL_WIDTH_PX, inspectorOpen),
            );
        }
        // Intentionally only when the active workflow id changes — toggling “remember widths” must not reset mid-session.
    }, [activeWf?.id]);

    useEffect(() => {
        if (prevInspectorOpenRef.current === inspectorOpen) return;
        prevInspectorOpenRef.current = inspectorOpen;
        setPanelWidths(p => clampPanelWidths(window.innerWidth, p.left, p.right, inspectorOpen));
    }, [inspectorOpen]);

    useEffect(() => {
        const onResize = () => {
            const w = window.innerWidth;
            setPanelWidths(prev => {
                const c = clampPanelWidths(w, prev.left, prev.right, inspectorOpen);
                if (
                    rememberWorkflowPanelWidths &&
                    activeWf?.id &&
                    (c.left !== prev.left || c.right !== prev.right)
                ) {
                    writePanelWidthsForWorkflow(activeWf.id, c.left, c.right);
                }
                return c;
            });
        };
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, [inspectorOpen, rememberWorkflowPanelWidths, activeWf?.id]);

    const persistPanelWidthsFromState = useCallback(
        (left: number, right: number) => {
            if (!rememberWorkflowPanelWidths || !activeWf?.id) return;
            writePanelWidthsForWorkflow(activeWf.id, left, right);
        },
        [rememberWorkflowPanelWidths, activeWf?.id],
    );

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
        setPanelWidths(p =>
            clampPanelWidths(window.innerWidth, nextLeft, p.right, inspectorOpen),
        );
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
            persistPanelWidthsFromState(p.left, p.right);
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
        setPanelWidths(p =>
            clampPanelWidths(window.innerWidth, p.left, nextRight, inspectorOpen),
        );
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
            persistPanelWidthsFromState(p.left, p.right);
            return p;
        });
    };

    // ------------------------------------------------------------------
    const loadAll = async () => {
        const [wfs, projs, ps, pals, structs, docs, tts, vs, audioFiles, transcriptionProvs] = await Promise.all([
            ApiClient.getWorkflows(),
            ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]),
            ApiClient.getPersonas(),
            ApiClient.getPalettes(),
            ApiClient.getStructures().catch(() => []),
            ApiClient.getDocuments().catch(() => []),
            ApiClient.getTtsModelsReady().catch(() => [] as TtsModelRead[]),
            ApiClient.getVoiceSamples().catch(() => [] as VoiceSampleListItem[]),
            ApiClient.getAudioFileArtifacts().catch(() => [] as AudioFileArtifactRead[]),
            ApiClient.getTranscriptionProviders().catch(() => [] as TranscriptionProviderItem[]),
        ]);
        setWorkflows(wfs);
        setWorkflowProjects(projs);
        setPersonas(ps);
        setPalettes(pals);
        setStructures(structs);
        setDocuments(docs);
        setTtsModelsReady(tts);
        setVoiceSamplesList(vs);
        setAudioFileArtifacts(audioFiles);
        setTranscriptionProviders(transcriptionProvs);
    };
    const refreshWorkflowLists = async () => {
        const [wfs, projs] = await Promise.all([
            ApiClient.getWorkflows(),
            ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]),
        ]);
        setWorkflows(wfs);
        setWorkflowProjects(projs);
    };
    useEffect(() => { loadAll().finally(() => setIsDataLoading(false)); }, []);

    useEffect(() => {
        void ApiClient.getWorkflowExecutionLimits()
            .then(envelope => setWorkflowExecutionEnvelope(envelope))
            .catch(() => setWorkflowExecutionEnvelope(null));
    }, []);

    useEffect(() => {
        setRunExecutionLimitsOverrides({});
    }, [activeWf?.id]);

    useEffect(() => {
        if (!workflowImportNotice) return;
        const t = window.setTimeout(() => setWorkflowImportNotice(null), 12000);
        return () => clearTimeout(t);
    }, [workflowImportNotice]);

    useEffect(() => {
        if (palettesRefreshKey <= 0) return;
        void ApiClient.getPalettes().then(setPalettes);
    }, [palettesRefreshKey]);

    useEffect(() => {
        if (!user) {
            setServerResolvedWorkflowPalette(null);
            return;
        }
        let cancelled = false;
        const wid = activeWf?.id ?? null;
        void ApiClient.resolveWorkflowPalette(wid)
            .then(p => {
                if (!cancelled) setServerResolvedWorkflowPalette(p);
            })
            .catch(() => {
                if (!cancelled) setServerResolvedWorkflowPalette(null);
            });
        return () => {
            cancelled = true;
        };
    }, [user, activeWf?.id, user?.settings?.preferred_editor_palette_id, palettesRefreshKey]);

    const sortedPalettes = React.useMemo(() => sortWorkflowPalettesForDisplay(palettes), [palettes]);

    /** System "Default" preset id (same as unset palette_id). Shown only as the empty option, not twice. */
    const builtinDefaultPaletteId = React.useMemo(() => {
        const p = palettes.find(x => isBuiltinDefaultSystemPalette(x));
        return p?.id ?? null;
    }, [palettes]);

    const paletteOptionsForToolbar = React.useMemo(
        () => sortedPalettes.filter(p => !isBuiltinDefaultSystemPalette(p)),
        [sortedPalettes],
    );

    const toolbarPaletteSelectValue = React.useMemo(() => {
        const pid = activeWf?.palette_id ?? null;
        if (!pid) return '';
        if (builtinDefaultPaletteId != null && pid === builtinDefaultPaletteId) return '';
        return pid;
    }, [activeWf?.palette_id, builtinDefaultPaletteId]);

    const activePalette = React.useMemo(() => {
        if (activeWf?.palette_id) {
            const localPick = palettes.find(p => p.id === activeWf.palette_id);
            if (localPick) return localPick;
            return serverResolvedWorkflowPalette ?? resolveFallbackWorkflowPalette(palettes);
        }
        return serverResolvedWorkflowPalette ?? resolveFallbackWorkflowPalette(palettes);
    }, [activeWf?.palette_id, palettes, serverResolvedWorkflowPalette]);

    const paletteColors = React.useMemo(() => {
        if (!activePalette) {
            return DEFAULT_PALETTE_COLORS;
        }
        const ecs = activePalette.effective_colors;
        if (ecs && Object.keys(ecs).length > 0) {
            return { ...EDITOR_NODE_PALETTE_EXTRA, ...ecs };
        }
        if (!activePalette.colors) {
            return DEFAULT_PALETTE_COLORS;
        }
        return normalizeWorkflowPaletteColors(activePalette.colors);
    }, [activePalette]);

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

    /** Project drill-in list: exposed-as-custom-skill defs appear only under Custom Skills. */
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
            // Last updated desc, then id asc (matches API list_workflows ordering for ties).
            list = [...list].sort((a, b) => {
                const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                if (tb !== ta) return tb - ta;
                return a.id.localeCompare(b.id);
            });
        }
        return list;
    }, [workflowsInProjectDrillIn, workflowNameFilter, workflowListSort]);

    useEffect(() => {
        setMoveProjectPickerFor(null);
    }, [selectedProjectId]);

    const workflowCountForProject = (p: WorkflowProject) => {
        const inProject =
            sharedProjectId && p.id === sharedProjectId
                ? workflows.filter(w => w.project_id === p.id || w.project_id == null)
                : workflows.filter(w => w.project_id === p.id);
        return inProject.filter(w => !w.expose_as_custom_skill).length;
    };

    const selectedProject = React.useMemo(
        () =>
            selectedProjectId
                ? workflowProjects.find(p => p.id === selectedProjectId) ?? null
                : null,
        [workflowProjects, selectedProjectId],
    );

    const [routeLoadError, setRouteLoadError] = useState<string | null>(null);

    const closeActiveWorkflowSession = useCallback(() => {
        graphHistoryRef.current.clear();
        setActiveWf(null);
        setLastSavedWf(null);
        setNodes([]);
        setEdges([]);
        setSelectedEdge(null);
        setPendingNodeDelete(null);
        setNodeDeleteKeyboardMessage(null);
        setDeletingEdgeId(null);
        setRunResult(null);
        setRunningNodeIds(new Set());
        setLastRunId(null);
        setIsLastRunOpen(false);
        setLastRunNodeData({});
        setSaveError(null);
    }, []);

    const openWorkflow = async (
        wfOrListItem: WorkflowDefinition | WorkflowDefinitionListItem,
        opts?: { skipDirtyConfirm?: boolean },
    ) => {
        setSaveError(null);
        if (
            isDirty &&
            activeWf &&
            wfOrListItem.id !== activeWf.id &&
            !opts?.skipDirtyConfirm
        ) {
            if (!window.confirm("You have unsaved changes in your current workflow. Are you sure you want to discard them and open a different workflow?")) {
                return;
            }
        }
        const wf: WorkflowDefinition = 'graph' in wfOrListItem
            ? wfOrListItem as WorkflowDefinition
            : await ApiClient.getWorkflow(wfOrListItem.id);
        const responseNodeIds = new Set(
            (wf.graph.nodes as AppGraphNode[]).filter(n => (n as any).kind === 'utility' && (n as any).utility_type === 'response').map(n => n.id)
        );
        const filteredNodes = (wf.graph.nodes as AppGraphNode[]).filter(n => !responseNodeIds.has(n.id));
        const filteredEdges = wf.graph.edges.filter((e: { source: string; target: string }) => !responseNodeIds.has(e.source) && !responseNodeIds.has(e.target));
        const wfWithGraph = { ...wf, graph: { ...wf.graph, nodes: filteredNodes, edges: filteredEdges } };
        graphHistoryRef.current.clear();
        setWorkflows(ws => mergeWorkflowDefinitionIntoList(ws, wfWithGraph));
        setActiveWf(wfWithGraph);
        setLastSavedWf(wfWithGraph);
        const flowNodes = filteredNodes.map(n => appNodeToFlow(n));
        const enrichedForEdges = flowNodes.map(n => {
            if (n.type === 'workflowRef') {
                const d = n.data as any;
                const subWorkflowRequiredOutputs = [{ key: 'output', type: 'string' as const }];
                return { ...n, data: { ...d, subWorkflowRequiredOutputs } };
            }
            return n;
        });
        setNodes(flowNodes.map(n => ({ ...n, selected: false })));
        const pal = wf.palette_id ? palettes.find(p => p.id === wf.palette_id) : resolveFallbackWorkflowPalette(palettes);
        const colors = pal?.colors ? normalizeWorkflowPaletteColors(pal.colors) : DEFAULT_PALETTE_COLORS;
        setEdges(filteredEdges.map((e: AppGraphEdge, i: number) => appEdgeToFlow(e, i, enrichedForEdges, colors, filteredEdges)));
        setSelectedEdge(null);
        setPendingNodeDelete(null);
        setNodeDeleteKeyboardMessage(null);
        setRunResult(null);
        setRunningNodeIds(new Set());
        setLastRunId(null);

        const folderId = wfWithGraph.project_id ?? sharedProjectId;
        if (folderId) setSelectedProjectId(folderId);
        if (wfWithGraph.expose_as_custom_skill) setIsCustomSkillsOpen(true);

        onSyncWorkflowPath?.(wfWithGraph.id);
    };

    const openWorkflowRef = useRef(openWorkflow);
    openWorkflowRef.current = openWorkflow;

    useEffect(() => {
        setRouteLoadError(null);
    }, [routeWorkflowId]);

    useEffect(() => {
        if (isDataLoading) return;
        const rid = routeWorkflowId ?? null;
        if (rid === null) return;
        if (activeWf?.id === rid) return;

        let cancelled = false;
        void (async () => {
            try {
                const inList = workflows.find(w => w.id === rid);
                const wf = inList ?? (await ApiClient.getWorkflow(rid));
                if (cancelled) return;
                await openWorkflowRef.current(wf, { skipDirtyConfirm: true });
            } catch {
                if (cancelled) return;
                setRouteLoadError('Could not open this workflow from the URL.');
                onSyncWorkflowPath?.(null);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [isDataLoading, routeWorkflowId, activeWf?.id, workflows, onSyncWorkflowPath]);

    useEffect(() => {
        if (isDataLoading) return;
        if (routeWorkflowId != null) return;
        if (!activeWf) return;
        if (isDirty) {
            onSyncWorkflowPath?.(activeWf.id);
            return;
        }
        closeActiveWorkflowSession();
    }, [
        isDataLoading,
        routeWorkflowId,
        activeWf,
        isDirty,
        closeActiveWorkflowSession,
        onSyncWorkflowPath,
    ]);

    const confirmDiscardAndImport = (): void => {
        if (isDirty && activeWf) {
            if (!window.confirm('You have unsaved changes. Discard them and import a new workflow?')) {
                throw new WorkflowImportError('Import cancelled.');
            }
        }
    };

    const handleImportWorkflow = async (payload: WorkflowDefinitionCreate) => {
        confirmDiscardAndImport();
        const paletteOk = payload.palette_id && palettes.some(p => p.id === payload.palette_id);
        const baseName = payload.name.trim();
        const name = baseName.toLowerCase().endsWith(' (imported)') ? baseName : `${baseName} (imported)`;
        if (!selectedProjectId) {
            throw new WorkflowImportError('Select a project folder first.');
        }
        const importGraph = payload.graph;
        if (!importGraph) {
            throw new WorkflowImportError('Import payload missing graph.');
        }
        const created = await ApiClient.createWorkflow({
            name,
            description: payload.description ?? null,
            graph: importGraph,
            palette_id: paletteOk ? payload.palette_id : null,
            project_id: selectedProjectId,
        });
        const wfs = await ApiClient.getWorkflows();
        setWorkflows(wfs);
        const projs = await ApiClient.getWorkflowProjects().catch(() => [] as WorkflowProject[]);
        setWorkflowProjects(projs);
        const refs = collectWorkflowRefIds(importGraph);
        setWorkflowImportNotice(
            refs.length > 0
                ? `Imported: ${refs.length} nested workflow reference(s) may need re-linking in the inspector if those workflows are missing here.`
                : null,
        );
        await openWorkflow(created);
    };

    const handleImportWorkflowBundle = async (bundle: WorkflowBundleExportDocument) => {
        confirmDiscardAndImport();
        if (!selectedProjectId) {
            throw new WorkflowImportError('Select a project folder first.');
        }
        const plan = planBundleImport(
            bundle,
            bundleImportExistingNames({
                workflows,
                personas,
                structures,
                documents,
                palettes,
            }),
        );
        const { root, importWarnings } = await executeWorkflowBundleImport({
            bundle,
            plan,
            projectId: selectedProjectId,
            api: {
                createPalette: data => ApiClient.createPalette(data),
                getPaletteBySlug: slug => ApiClient.getPaletteBySlug(slug),
                createPersona: data => ApiClient.createPersona(data),
                createStructure: data => ApiClient.createStructure(data),
                createDocument: data => ApiClient.createDocument(data),
                createWorkflow: data => ApiClient.createWorkflow(data),
                updateWorkflow: (id, data) => ApiClient.updateWorkflow(id, data),
            },
        });
        await loadAll();
        const nestedCount = bundle.included_workflows.length;
        const parts = [
            `Imported bundle: ${root.name}` +
                (nestedCount > 0 ? ` (+${nestedCount} nested workflow${nestedCount === 1 ? '' : 's'})` : ''),
        ];
        if (importWarnings.length > 0) {
            parts.push(importWarnings.join(' '));
        }
        setWorkflowImportNotice(parts.join(' '));
        await openWorkflow(root);
    };

    const exportActiveWorkflowBundleJson = async (): Promise<string> => {
        if (!activeWf) {
            throw new WorkflowBundleExportError('No workflow open to export.');
        }
        const doc = await assembleWorkflowBundleExport(activeWf, {
            fetchWorkflow: id => ApiClient.getWorkflow(id),
            fetchPersona: id => ApiClient.getPersona(id),
            fetchStructure: id => ApiClient.getStructure(id),
            fetchDocument: id => ApiClient.getDocument(id),
            fetchPalette: id => ApiClient.getPalette(id),
        });
        return serializeWorkflowBundleExport(doc);
    };

    const handleExportBundleDownload = async () => {
        if (!activeWf || bundleExportBusy) return;
        setBundleExportBusy(true);
        try {
            const json = await exportActiveWorkflowBundleJson();
            const blob = new Blob([json], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${slugifyWorkflowBundleExportBasename(activeWf.name)}.json`;
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            if (e instanceof WorkflowBundleExportError) {
                const detail =
                    e.missingWorkflowIds.length > 0
                        ? `\n\nMissing nested workflow id(s): ${e.missingWorkflowIds.join(', ')}`
                        : '';
                window.alert(`${e.message}${detail}`);
            } else {
                window.alert(e instanceof Error ? e.message : 'Export failed.');
            }
        } finally {
            setBundleExportBusy(false);
        }
    };

    const handleExportBundleCopy = async () => {
        if (!activeWf || bundleExportBusy) return;
        setBundleExportBusy(true);
        try {
            const json = await exportActiveWorkflowBundleJson();
            await copyWithFeedback(json);
        } catch (e) {
            if (e instanceof WorkflowBundleExportError) {
                const detail =
                    e.missingWorkflowIds.length > 0
                        ? ` Missing nested workflow id(s): ${e.missingWorkflowIds.join(', ')}`
                        : '';
                showStatusToast(`${e.message}${detail}`, true);
            } else {
                showStatusToast(e instanceof Error ? e.message : 'Export failed.', true);
            }
        } finally {
            setBundleExportBusy(false);
        }
    };

    const createWorkflow = async () => {
        if (isDirty) {
            if (!window.confirm("You have unsaved changes in your current workflow. Are you sure you want to discard them and create a new workflow?")) {
                return;
            }
        }
        const prefRaw = user?.settings?.preferred_editor_palette_id;
        const preferredId =
            typeof prefRaw === 'string' &&
            prefRaw.trim() !== '' &&
            palettes.some(p => p.id === prefRaw)
                ? prefRaw.trim()
                : null;
        if (!selectedProjectId) return;
        const wf = await ApiClient.createWorkflow({
            name: 'New Workflow',
            palette_id: preferredId,
            graph: {
                nodes: [
                    { id: genId(), kind: 'start', label: 'Start', position: { x: 50, y: 150 }, data: { required_inputs: [] } },
                    {
                        id: genId(),
                        kind: 'stop',
                        label: 'Stop',
                        position: { x: 600, y: 150 },
                        data: { required_outputs: [{ key: 'output', type: 'string' }] },
                    },
                ],
                edges: []
            },
            project_id: selectedProjectId,
        });
        await refreshWorkflowLists();
        openWorkflow(wf);
    };

    const moveWorkflowToProject = async (wfId: string, projectId: string): Promise<boolean> => {
        try {
            await ApiClient.updateWorkflow(wfId, { project_id: projectId });
            await refreshWorkflowLists();
            if (activeWf?.id === wfId) {
                setActiveWf(prev => (prev ? { ...prev, project_id: projectId } : null));
                setLastSavedWf(prev => (prev?.id === wfId ? { ...prev, project_id: projectId } : prev));
            }
            return true;
        } catch {
            /* ignore */
            return false;
        }
    };

    const handleCreateProject = async () => {
        const name = newProjectNameDraft.trim();
        if (!name) return;
        try {
            await ApiClient.createWorkflowProject({ name });
            setNewProjectNameDraft('');
            await refreshWorkflowLists();
        } catch {
            /* ignore */
        }
    };

    const handleDeleteProject = async () => {
        if (!selectedProjectId || !selectedProject) return;
        const inProject = workflowsInProject(selectedProjectId, sharedProjectId, workflows);
        const workflowCount = inProject.length;
        try {
            await ApiClient.deleteWorkflowProject(selectedProjectId, {
                deleteWorkflows: workflowCount > 0,
            });
            if (activeWf && inProject.some(w => w.id === activeWf.id)) {
                closeActiveWorkflowSession();
                onSyncWorkflowPath?.(null);
            }
            setSelectedProjectId(null);
            setWorkflowNameFilter('');
            await refreshWorkflowLists();
        } catch (err) {
            console.error('Failed to delete project:', err);
        }
    };

    const selectedProjectDeleteWorkflowCount = React.useMemo(() => {
        if (!selectedProjectId) return 0;
        return workflowsInProject(selectedProjectId, sharedProjectId, workflows).length;
    }, [selectedProjectId, sharedProjectId, workflows]);

    const loopBodyNodeIds = useMemo(
        () =>
            unionLoopBodyNodeIds({
                nodes: nodes.map(flowNodeToApp) as any,
                edges: edges.map(flowEdgeToApp) as any,
            }),
        [nodes, edges],
    );

    useEffect(() => {
        const ids = [
            ...new Set(
                nodes
                    .filter(n => n.type === 'workflowRef')
                    .map(n => String((n.data as { workflow_id?: string }).workflow_id ?? '').trim())
                    .filter(id => id.length > 0),
            ),
        ];
        for (const id of ids) {
            const row = workflows.find(w => w.id === id);
            if (workflowListEntryHasGraph(row)) continue;
            if (workflowPrefetchInFlightRef.current.has(id)) continue;
            workflowPrefetchInFlightRef.current.add(id);
            void ApiClient.getWorkflow(id)
                .then(full => {
                    setWorkflows(ws => mergeWorkflowDefinitionIntoList(ws, full));
                })
                .finally(() => {
                    workflowPrefetchInFlightRef.current.delete(id);
                });
        }
    }, [nodes, workflows]);

    // Enrich nodes with handle state and palette colors (must be before onConnect/edgesForFlow which use it)
    const nodesForFlow = React.useMemo(
        () =>
            enrichNodesForCanvasFlow(
                nodes,
                edges,
                paletteColors,
                workflows,
                structures,
                documents,
            ).map(n => ({
                ...n,
                data: {
                    ...(n.data as object),
                    outputOverrideActive: outputOverrides[n.id] !== undefined,
                },
            })) as Node[],
        [nodes, edges, paletteColors, workflows, structures, documents, outputOverrides],
    );

    const edgesForFlow = React.useMemo(
        () => styleEdgesForCanvas(edges, nodesForFlow, paletteColors, selectedEdge?.id ?? null),
        [edges, nodesForFlow, paletteColors, selectedEdge],
    );

    // ReactFlow handlers
    const onNodesChange = useCallback(
        (changes: NodeChange[]) => {
            if (
                !isApplyingGraphHistoryRef.current &&
                !reactFlowNodeChangesSkipUndoRecord(changes, workflowCanvasInteractionRef.current)
            ) {
                recordGraphBeforeMutation();
            }
            setNodes(ns => applyNodeChanges(changes, ns));
        },
        [recordGraphBeforeMutation],
    );
    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => {
            if (!isApplyingGraphHistoryRef.current && !reactFlowEdgeChangesSkipUndoRecord(changes)) {
                recordGraphBeforeMutation();
            }
            const removeIds = changes.filter((c): c is EdgeChange & { type: 'remove'; id: string } => c.type === 'remove').map(c => c.id);
            const removedEdges = removeIds.map(id => edges.find(e => e.id === id)).filter((e): e is Edge => Boolean(e));
            if (removedEdges.length > 0) {
                setNodes(ns => applyForLoopEndClearOnEdgeRemoved(ns, removedEdges));
            }
            setEdges(es => applyEdgeChanges(changes, es));
        },
        [edges, recordGraphBeforeMutation],
    );
    const onConnect: OnConnect = useCallback((params: Connection) => {
        const sourceNode = nodes.find(n => n.id === params.source);
        const targetNode = nodes.find(n => n.id === params.target);
        if (isAnnotationFlowNodeType(sourceNode?.type) || isAnnotationFlowNodeType(targetNode?.type)) {
            return;
        }
        recordGraphBeforeMutation();
        const pairing = pairForLoopEndOnConnect(params, sourceNode, targetNode);
        if (pairing) {
            setNodes(ns =>
                ns.map(n =>
                    n.id === pairing.targetId ?
                        { ...n, data: { ...(n.data as object), for_loop_id: pairing.forLoopId } }
                    :   n,
                ),
            );
        }
        const type = getSourceOutputType(nodesForFlow, params.source ?? '', params.sourceHandle ?? undefined, edges);
        const color = resolveWorkflowPaletteColor(paletteColors, type);
        setEdges(es => addEdge({
            ...params,
            animated: false,
            style: { strokeWidth: 3, stroke: color },
            markerEnd: { type: MarkerType.ArrowClosed, color },
            zIndex: 1000
        }, es));
    }, [nodes, nodesForFlow, paletteColors, edges, recordGraphBeforeMutation]);

    const onNodeDragStart = useCallback(() => {
        recordGraphBeforeMutation();
        workflowCanvasInteractionRef.current.nodeDrag = true;
    }, [recordGraphBeforeMutation]);

    const onNodeDragStop = useCallback(() => {
        workflowCanvasInteractionRef.current.nodeDrag = false;
    }, []);

    const onNodeClick = useCallback((_: React.MouseEvent, _node: Node) => {
        setSelectedEdge(null);
        setPendingNodeDelete(null);
        setDeletingEdgeId(null);
        setInspectorTab('node');
    }, []);
    const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
        setNodes(ns => ns.map(n => ({ ...n, selected: false })));
        setSelectedEdge(edge);
        setPendingNodeDelete(null);
        setDeletingEdgeId(null);
        setInspectorTab('node');
    }, []);
    const onPaneClick = useCallback(() => {
        setNodes(ns => ns.map(n => ({ ...n, selected: false })));
        setSelectedEdge(null);
        setPendingNodeDelete(null);
        setDeletingEdgeId(null);
        setInspectorTab('node');
        if (overlayPanels) {
            setCompactPaletteOpen(false);
            setCompactExplorerOpen(false);
        }
    }, [overlayPanels]);

    const onImmersiveEdgePointerDown = useCallback((edge: 'left' | 'right', e: React.PointerEvent<HTMLButtonElement>) => {
        immersiveEdgeTapTrackingRef.current = {
            edge,
            x: e.clientX,
            y: e.clientY,
            pointerId: e.pointerId,
        };
    }, []);

    const onImmersiveEdgePointerUp = useCallback(
        (edge: 'left' | 'right', e: React.PointerEvent<HTMLButtonElement>) => {
            const t = immersiveEdgeTapTrackingRef.current;
            immersiveEdgeTapTrackingRef.current = null;
            if (!t || t.pointerId !== e.pointerId || t.edge !== edge) return;
            const dx = Math.abs(e.clientX - t.x);
            const dy = Math.abs(e.clientY - t.y);
            if (dx > IMMERSIVE_PANEL_EDGE_TAP_MOVE_THRESHOLD_PX || dy > IMMERSIVE_PANEL_EDGE_TAP_MOVE_THRESHOLD_PX) {
                return;
            }
            const result = immersivePanelEdgeTapResult(edge, {
                immersive: Boolean(immersive),
                runInputWizardOpen: runInputWizard != null,
                workflowImportModalOpen,
                outputOverrideModalOpen,
                compactPaletteOpen,
                compactExplorerOpen,
            });
            if (result) {
                setCompactPaletteOpen(result.nextPaletteOpen);
                setCompactExplorerOpen(result.nextExplorerOpen);
            }
        },
        [
            immersive,
            runInputWizard,
            workflowImportModalOpen,
            outputOverrideModalOpen,
            compactPaletteOpen,
            compactExplorerOpen,
        ],
    );

    const onImmersiveEdgePointerCancel = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
        const t = immersiveEdgeTapTrackingRef.current;
        if (t?.pointerId === e.pointerId) immersiveEdgeTapTrackingRef.current = null;
    }, []);

    // Connection validation (see workflowConnectionRules.ts)
    const isValidConnection = useCallback(
        (connection: Connection | Edge) => isValidWorkflowConnection(nodes, edges, connection),
        [nodes, edges],
    );

    // Drag-and-drop from palette
    const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }, []);
    const onDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        const type = e.dataTransfer.getData('nodeType');
        if (!type) return;
        const rf = reactFlowInstanceRef.current;
        if (!rf) return;
        const extra = JSON.parse(e.dataTransfer.getData('nodeExtra') || '{}');
        const p = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
        const position = { x: p.x - 80, y: p.y - 40 };
        const id = genId();
        recordGraphBeforeMutation();
        if (type === 'simpleLLMCall') {
            setNodes(ns => [...ns, {
                id,
                type: 'simpleLLMCall',
                position,
                data: {
                    label: extra.label ?? 'LLM Call',
                    required_inputs: [{ key: 'user_prompt', type: 'string', value: null }],
                    persona_id: null,
                    structure_id: null,
                    additional_system_prompt_context: null,
                },
            }]);
        } else if (type === 'multimodalLLMCall') {
            setNodes(ns => [...ns, {
                id,
                type: 'multimodalLLMCall',
                position,
                data: {
                    label: extra.label ?? 'Multimodal LLM',
                    required_inputs: [
                        { key: 'user_prompt', type: 'string', value: null },
                        { key: 'images', type: 'list', value: null },
                    ],
                    persona_id: null,
                    structure_id: null,
                    additional_system_prompt_context: null,
                    model: null,
                },
            }]);
        } else if (type === 'textToSpeech') {
            setNodes(ns => [...ns, {
                id,
                type: 'textToSpeech',
                position,
                data: {
                    label: extra.label ?? 'Text-to-Speech',
                    tts_model_id: null,
                    voice_sample_id: null,
                    engine: null,
                    tts_options: {},
                    required_inputs: [{ key: 'text', type: 'string', value: null }],
                },
            }]);
        } else if (type === 'transcribeAudio') {
            setNodes(ns => [...ns, {
                id,
                type: 'transcribeAudio',
                position,
                data: {
                    label: extra.label ?? 'Voice input',
                    task: 'transcribe',
                    language: null,
                    model: null,
                },
            }]);
        } else if (type === 'audioFileInput') {
            setNodes(ns => [...ns, {
                id,
                type: 'audioFileInput',
                position,
                data: {
                    label: extra.label ?? 'Audio File Input',
                    audio_artifact_id: null,
                    task: 'transcribe',
                    language: null,
                    model: null,
                },
            }]);
        } else if (type === 'transcribeFile') {
            setNodes(ns => [...ns, {
                id,
                type: 'transcribeFile',
                position,
                data: {
                    label: extra.label ?? 'Transcribe File',
                    provider: extra.provider ?? 'local_whisper',
                    audio_artifact_id: null,
                    task: 'transcribe',
                    language: null,
                    prompt: null,
                    diarization_enabled: extra.diarization_enabled ?? false,
                    include_word_timestamps: extra.include_word_timestamps ?? false,
                    provider_model_id: null,
                },
            }]);
        } else if (type === 'gmailListMessages') {
            setNodes(ns => [...ns, {
                id,
                type: 'gmailListMessages',
                position,
                data: {
                    label: extra.label ?? 'Gmail List',
                    google_connection_id: null,
                    max_results: 10,
                    unread_only: false,
                    after: null,
                    before: null,
                    required_inputs: [
                        { key: 'after', type: 'string', value: null },
                        { key: 'before', type: 'string', value: null },
                        { key: 'unread_only', type: 'boolean', value: false },
                        { key: 'query', type: 'string', value: null },
                        { key: 'max_results', type: 'int', value: 10 },
                    ],
                },
            }]);
        } else if (type === 'calendarListEvents') {
            setNodes(ns => [...ns, {
                id,
                type: 'calendarListEvents',
                position,
                data: {
                    label: extra.label ?? 'Calendar Events',
                    google_connection_id: null,
                    calendar_id: 'primary',
                    required_inputs: [
                        { key: 'time_min', type: 'string', value: null },
                        { key: 'time_max', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'googleDocsGetDocument') {
            setNodes(ns => [...ns, {
                id,
                type: 'googleDocsGetDocument',
                position,
                data: {
                    label: extra.label ?? 'Google Docs Get',
                    google_connection_id: null,
                    document_url_or_id: null,
                    include_tabs_content: true,
                    required_inputs: [
                        { key: 'document_url_or_id', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'googleDocsParseDocument') {
            setNodes(ns => [...ns, {
                id,
                type: 'googleDocsParseDocument',
                position,
                data: {
                    label: extra.label ?? 'Google Docs Parse',
                    chunk_strategy: 'structure',
                    max_chunk_text_chars: null,
                    required_inputs: [
                        { key: 'document', type: 'dictionary', value: null },
                    ],
                },
            }]);
        } else if (type === 'fetchUrl') {
            setNodes(ns => [...ns, {
                id,
                type: 'fetchUrl',
                position,
                data: {
                    label: extra.label ?? 'Fetch URL',
                    url: '',
                    method: 'GET',
                    headers: {},
                    timeout_ms: null,
                    cache_policy: 'default',
                    required_inputs: [
                        { key: 'url', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'captureUrlSnapshot') {
            setNodes(ns => [...ns, {
                id,
                type: 'captureUrlSnapshot',
                position,
                data: {
                    label: extra.label ?? 'URL snapshot',
                    url: '',
                    full_page: true,
                    viewport_width: null,
                    viewport_height: null,
                    wait_until: 'load',
                    timeout_ms: null,
                    cache_policy: 'default',
                    required_inputs: [
                        { key: 'url', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'listToString') {
            setNodes(ns => [...ns, {
                id,
                type: 'listToString',
                position,
                data: {
                    label: extra.label ?? 'List to String',
                    use_text_join: true,
                    add_line_breaks_between_items: true,
                },
            }]);
        } else if (type === 'stringToList') {
            setNodes(ns => [...ns, { id, type: 'stringToList', position, data: { label: extra.label ?? 'String to List' } }]);
        } else if (type === 'prependText') {
            setNodes(ns => [...ns, {
                id,
                type: 'prependText',
                position,
                data: {
                    label: extra.label ?? 'Prepend Text',
                    required_inputs: [
                        { key: 'target_string', type: 'string', value: null },
                        { key: 'text_to_prepend', type: 'string', value: null },
                    ],
                    add_additional_line: false,
                },
            }]);
        } else if (type === 'stringTrunc') {
            setNodes(ns => [...ns, {
                id,
                type: 'stringTrunc',
                position,
                data: {
                    label: extra.label ?? 'String Trunc',
                    required_inputs: [
                        { key: 'target_string', type: 'string', value: null },
                        { key: 'start_index', type: 'int', value: 0 },
                        { key: 'end_index', type: 'int', value: -1 },
                    ],
                },
            }]);
        } else if (type === 'messageUtility') {
            setNodes(ns => [...ns, {
                id,
                type: 'messageUtility',
                position,
                data: {
                    label: extra.label ?? 'Message',
                    required_inputs: [{ key: 'message', type: 'string', value: null }],
                },
            }]);
        } else if (type === 'basicConditional') {
            setNodes(ns => [...ns, {
                id,
                type: 'basicConditional',
                position,
                data: {
                    label: extra.label ?? 'Conditional',
                    required_inputs: [{ key: 'condition', type: 'boolean', value: null }],
                    condition: null,
                },
            }]);
        } else if (type === 'isControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'isControl',
                position,
                data: {
                    label: extra.label ?? 'Is?',
                    required_inputs: [
                        { key: 'input_a', type: 'string', value: null },
                        { key: 'input_b', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'isEmptyControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'isEmptyControl',
                position,
                data: {
                    label: extra.label ?? 'Is Empty?',
                    required_inputs: [{ key: 'value', type: 'any', value: null }],
                },
            }]);
        } else if (type === 'gtControl') {
            setNodes(ns => [...ns, { id, type: 'gtControl', position, data: { label: extra.label ?? 'Gt?', required_inputs: [{ key: 'input_a', type: 'string', value: null }, { key: 'input_b', type: 'string', value: null }] } }]);
        } else if (type === 'ltControl') {
            setNodes(ns => [...ns, { id, type: 'ltControl', position, data: { label: extra.label ?? 'Lt?', required_inputs: [{ key: 'input_a', type: 'string', value: null }, { key: 'input_b', type: 'string', value: null }] } }]);
        } else if (type === 'gteControl') {
            setNodes(ns => [...ns, { id, type: 'gteControl', position, data: { label: extra.label ?? 'Gte?', required_inputs: [{ key: 'input_a', type: 'string', value: null }, { key: 'input_b', type: 'string', value: null }] } }]);
        } else if (type === 'lteControl') {
            setNodes(ns => [...ns, { id, type: 'lteControl', position, data: { label: extra.label ?? 'Lte?', required_inputs: [{ key: 'input_a', type: 'string', value: null }, { key: 'input_b', type: 'string', value: null }] } }]);
        } else if (type === 'andControl') {
            setNodes(ns => [...ns, { id, type: 'andControl', position, data: { label: extra.label ?? 'And', required_inputs: [{ key: 'input_a', type: 'boolean', value: null }, { key: 'input_b', type: 'boolean', value: null }] } }]);
        } else if (type === 'orControl') {
            setNodes(ns => [...ns, { id, type: 'orControl', position, data: { label: extra.label ?? 'Or', required_inputs: [{ key: 'input_a', type: 'boolean', value: null }, { key: 'input_b', type: 'boolean', value: null }] } }]);
        } else if (type === 'xorControl') {
            setNodes(ns => [...ns, { id, type: 'xorControl', position, data: { label: extra.label ?? 'Xor', required_inputs: [{ key: 'input_a', type: 'boolean', value: null }, { key: 'input_b', type: 'boolean', value: null }] } }]);
        } else if (type === 'notControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'notControl',
                position,
                data: { label: extra.label ?? 'Not', required_inputs: [{ key: 'input', type: 'boolean', value: null }] },
            }]);
        } else if (type === 'betweenControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'betweenControl',
                position,
                data: {
                    label: extra.label ?? 'Between',
                    required_inputs: [
                        { key: 'low', type: 'int', value: 0 },
                        { key: 'value', type: 'int', value: 0 },
                        { key: 'high', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'tryCatchControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'tryCatchControl',
                position,
                data: {
                    label: extra.label ?? 'Try / Catch',
                    required_inputs: [{ key: 'value', type: 'any', value: null }],
                },
            }]);
        } else if (type === 'forLoopControl') {
            setNodes(ns => [...ns, {
                id,
                type: 'forLoopControl',
                position,
                data: {
                    label: extra.label ?? 'For Loop',
                    required_inputs: [{ key: 'input', type: 'list', value: null }],
                    iteration_mode: 'sequential',
                },
            }]);
        } else if (type === 'forLoopEndControl') {
            const ex = (extra as { exports?: string[] }).exports;
            setNodes(ns => [...ns, {
                id,
                type: 'forLoopEndControl',
                position,
                data: {
                    label: (extra as { label?: string }).label ?? 'For Loop End',
                    for_loop_id: (extra as { for_loop_id?: string }).for_loop_id ?? '',
                    exports: Array.isArray(ex) && ex.length > 0 ? ex : ['odds', 'evens'],
                },
            }]);
        } else if (type === 'structurePrimitive') {
            setNodes(ns => [...ns, { id, type: 'structurePrimitive', position, data: { label: 'Structure', structure_id: '' } }]);
        } else if (type === 'documentPrimitive') {
            setNodes(ns => [...ns, { id, type: 'documentPrimitive', position, data: { label: 'Document', document_id: '' } }]);
        } else if (type === 'imagePrimitive') {
            setNodes(ns => [...ns, {
                id,
                type: 'imagePrimitive',
                position,
                data: {
                    label: 'Image',
                    artifact_id: '',
                    required_inputs: [{ key: 'image', type: 'dictionary', value: null }],
                },
            }]);
        } else if (type === 'gmailPrimitive') {
            setNodes(ns => [
                ...ns,
                {
                    id,
                    type: 'gmailPrimitive',
                    position,
                    data: {
                        label: (extra as { label?: string }).label ?? 'Gmail',
                        message: {},
                        required_inputs: [{ key: 'gmail', type: 'gmail' as const, value: null }],
                    },
                },
            ]);
        } else if (type === 'sandboxBehaviorPrimitive') {
            setNodes(ns => [...ns, { id, type: 'sandboxBehaviorPrimitive', position, data: { label: 'Sandbox behavior' } }]);
        } else if (type === 'decisionActionPrimitive') {
            setNodes(ns => [
                ...ns,
                {
                    id,
                    type: 'decisionActionPrimitive',
                    position,
                    data: { label: extra.label ?? 'Decision action', action: DEFAULT_SANDBOX_DECISION_ACTION },
                },
            ]);
        } else if (type === 'sandboxTickPrimitive') {
            setNodes(ns => [...ns, { id, type: 'sandboxTickPrimitive', position, data: { label: extra.label ?? 'Sandbox tick' } }]);
        } else if (type === 'stringPrimitive') {
            setNodes(ns => [...ns, { id, type: 'stringPrimitive', position, data: { label: 'String', text: '' } }]);
        } else if (type === 'listPrimitive') {
            setNodes(ns => [...ns, { id, type: 'listPrimitive', position, data: { label: 'List', data: [] } }]);
        } else if (type === 'dictionaryPrimitive') {
            setNodes(ns => [...ns, { id, type: 'dictionaryPrimitive', position, data: { label: 'Dictionary', data: {} } }]);
        } else if (type === 'booleanPrimitive') {
            setNodes(ns => [...ns, { id, type: 'booleanPrimitive', position, data: { label: 'Boolean', value: false } }]);
        } else if (type === 'dateTimePrimitive') {
            setNodes(ns => [...ns, { id, type: 'dateTimePrimitive', position, data: { label: 'DateTime', iso: null, use_now: false } }]);
        } else if (type === 'intPrimitive') {
            setNodes(ns => [...ns, { id, type: 'intPrimitive', position, data: { label: 'Int', value: 0 } }]);
        } else if (type === 'lenFromList') {
            setNodes(ns => [...ns, { id, type: 'lenFromList', position, data: { label: extra.label ?? 'Len from List' } }]);
        } else if (type === 'randomItemFromList') {
            setNodes(ns => [...ns, { id, type: 'randomItemFromList', position, data: { label: extra.label ?? 'Random item from list' } }]);
        } else if (type === 'sandboxTickItems') {
            setNodes(ns => [...ns, { id, type: 'sandboxTickItems', position, data: { label: extra.label ?? 'Sandbox get items', item_type: 'all' } }]);
        } else if (type === 'sandboxWorldGrid') {
            setNodes(ns => [...ns, { id, type: 'sandboxWorldGrid', position, data: { label: extra.label ?? 'Sandbox world grid' } }]);
        } else if (type === 'sandboxAvailableCells') {
            setNodes(ns => [...ns, { id, type: 'sandboxAvailableCells', position, data: { label: extra.label ?? 'Sandbox available cells' } }]);
        } else if (type === 'sandboxTickPet') {
            setNodes(ns => [...ns, { id, type: 'sandboxTickPet', position, data: { label: extra.label ?? 'Sandbox tick pet' } }]);
        } else if (type === 'sandboxNearestItemByType') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxNearestItemByType',
                position,
                data: {
                    label: extra.label ?? 'Sandbox nearest item by type',
                    required_inputs: [
                        { key: 'sandbox_tick', type: 'dictionary', value: null },
                        { key: 'item_type', type: 'string', value: 'food' },
                    ],
                },
            }]);
        } else if (type === 'sandboxClosestItem') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxClosestItem',
                position,
                data: {
                    label: extra.label ?? 'Get Closest Item',
                    required_inputs: [
                        { key: 'sandbox_tick', type: 'dictionary', value: null },
                        { key: 'item_type', type: 'string', value: 'food' },
                    ],
                },
            }]);
        } else if (type === 'sandboxDecisionMoveTo') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxDecisionMoveTo',
                position,
                data: {
                    label: extra.label ?? 'Sandbox decision move_to',
                    required_inputs: [
                        { key: 'target_item_id', type: 'string', value: null },
                        { key: 'target_cell', type: 'dictionary', value: null },
                        { key: 'reason', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'sandboxStarterDecision') {
            setNodes(ns => [...ns, { id, type: 'sandboxStarterDecision', position, data: { label: extra.label ?? 'Starter sandbox decision' } }]);
        } else if (type === 'sandboxFilterItemsByType') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxFilterItemsByType',
                position,
                data: {
                    label: extra.label ?? 'Sandbox filter items by type',
                    required_inputs: [
                        { key: 'items', type: 'list', value: null },
                        { key: 'item_type', type: 'string', value: 'food' },
                    ],
                },
            }]);
        } else if (type === 'sandboxDecisionIntent') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxDecisionIntent',
                position,
                data: {
                    label: extra.label ?? 'Sandbox decision intent',
                    required_inputs: [
                        { key: 'action', type: 'string', value: 'wander' },
                        { key: 'target_item_id', type: 'string', value: null },
                        { key: 'target_cell', type: 'dictionary', value: null },
                        { key: 'reason', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'sandboxPetHunger') {
            setNodes(ns => [...ns, { id, type: 'sandboxPetHunger', position, data: { label: extra.label ?? 'Sandbox pet hunger' } }]);
        } else if (type === 'sandboxPetEnergy') {
            setNodes(ns => [...ns, { id, type: 'sandboxPetEnergy', position, data: { label: extra.label ?? 'Sandbox pet energy' } }]);
        } else if (type === 'sandboxPetCell') {
            setNodes(ns => [...ns, { id, type: 'sandboxPetCell', position, data: { label: extra.label ?? 'Sandbox pet cell' } }]);
        } else if (type === 'sandboxIsNearby8') {
            setNodes(ns => [...ns, {
                id,
                type: 'sandboxIsNearby8',
                position,
                data: {
                    label: extra.label ?? 'Sandbox is nearby8',
                    required_inputs: [
                        { key: 'cell_a', type: 'dictionary', value: null },
                        { key: 'cell_b', type: 'dictionary', value: null },
                    ],
                },
            }]);
        } else if (type === 'sandboxFirstNearbyFood') {
            setNodes(ns => [...ns, { id, type: 'sandboxFirstNearbyFood', position, data: { label: extra.label ?? 'Sandbox first nearby food' } }]);
        } else if (type === 'sandboxFirstFoodWorldOrder') {
            setNodes(ns => [...ns, { id, type: 'sandboxFirstFoodWorldOrder', position, data: { label: extra.label ?? 'Sandbox first food (world order)' } }]);
        } else if (type === 'intToString') {
            setNodes(ns => [...ns, { id, type: 'intToString', position, data: { label: extra.label ?? 'Int to String' } }]);
        } else if (type === 'listItemByIndex') {
            setNodes(ns => [...ns, {
                id,
                type: 'listItemByIndex',
                position,
                data: {
                    label: extra.label ?? 'List Item by Index',
                    required_inputs: [
                        { key: 'index', type: 'int', value: 0 },
                        { key: 'list', type: 'list', value: null },
                    ],
                },
            }]);
        } else if (type === 'dictionaryValueByKey') {
            setNodes(ns => [...ns, {
                id,
                type: 'dictionaryValueByKey',
                position,
                data: {
                    label: extra.label ?? 'Dictionary Value by Key',
                    output_value_type: 'list',
                    required_inputs: [
                        { key: 'key', type: 'string', value: '' },
                        { key: 'dictionary', type: 'dictionary', value: null },
                        { key: 'fallback', type: 'any', value: null },
                    ],
                },
            }]);
        } else if (type === 'dictionarySetValueByKey') {
            setNodes(ns => [...ns, {
                id,
                type: 'dictionarySetValueByKey',
                position,
                data: {
                    label: extra.label ?? 'Dictionary Set Value by Key',
                    required_inputs: [
                        { key: 'dictionary', type: 'dictionary', value: null },
                        { key: 'key', type: 'string', value: '' },
                        { key: 'value', type: 'any', value: null },
                    ],
                },
            }]);
        } else if (type === 'readDocumentProperty') {
            setNodes(ns => [...ns, {
                id,
                type: 'readDocumentProperty',
                position,
                data: {
                    label: extra.label ?? 'Read Document Property',
                    output_value_type: 'string',
                    required_inputs: [
                        { key: 'target_property', type: 'string', value: '' },
                        { key: 'document', type: 'document', value: null },
                    ],
                },
            }]);
        } else if (type === 'loadDocument') {
            setNodes(ns => [...ns, {
                id,
                type: 'loadDocument',
                position,
                data: {
                    label: extra.label ?? 'Load Document',
                    required_inputs: [
                        { key: 'document_id', type: 'string', value: null },
                        { key: 'document_name', type: 'string', value: null },
                    ],
                },
            }]);
        } else if (type === 'upsertDocument') {
            const tmpl = extra?.template === 'text_only';
            setNodes(ns => [...ns, {
                id,
                type: 'upsertDocument',
                position,
                data: {
                    label: typeof extra.label === 'string' && extra.label.trim() !== '' ? extra.label : tmpl ? 'Save text as Document' : 'Upsert Document',
                    required_inputs: tmpl
                        ? [
                              { key: 'name', type: 'string', value: '' },
                              { key: 'content', type: 'string', value: '' },
                          ]
                        : [
                              { key: 'name', type: 'string', value: '' },
                              { key: 'content', type: 'string', value: '' },
                              { key: 'existing_document_id', type: 'string', value: null },
                              { key: 'write_mode', type: 'string', value: 'replace' },
                          ],
                },
            }]);
        } else if (type === 'parseDocumentBody') {
            setNodes(ns => [...ns, {
                id,
                type: 'parseDocumentBody',
                position,
                data: {
                    label: extra.label ?? 'Parse Document Body',
                    required_inputs: [{ key: 'document', type: 'document', value: null }],
                },
            }]);
        } else if (type === 'htmlParseBasic') {
            setNodes(ns => [...ns, {
                id,
                type: 'htmlParseBasic',
                position,
                data: {
                    label: extra.label ?? 'HTML Parse (basic)',
                    required_inputs: [{ key: 'html', type: 'string', value: null }],
                },
            }]);
        } else if (type === 'writeObjectToDocumentBody') {
            setNodes(ns => [...ns, {
                id,
                type: 'writeObjectToDocumentBody',
                position,
                data: {
                    label: extra.label ?? 'Write Object to Document Body',
                    required_inputs: [{ key: 'value', type: 'any', value: null }],
                },
            }]);
        } else if (type === 'appendValueToDocument') {
            setNodes(ns => [...ns, {
                id,
                type: 'appendValueToDocument',
                position,
                data: {
                    label: extra.label ?? 'Append Value to Document',
                    required_inputs: [
                        { key: 'document', type: 'document', value: null },
                        { key: 'value', type: 'any', value: null },
                    ],
                },
            }]);
        } else if (type === 'validateAgainstStructure') {
            setNodes(ns => [...ns, {
                id,
                type: 'validateAgainstStructure',
                position,
                data: {
                    label: extra.label ?? 'Validate Against Structure',
                    structure_id: null,
                    required_inputs: [
                        { key: 'value', type: 'any', value: null },
                        { key: 'structure', type: 'structure', value: null },
                    ],
                },
            }]);
        } else if (type === 'addToList') {
            setNodes(ns => [...ns, {
                id,
                type: 'addToList',
                position,
                data: {
                    label: extra.label ?? 'Add to List',
                    required_inputs: [
                        { key: 'list', type: 'list', value: null },
                        { key: 'value', type: 'any', value: null },
                    ],
                },
            }]);
        } else if (type === 'addDays') {
            setNodes(ns => [...ns, {
                id,
                type: 'addDays',
                position,
                data: {
                    label: extra.label ?? 'Add days',
                    required_inputs: [
                        { key: 'input', type: 'datetime', value: null },
                        { key: 'days', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'addInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'addInts',
                position,
                data: {
                    label: extra.label ?? 'Add',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'subtractInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'subtractInts',
                position,
                data: {
                    label: extra.label ?? 'Subtract',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'multiplyInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'multiplyInts',
                position,
                data: {
                    label: extra.label ?? 'Multiply',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'divideInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'divideInts',
                position,
                data: {
                    label: extra.label ?? 'Divide',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'moduloInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'moduloInts',
                position,
                data: {
                    label: extra.label ?? 'Modulo',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'minInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'minInts',
                position,
                data: {
                    label: extra.label ?? 'Min',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'maxInts') {
            setNodes(ns => [...ns, {
                id,
                type: 'maxInts',
                position,
                data: {
                    label: extra.label ?? 'Max',
                    required_inputs: [
                        { key: 'input_a', type: 'int', value: 0 },
                        { key: 'input_b', type: 'int', value: 0 },
                    ],
                },
            }]);
        } else if (type === 'stop') {
            setNodes(ns => [
                ...ns,
                {
                    id,
                    type: 'stop',
                    position,
                    data: {
                        label: extra.label ?? 'Stop',
                        required_outputs: [{ key: 'output', type: 'string' }],
                        stop_priority: 0,
                    },
                },
            ]);
        } else if (type === 'annotationNote') {
            const ex = extra as {
                label?: string;
                text?: string;
                color?: string | null;
                width?: number;
                height?: number;
                label_font_size_px?: number;
                content_font_size_px?: number;
                z_index?: number;
            };
            const w =
                typeof ex.width === 'number' && Number.isFinite(ex.width) ? ex.width : ANNOTATION_NOTE_DEFAULT_WIDTH;
            const h =
                typeof ex.height === 'number' && Number.isFinite(ex.height) ? ex.height : ANNOTATION_NOTE_DEFAULT_HEIGHT;
            const ziNote = clampAnnotationNoteZIndex(ex.z_index);
            setNodes(ns => [
                ...ns,
                {
                    id,
                    type: 'annotationNote',
                    position,
                    zIndex: ziNote,
                    selectable: true,
                    connectable: false,
                    style: { width: w, height: h },
                    data: {
                        label: ex.label ?? 'Note',
                        text: typeof ex.text === 'string' ? ex.text : '',
                        color: ex.color ?? null,
                        label_font_size_px:
                            typeof ex.label_font_size_px === 'number' && Number.isFinite(ex.label_font_size_px)
                                ? ex.label_font_size_px
                                : ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
                        content_font_size_px:
                            typeof ex.content_font_size_px === 'number' && Number.isFinite(ex.content_font_size_px)
                                ? ex.content_font_size_px
                                : 12,
                        width: w,
                        height: h,
                        z_index: ziNote,
                    },
                },
            ]);
        } else if (type === 'annotationRegion') {
            const ex = extra as {
                label?: string;
                width?: number;
                height?: number;
                color?: string | null;
                z_index?: number;
                label_font_size_px?: number;
            };
            const w = typeof ex.width === 'number' && Number.isFinite(ex.width) ? ex.width : 400;
            const h = typeof ex.height === 'number' && Number.isFinite(ex.height) ? ex.height : 280;
            const lf =
                typeof ex.label_font_size_px === 'number' && Number.isFinite(ex.label_font_size_px)
                    ? ex.label_font_size_px
                    : 11;
            const zi = clampAnnotationRegionZIndex(ex.z_index);
            setNodes(ns => [
                ...ns,
                {
                    id,
                    type: 'annotationRegion',
                    position,
                    zIndex: zi,
                    selectable: true,
                    connectable: false,
                    style: { width: w, height: h },
                    data: {
                        label: ex.label ?? 'Region',
                        color: ex.color ?? null,
                        width: w,
                        height: h,
                        label_font_size_px: lf,
                        z_index: zi,
                    },
                },
            ]);
        } else if (type === 'workflowRef') {
            if (extra.workflow_id === activeWf?.id) {
                return;
            }
            const droppedWfId = String(extra.workflow_id ?? '').trim();
            setNodes(ns => [...ns, {
                id,
                type: 'workflowRef',
                position,
                data: {
                    label: extra.workflow_name ?? 'Workflow',
                    workflow_id: extra.workflow_id ?? '',
                },
            }]);
            if (droppedWfId.length > 0) {
                if (!workflowPrefetchInFlightRef.current.has(droppedWfId)) {
                    workflowPrefetchInFlightRef.current.add(droppedWfId);
                    void ApiClient.getWorkflow(droppedWfId)
                        .then(full => {
                            setWorkflows(ws => mergeWorkflowDefinitionIntoList(ws, full));
                        })
                        .finally(() => {
                            workflowPrefetchInFlightRef.current.delete(droppedWfId);
                        });
                }
            }
        }
    }, [activeWf?.id, recordGraphBeforeMutation]);

    const handleExposeCustomSkillChange = useCallback(
        async (value: boolean) => {
            if (!activeWf) return;
            try {
                const updated = await ApiClient.updateWorkflow(activeWf.id, { expose_as_custom_skill: value });
                setActiveWf(updated);
                setLastSavedWf(prev => (prev?.id === updated.id ? updated : prev));
                setWorkflows(ws => ws.map(w => (w.id === updated.id ? updated : w)));
                if (value) setIsCustomSkillsOpen(true);
            } catch {
                /* surface via toast if needed */
            }
        },
        [activeWf, setIsCustomSkillsOpen],
    );

    const patchGraphExecutionLimits = useCallback((next: WorkflowExecutionLimitsOverrides | null) => {
        setActiveWf(prev => {
            if (!prev?.graph) return prev;
            return {
                ...prev,
                graph: {
                    ...prev.graph,
                    execution_limits: next == null ? null : next,
                },
            };
        });
    }, []);

    // Save
    const handleSave = async () => {
        if (!activeWf) return;
        setIsSaving(true);
        setSaveError(null);
        try {
            const nodesToSave = resolveWorkflowRefLabels(nodes, workflows);
            const prevGraph = activeWf.graph ?? { nodes: [], edges: [] };
            const rawLimits = prevGraph.execution_limits;
            let nextLimits: WorkflowExecutionLimitsOverrides | null | undefined;
            if (rawLimits === null) nextLimits = null;
            else if (rawLimits === undefined) nextLimits = undefined;
            else nextLimits = nonEmptyWorkflowExecutionLimits(rawLimits) ?? null;
            const graph: WorkflowGraph = {
                ...prevGraph,
                nodes: nodesToSave.map(flowNodeToApp),
                edges: edges.map(flowEdgeToApp),
            };
            if (nextLimits === undefined) {
                delete graph.execution_limits;
            } else {
                graph.execution_limits = nextLimits;
            }
            /** If the workflow references a deleted or unknown project, fall back to Shared (backend also coerces invalid ids). */
            const rawPid = activeWf.project_id ?? null;
            let resolvedProjectId: string | null = rawPid;
            if (rawPid != null && !workflowProjects.some(p => p.id === rawPid)) {
                resolvedProjectId = sharedProjectId ?? null;
            }
            const updated = await ApiClient.updateWorkflow(activeWf.id, {
                name: activeWf.name,
                description: activeWf.description,
                palette_id: activeWf.palette_id ?? null,
                project_id: resolvedProjectId,
                expose_as_custom_skill: activeWf.expose_as_custom_skill ?? false,
                graph,
            });
            setActiveWf(updated);
            setLastSavedWf(updated);
            setWorkflows(ws => ws.map(w => (w.id === updated.id ? updated : w)));
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setSaveError(msg);
            throw err;
        } finally {
            setIsSaving(false);
        }
    };

    // Tracking dirty state
    useEffect(() => {
        if (!activeWf || !lastSavedWf || activeWf.id !== lastSavedWf.id) {
            setIsDirty(false);
            return;
        }
        const savedNodesStr = JSON.stringify(lastSavedWf.graph.nodes);
        const savedEdgesStr = JSON.stringify(lastSavedWf.graph.edges);
        const nodesForCompare = resolveWorkflowRefLabels(nodes, workflows);
        const currNodesStr = JSON.stringify(nodesForCompare.map(flowNodeToApp));
        const currEdgesStr = JSON.stringify(edges.map(flowEdgeToApp));
        const limitsDirty =
            stableGraphLimitsSnapshot(activeWf.graph.execution_limits) !==
            stableGraphLimitsSnapshot(lastSavedWf.graph.execution_limits);
        const graphDirty =
            savedNodesStr !== currNodesStr || savedEdgesStr !== currEdgesStr || limitsDirty;
        const metaDirty =
            activeWf.name !== lastSavedWf.name ||
            (activeWf.palette_id ?? null) !== (lastSavedWf.palette_id ?? null) ||
            (activeWf.project_id ?? null) !== (lastSavedWf.project_id ?? null) ||
            (activeWf.expose_as_custom_skill ?? false) !== (lastSavedWf.expose_as_custom_skill ?? false);
        setIsDirty(graphDirty || metaDirty);
    }, [nodes, edges, activeWf, lastSavedWf, workflows]);

    useEffect(() => {
        setUnsavedChanges?.(isDirty);
    }, [isDirty, setUnsavedChanges]);

    useEffect(() => {
        if (requestSave && requestSave > 0) {
            handleSave().then(() => onSaved?.());
        }
    }, [requestSave]);

    useEffect(() => {
        setOutputOverrides({});
    }, [activeWf?.id]);

    const handleTranscribeTalk = useCallback(async () => {
        if (transcribeCapture == null) return;
        setTranscribeError(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            transcribeMediaStreamRef.current = stream;
            const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MediaRecorder.isTypeSupported('audio/webm')
                  ? 'audio/webm'
                  : '';
            const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
            transcribeMediaRecorderRef.current = rec;
            transcribeChunksRef.current = [];
            rec.ondataavailable = e => {
                if (e.data.size > 0) transcribeChunksRef.current.push(e.data);
            };
            rec.onerror = () => {
                setTranscribeError('Recording failed');
                setTranscribeUi('error');
            };
            rec.start();
            setTranscribeUi('recording');
        } catch (e) {
            const msg = e instanceof Error ? e.message : 'Microphone not available';
            setTranscribeError(msg);
            setTranscribeUi('error');
        }
    }, [transcribeCapture]);

    const handleTranscribeStop = useCallback(async () => {
        const rec = transcribeMediaRecorderRef.current;
        const cap = transcribeCapture;
        if (rec == null || cap == null) return;
        if (rec.state === 'inactive') return;
        setTranscribeUi('uploading');
        rec.onstop = () => {
            void (async () => {
                transcribeMediaStreamRef.current?.getTracks().forEach(t => t.stop());
                transcribeMediaStreamRef.current = null;
                transcribeMediaRecorderRef.current = null;
                const blob = new Blob(transcribeChunksRef.current, { type: rec.mimeType || 'audio/webm' });
                transcribeChunksRef.current = [];
                try {
                    await ApiClient.postWorkflowTranscribeAudio(cap.runId, {
                        nodeId: cap.nodeId,
                        forLoopId: cap.forLoopId,
                        forLoopIteration: cap.forLoopIteration,
                        blob,
                        filename: 'recording.webm',
                    });
                    setTranscribeCapture(null);
                    setTranscribeUi('idle');
                    setTranscribeError(null);
                } catch (err) {
                    const msg = err instanceof Error ? err.message : String(err);
                    setTranscribeError(msg);
                    setTranscribeUi('error');
                }
            })();
        };
        rec.stop();
    }, [transcribeCapture]);

    const handleAudioFileInputRuntimeFile = useCallback(async (file: File | null) => {
        const cap = audioFileInputCapture;
        if (file == null || cap == null) return;
        setAudioFileInputUploading(true);
        setAudioFileInputError(null);
        try {
            await ApiClient.postWorkflowAudioFileInput(cap.runId, {
                nodeId: cap.nodeId,
                forLoopId: cap.forLoopId,
                forLoopIteration: cap.forLoopIteration,
                file,
            });
            setAudioFileInputCapture(null);
            setAudioFileInputError(null);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setAudioFileInputError(msg);
            workflowRunAbortRef.current?.abort();
            const failedNodeResult: NodeRunResult = {
                node_id: cap.nodeId,
                status: 'error',
                error: msg,
                latency_ms: 0,
                details: {
                    resolved_inputs: {
                        filename: file.name,
                        size_bytes: file.size,
                        mime_type: file.type || 'application/octet-stream',
                        source_type: 'audio_file',
                    },
                },
            };
            setLastRunNodeData(prev => ({ ...prev, [cap.nodeId]: failedNodeResult }));
            setRunResult(prev => {
                const nodeResults = prev?.node_results ?? [];
                const nextStep = Math.max(0, ...nodeResults.map(r => r.step_number ?? 0)) + 1;
                const withStep = { ...failedNodeResult, step_number: nextStep };
                return {
                    workflow_id: prev?.workflow_id ?? activeWf?.id ?? '',
                    run_id: prev?.run_id,
                    status: 'error',
                    node_results: [...nodeResults.filter(r => r.node_id !== cap.nodeId), withStep],
                    error: msg,
                };
            });
        } finally {
            setAudioFileInputUploading(false);
        }
    }, [activeWf?.id, audioFileInputCapture]);

    const handleTranscribeFileRuntimeFile = useCallback(async (file: File | null) => {
        const cap = transcribeFileCapture;
        if (file == null || cap == null) return;
        setTranscribeFileUploading(true);
        setTranscribeFileError(null);
        try {
            await ApiClient.postWorkflowTranscribeFileInput(cap.runId, {
                nodeId: cap.nodeId,
                forLoopId: cap.forLoopId,
                forLoopIteration: cap.forLoopIteration,
                file,
            });
            setTranscribeFileCapture(null);
            setTranscribeFileError(null);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setTranscribeFileError(msg);
            workflowRunAbortRef.current?.abort();
            const failedNodeResult: NodeRunResult = {
                node_id: cap.nodeId,
                status: 'error',
                error: msg,
                latency_ms: 0,
                details: {
                    resolved_inputs: {
                        filename: file.name,
                        size_bytes: file.size,
                        mime_type: file.type || 'application/octet-stream',
                        source_type: 'transcribe_file',
                    },
                },
            };
            setLastRunNodeData(prev => ({ ...prev, [cap.nodeId]: failedNodeResult }));
            setRunResult(prev => {
                const nodeResults = prev?.node_results ?? [];
                const nextStep = Math.max(0, ...nodeResults.map(r => r.step_number ?? 0)) + 1;
                const withStep = { ...failedNodeResult, step_number: nextStep };
                return {
                    workflow_id: prev?.workflow_id ?? activeWf?.id ?? '',
                    run_id: prev?.run_id,
                    status: 'error',
                    node_results: [...nodeResults.filter(r => r.node_id !== cap.nodeId), withStep],
                    error: msg,
                };
            });
        } finally {
            setTranscribeFileUploading(false);
        }
    }, [activeWf?.id, transcribeFileCapture]);

    const handleCancelRun = useCallback(async () => {
        const rid = lastRunId;
        if (!rid) return;
        try {
            await ApiClient.cancelWorkflowRun(rid);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            showStatusToast(msg, true);
        }
    }, [lastRunId, showStatusToast]);

    const doRun = async (inputOverrides?: Record<string, any>) => {
        if (!activeWf) return;
        workflowRunAbortRef.current?.abort();
        const runAbort = new AbortController();
        workflowRunAbortRef.current = runAbort;
        workflowStreamSeqRef.current = 0;
        const runLim = nonEmptyWorkflowExecutionLimits(runExecutionLimitsOverrides);
        setInspectorTab('logs');
        setIsRunning(true);
        setRunResult(null);
        setRunningNodeIds(new Set());

        try {
            let acknowledgePreflight = false;
            for (;;) {
                try {
                    await ApiClient.runWorkflowStream(activeWf.id, (rawEvent: any) => {
                    const incomingSeq = typeof rawEvent.seq === 'number' ? rawEvent.seq : undefined;
                    if (
                        incomingSeq !== undefined &&
                        incomingSeq <= workflowStreamSeqRef.current
                    ) {
                        return;
                    }
                    if (incomingSeq !== undefined) {
                        workflowStreamSeqRef.current = Math.max(
                            workflowStreamSeqRef.current,
                            incomingSeq,
                        );
                    }
                    const event = rawEvent;
                    if (event.event === "start") {
                        ttsAfterWorkflowQueueRef.current = [];
                        ttsAutoplayChainRef.current = Promise.resolve();
                        setLastRunNodeData({});
                        setLastRunId(event.run_id ?? null);
                        setIsLastRunOpen(true);
                        setRunResult({ workflow_id: activeWf.id, status: 'running' as any, node_results: [] });
                    } else if (event.event === "node_start") {
                        setRunningNodeIds(prev => {
                            const next = new Set(prev);
                            next.add(String(event.node_id));
                            return next;
                        });
                    } else if (event.event === "input_required" && event.kind === "transcribe_audio") {
                        setTranscribeCapture({
                            runId: String(event.run_id),
                            nodeId: String(event.node_id),
                            forLoopId:
                                event.for_loop_id != null && String(event.for_loop_id).trim() !== ''
                                    ? String(event.for_loop_id)
                                    : null,
                            forLoopIteration:
                                typeof event.for_loop_iteration === "number" ? event.for_loop_iteration : 0,
                        });
                        setTranscribeUi("idle");
                        setTranscribeError(null);
                    } else if (event.event === "input_required" && event.kind === "audio_file_input") {
                        setAudioFileInputCapture({
                            runId: String(event.run_id),
                            nodeId: String(event.node_id),
                            forLoopId:
                                event.for_loop_id != null && String(event.for_loop_id).trim() !== ''
                                    ? String(event.for_loop_id)
                                    : null,
                            forLoopIteration:
                                typeof event.for_loop_iteration === "number" ? event.for_loop_iteration : 0,
                        });
                        setAudioFileInputUploading(false);
                        setAudioFileInputError(null);
                    } else if (event.event === "input_required" && event.kind === "transcribe_file") {
                        setTranscribeFileCapture({
                            runId: String(event.run_id),
                            nodeId: String(event.node_id),
                            forLoopId:
                                event.for_loop_id != null && String(event.for_loop_id).trim() !== ''
                                    ? String(event.for_loop_id)
                                    : null,
                            forLoopIteration:
                                typeof event.for_loop_iteration === "number" ? event.for_loop_iteration : 0,
                        });
                        setTranscribeFileUploading(false);
                        setTranscribeFileError(null);
                    } else if (event.event === "node_end") {
                        const nodeResult: NodeRunResult = event.result;
                        const handledTcRaw = (event as { handled_by_try_catch?: unknown }).handled_by_try_catch;
                        const handledTc =
                            typeof handledTcRaw === 'string' && handledTcRaw.trim() !== ''
                                ? handledTcRaw.trim()
                                : null;
                        if (handledTc && nodeResult.status === 'error') {
                            showStatusToast(
                                `Handled by Try / Catch (${handledTc}); see Run logs for the failed step.`,
                            );
                        }
                        const ttsFlowNode = nodes.find(
                            nn => nn.id === nodeResult.node_id && nn.type === 'textToSpeech',
                        );
                        const ttsNodeData = ttsFlowNode?.data as Record<string, unknown> | undefined;
                        const playbackWhen: TtsPlaybackWhen = resolveTtsPlaybackWhen(
                            user?.settings as Record<string, unknown> | undefined,
                            ttsNodeData,
                        );
                        const hasAudio =
                            nodeResult.status === 'ok' && isPlayableTtsAudioOutput(nodeResult.output);
                        const audioOut = hasAudio
                            ? (nodeResult.output as { kind: 'audio'; audio_base64: string; mime_type?: string })
                            : null;
                        if (audioOut && playbackWhen === 'after_workflow') {
                            const mime =
                                typeof audioOut.mime_type === 'string' && audioOut.mime_type
                                    ? audioOut.mime_type
                                    : 'audio/wav';
                            ttsAfterWorkflowQueueRef.current.push({
                                audio_base64: audioOut.audio_base64,
                                mime_type: mime,
                                step_number: nodeResult.step_number ?? 0,
                                node_id: nodeResult.node_id,
                            });
                        } else if (audioOut && playbackWhen === 'inline') {
                            const mime =
                                typeof audioOut.mime_type === 'string' && audioOut.mime_type
                                    ? audioOut.mime_type
                                    : 'audio/wav';
                            ttsAutoplayChainRef.current = ttsAutoplayChainRef.current.then(async () => {
                                try {
                                    await playTtsAudioFromBase64(audioOut.audio_base64, mime);
                                } catch (e) {
                                    console.warn(
                                        'TTS auto-play failed',
                                        e instanceof Error ? `${e.name}: ${e.message}` : String(e),
                                        e,
                                    );
                                    const isNotAllowed =
                                        e instanceof DOMException && e.name === 'NotAllowedError';
                                    showStatusToast(
                                        isNotAllowed ?
                                            'Browser blocked auto-play — use the audio control or Download in Run logs.'
                                        :   'Could not play TTS audio',
                                        true,
                                    );
                                }
                            });
                        }
                        setLastRunNodeData(prev => {
                            const cur = prev[nodeResult.node_id];
                            const nextEntry = mergeLastRunNodeResult(cur, nodeResult);
                            if (nextEntry === cur) {
                                return prev;
                            }
                            return { ...prev, [nodeResult.node_id]: nextEntry };
                        });
                        setRunResult(prev => {
                            if (!prev) return prev;
                            return { ...prev, node_results: [...prev.node_results, event.result] };
                        });
                        setRunningNodeIds(prev => {
                            const next = new Set(prev);
                            next.delete(nodeResult.node_id);
                            return next;
                        });
                    } else if (event.event === "end") {
                        const endResult = event.result;
                        setRunResult(endResult);
                        setRunningNodeIds(new Set());
                        const ok = endResult?.status === 'ok';
                        const pending = ttsAfterWorkflowQueueRef.current;
                        if (ok && pending.length > 0) {
                            const sorted = sortTtsQueuedClips(pending);
                            ttsAfterWorkflowQueueRef.current = [];
                            for (const clip of sorted) {
                                ttsAutoplayChainRef.current = ttsAutoplayChainRef.current.then(async () => {
                                    try {
                                        await playTtsAudioFromBase64(clip.audio_base64, clip.mime_type);
                                    } catch (e) {
                                        console.warn(
                                            'TTS queued playback failed',
                                            e instanceof Error ? `${e.name}: ${e.message}` : String(e),
                                            e,
                                        );
                                        const isNotAllowed =
                                            e instanceof DOMException && e.name === 'NotAllowedError';
                                        showStatusToast(
                                            isNotAllowed ?
                                                'Browser blocked auto-play — use the audio control or Download in Run logs.'
                                            :   'Could not play TTS audio',
                                            true,
                                        );
                                    }
                                });
                            }
                        } else {
                            ttsAfterWorkflowQueueRef.current = [];
                        }
                    } else if (event.event === "canceled") {
                        ttsAfterWorkflowQueueRef.current = [];
                        ttsAutoplayChainRef.current = Promise.resolve();
                        setRunningNodeIds(new Set());
                        setRunResult(prev => ({
                            workflow_id: activeWf.id,
                            status: 'canceled',
                            node_results: prev?.node_results ?? [],
                            error: 'Workflow run canceled',
                        }));
                    } else if (event.event === "error") {
                        ttsAfterWorkflowQueueRef.current = [];
                        ttsAutoplayChainRef.current = Promise.resolve();
                        setRunningNodeIds(new Set());
                        setRunResult({ workflow_id: activeWf.id, status: 'error', node_results: [], error: event.error } as any);
                        console.error("Workflow Execution Error", event.error);
                    }
                },
                {
                    ...(inputOverrides ? { input_overrides: inputOverrides } : {}),
                    ...(Object.keys(outputOverrides).length > 0 ? { output_overrides: outputOverrides } : {}),
                    ...(runLim ? { execution_limits: runLim } : {}),
                    execution_time_zone: resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined),
                    signal: runAbort.signal,
                    ...(acknowledgePreflight ? { acknowledge_preflight_warnings: true } : {}),
                },
            );
                    break;
                } catch (preErr: unknown) {
                    const detail = getApiErrorDetailObject((preErr as Error & { apiBody?: unknown }).apiBody);
                    if (
                        !acknowledgePreflight &&
                        detail &&
                        detail.error === 'preflight_warnings' &&
                        typeof window !== 'undefined' &&
                        window.confirm(
                            typeof detail.message === 'string'
                                ? `${detail.message}\n\nProceed with this run?`
                                : 'This run may exceed safe execution limits or uses uncertain estimates. Proceed?',
                        )
                    ) {
                        acknowledgePreflight = true;
                        continue;
                    }
                    throw preErr;
                }
            }
        } catch (err: any) {
            ttsAfterWorkflowQueueRef.current = [];
            ttsAutoplayChainRef.current = Promise.resolve();
            console.error(err);
            const msg = err instanceof Error ? err.message : String(err);
            setRunResult({ workflow_id: activeWf.id, status: 'error', node_results: [], error: msg } as any);
        } finally {
            const r = transcribeMediaRecorderRef.current;
            if (r && r.state !== "inactive") {
                r.onstop = null;
                r.stop();
            }
            transcribeMediaStreamRef.current?.getTracks().forEach(t => t.stop());
            transcribeMediaStreamRef.current = null;
            transcribeMediaRecorderRef.current = null;
            transcribeChunksRef.current = [];
            setTranscribeCapture(null);
            setTranscribeUi("idle");
            setTranscribeError(null);
            setIsRunning(false);
            setRunningNodeIds(new Set());
            if (workflowRunAbortRef.current === runAbort) {
                workflowRunAbortRef.current = null;
            }
        }
    };

    const clearRunInputWizard = () => {
        setRunInputWizard(null);
        setRunWizardStepDraft(null);
        setRunWizardListDictRaw('');
    };

    const handleRun = async () => {
        if (!activeWf) return;
        await handleSave();

        const startNode = nodes.find(n => n.type === 'start');
        const rawInputs = (startNode?.data as any)?.required_inputs;
        const inputs = normalizeStartInputsForRun(rawInputs, (startNode?.data as any)?.text);
        const missing = missingStartInputsForRun(inputs);

        if (inputs.length > 0 && missing.length > 0) {
            setRunInputWizard({ queue: missing, index: 0, overrides: {} });
            return;
        }

        await doRun();
    };

    const handleRunWizardPrimary = () => {
        if (!runInputWizard) return;
        const inp = runInputWizard.queue[runInputWizard.index];
        let value: unknown;
        if (inp.type === 'list' || inp.type === 'dictionary') {
            const parsed = parseRunWizardListOrDictJson(inp.type, runWizardListDictRaw);
            if (parsed == null || !isValidRunWizardDraft(inp.type, parsed)) return;
            value = draftValueToOverride(inp.type, parsed);
        } else if (inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure') {
            const parsed = parseRunWizardAnyJson(runWizardListDictRaw);
            if (parsed === undefined || !isValidRunWizardDraft(inp.type, parsed)) return;
            value = draftValueToOverride(inp.type, parsed);
        } else {
            if (!isValidRunWizardDraft(inp.type, runWizardStepDraft)) return;
            value = draftValueToOverride(inp.type, runWizardStepDraft);
        }
        const nextOverrides = { ...runInputWizard.overrides, [inp.key]: value };
        const isLast = runInputWizard.index >= runInputWizard.queue.length - 1;
        if (isLast) {
            clearRunInputWizard();
            void doRun(nextOverrides);
            return;
        }
        setRunInputWizard({
            queue: runInputWizard.queue,
            index: runInputWizard.index + 1,
            overrides: nextOverrides,
        });
    };

    const handleRunWizardBack = () => {
        setRunInputWizard(prev => {
            if (!prev || prev.index <= 0) return prev;
            return { ...prev, index: prev.index - 1 };
        });
    };

    // Animate edges and nodes during run
    useEffect(() => {
        const completedNodeIds = runResult?.node_results.map(r => r.node_id) || [];

        setEdges(es => es.map(e => {
            // An edge is animated if we're running AND its source hasn't completed yet.
            const isSourceCompleted = completedNodeIds.includes(e.source);
            const shouldAnimate = isRunning ? !isSourceCompleted : false;
            
            return {
                ...e,
                animated: shouldAnimate
            };
        }));
        
        setNodes(ns => ns.map(n => ({
            ...n,
            data: { ...n.data, isRunning: runningNodeIds.has(n.id) },
        })));
    }, [isRunning, runningNodeIds, runResult]);

    // Delete
    const handleDeleteWf = async () => {
        if (!activeWf || !deletingWfId) return;
        try {
            await ApiClient.deleteWorkflow(activeWf.id);
            closeActiveWorkflowSession();
            onSyncWorkflowPath?.(null);
            setDeletingWfId(null);
            await refreshWorkflowLists();
        } catch (err) {
            console.error("Failed to delete workflow:", err);
        }
    };

    // Right-panel value node editor (text fields: onFocus → recordGraphBeforeMutation, onChange → patch only)
    const patchSelectedNodeData = (patch: Record<string, any>, deleteKeys?: string[]) => {
        if (!selectedNode) return;
        const merge = (data: Record<string, any>) => {
            const next = { ...data, ...patch };
            if (deleteKeys?.length) {
                for (const k of deleteKeys) {
                    delete next[k];
                }
            }
            return next;
        };
        setNodes(ns => ns.map(n => (n.id === selectedNode.id ? { ...n, data: merge(n.data as Record<string, any>) } : n)));
    };

    const updateSelectedNodeData = (patch: Record<string, any>, deleteKeys?: string[]) => {
        recordGraphBeforeMutation();
        patchSelectedNodeData(patch, deleteKeys);
    };

    const bumpSelectedAnnotationZIndex = (delta: number) => {
        if (!selectedNode) return;
        if (selectedNode.type !== 'annotationNote' && selectedNode.type !== 'annotationRegion') return;
        recordGraphBeforeMutation();
        const id = selectedNode.id;
        const applyBump = (n: Node) => {
            if (n.type === 'annotationNote') {
                const cur =
                    typeof n.zIndex === 'number' && Number.isFinite(n.zIndex)
                        ? n.zIndex
                        : clampAnnotationNoteZIndex((n.data as { z_index?: number }).z_index);
                const next = Math.min(
                    ANNOTATION_NOTE_Z_INDEX_MAX,
                    Math.max(ANNOTATION_NOTE_Z_INDEX_MIN, Math.round(cur + delta)),
                );
                return { ...n, zIndex: next, data: { ...(n.data as object), z_index: next } };
            }
            if (n.type === 'annotationRegion') {
                const cur =
                    typeof n.zIndex === 'number' && Number.isFinite(n.zIndex)
                        ? n.zIndex
                        : clampAnnotationRegionZIndex((n.data as { z_index?: number }).z_index);
                const next = Math.min(
                    ANNOTATION_REGION_Z_INDEX_MAX,
                    Math.max(ANNOTATION_REGION_Z_INDEX_MIN, Math.round(cur + delta)),
                );
                return { ...n, zIndex: next, data: { ...(n.data as object), z_index: next } };
            }
            return n;
        };
        setNodes(ns => ns.map(n => (n.id === id ? applyBump(n) : n)));
    };

    const handleConfirmPendingNodeDelete = useCallback(() => {
        if (!pendingNodeDelete) return;
        recordGraphBeforeMutation();
        const idSet = new Set(pendingNodeDelete.ids);
        setNodes(ns => ns.filter(n => !idSet.has(n.id)).map(n => ({ ...n, selected: false })));
        setEdges(es => es.filter(e => !idSet.has(e.source) && !idSet.has(e.target)));
        setPendingNodeDelete(null);
    }, [pendingNodeDelete, recordGraphBeforeMutation]);

    const handleDeleteEdge = () => {
        if (!selectedEdge) return;
        recordGraphBeforeMutation();
        const edge = selectedEdge;
        if (edge.sourceHandle === 'signal_out' && edge.targetHandle === 'trigger') {
            setNodes(ns => applyForLoopEndClearOnEdgeRemoved(ns, [edge]));
        }
        setEdges(es => es.filter(e => e.id !== selectedEdge.id));
        setSelectedEdge(null);
        setDeletingEdgeId(null);
    };

    useEffect(() => {
        if (!nodeDeleteKeyboardMessage) return;
        const t = window.setTimeout(() => setNodeDeleteKeyboardMessage(null), 4500);
        return () => clearTimeout(t);
    }, [nodeDeleteKeyboardMessage]);

    useEffect(() => {
        if (!pendingNodeDelete) return;
        const id = requestAnimationFrame(() => {
            nodeDeleteConfirmRef.current?.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'nearest',
            });
        });
        return () => cancelAnimationFrame(id);
    }, [pendingNodeDelete]);

    useEffect(() => {
        setPendingNodeDelete(pd => {
            if (!pd) return null;
            const sel = new Set(selectedCanvasNodes.map(n => n.id));
            return pd.ids.every(id => sel.has(id)) ? pd : null;
        });
    }, [selectedCanvasNodes]);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (!activeWf) return;

            const panelArrow = immersivePanelArrowShortcutResult({
                immersive: Boolean(immersive),
                targetIsTextEntry: eventTargetIsTextEntry(e.target),
                runInputWizardOpen: runInputWizard != null,
                workflowImportModalOpen,
                outputOverrideModalOpen,
                compactPaletteOpen,
                compactExplorerOpen,
                event: e,
            });
            if (panelArrow) {
                e.preventDefault();
                setCompactPaletteOpen(panelArrow.nextPaletteOpen);
                setCompactExplorerOpen(panelArrow.nextExplorerOpen);
                return;
            }

            const zLetter = e.key === 'z' || e.key === 'Z';
            if ((e.metaKey || e.ctrlKey) && zLetter && !e.altKey) {
                if (eventTargetIsTextEntry(e.target)) return;
                if (e.shiftKey) {
                    if (redoGraph()) e.preventDefault();
                } else {
                    if (undoGraph()) e.preventDefault();
                }
                return;
            }
            if (e.ctrlKey && !e.metaKey && (e.key === 'y' || e.key === 'Y') && !e.shiftKey && !e.altKey) {
                if (eventTargetIsTextEntry(e.target)) return;
                if (redoGraph()) e.preventDefault();
                return;
            }

            if (e.key === 'Escape') {
                if (pendingNodeDelete) {
                    e.preventDefault();
                    setPendingNodeDelete(null);
                    return;
                }
                if (deletingEdgeId) {
                    e.preventDefault();
                    setDeletingEdgeId(null);
                    return;
                }
                return;
            }

            if (!isKeyboardDeleteIntentKey(e)) return;
            if (eventTargetIsTextEntry(e.target)) return;

            if (pendingNodeDelete) return;

            if (selectedEdge) {
                e.preventDefault();
                setDeletingEdgeId(selectedEdge.id);
                setNodeDeleteKeyboardMessage(null);
                return;
            }

            if (selectedCanvasNodes.length === 0) return;

            const plan = planCanvasNodeDeletion(selectedCanvasNodes, nodes);
            if (!plan.ok) {
                e.preventDefault();
                setNodeDeleteKeyboardMessage(plan.reason);
                return;
            }
            e.preventDefault();
            setPendingNodeDelete({ ids: plan.ids, skippedStart: plan.skippedStart });
            setNodeDeleteKeyboardMessage(null);
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [
        activeWf,
        compactExplorerOpen,
        compactPaletteOpen,
        deletingEdgeId,
        immersive,
        nodes,
        outputOverrideModalOpen,
        pendingNodeDelete,
        redoGraph,
        runInputWizard,
        selectedCanvasNodes,
        selectedEdge,
        undoGraph,
        workflowImportModalOpen,
    ]);

    const explorerWorkflowOnly =
        inspectorTab === 'node' && !selectedNode && !selectedEdge && !multiCanvasSelectActive && activeWf != null;

    // ------------------------------------------------------------------ render
    if (isDataLoading) {
        return (
            <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                <Loader2 className="animate-spin" size={24} />
                <span>Loading workflows…</span>
            </div>
        );
    }

    return (
        <div className="flex h-full overflow-hidden relative">
            {/* No full-screen backdrop over the canvas: it used z-40 above the graph (z-0) and blocked
 drag-drop from the palette, pan/zoom, and node selection. Close slide-overs via toolbar
                toggles or an empty-canvas click (onPaneClick). */}

            {/* ==== Left panel ==== */}
            <div
                className={
                    overlayPanels
                        ? `absolute left-0 top-0 bottom-0 z-50 flex min-w-0 transition-transform duration-200 ease-out ${
                              compactPaletteOpen ? 'translate-x-0 pointer-events-auto' : '-translate-x-full pointer-events-none'
                          }`
                        : 'relative z-10 shrink-0 flex min-w-0'
                }
                style={overlayPanels ? { width: 'min(85vw, 22rem)' } : { width: panelWidths.left }}
            >
                <div className="flex-1 min-w-0 border-r border-mw-border bg-mw-sidebar flex flex-col min-h-0 overflow-y-auto">
                {/* Workflows */}
                <div className="p-3 border-b border-mw-border shrink-0">
                    <div className="flex items-center justify-between mb-2">
                        <button onClick={() => setIsWorkflowsOpen(!isWorkflowsOpen)} className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors">
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
                            <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
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
                                        <span className="shrink-0 text-xs text-mw-text-secondary tabular-nums">{workflowCountForProject(p)}</span>
                                    </button>
                                ))}
                                {displayedProjects.length === 0 && (
                                    <div className="text-xs text-mw-text-secondary text-center py-2">No projects yet</div>
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
                                <span className="text-xs font-semibold text-mw-text-primary truncate min-w-0 flex-1" title={selectedProject?.name ?? ''}>
                                    {selectedProject?.name ?? 'Project'}
                                </span>
                                <div className="flex items-center gap-0.5 shrink-0">
                                    <button
                                        type="button"
                                        id="import-workflow-json-btn"
                                        onClick={() => setWorkflowImportModalOpen(true)}
                                        className="p-1 text-mw-text-secondary hover:text-mw-primary hover:bg-mw-primary-muted rounded transition-colors"
                                        title="Import workflow JSON"
                                    >
                                        <Upload size={14} />
                                    </button>
                                    <button id="new-workflow-btn" onClick={createWorkflow} className="p-1 text-mw-primary hover:bg-mw-primary-muted rounded transition-colors" title="New Workflow"><Plus size={14} /></button>
                                    {selectedProject && (
                                        <WorkflowProjectDeleteControl
                                            projectName={selectedProject.name}
                                            workflowCount={selectedProjectDeleteWorkflowCount}
                                            disabled={!isDeletableProject(selectedProject)}
                                            onConfirmDelete={handleDeleteProject}
                                        />
                                    )}
                                </div>
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
                            <div className={`space-y-1 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                {filteredWorkflowsInProject.map(wf => {
                                    const wfColor = getHandleColor(paletteColors, 'workflow');
                                    return (
                                        <WorkflowPaletteWorkflowRow
                                            key={wf.id}
                                            workflow={wf}
                                            wfColor={wfColor}
                                            activeWorkflowId={activeWf?.id ?? null}
                                            draggable={activeWf?.id !== wf.id}
                                            onOpen={openWorkflow}
                                            moveProjectPickerFor={moveProjectPickerFor}
                                            onToggleMovePicker={id =>
                                                setMoveProjectPickerFor(prev => (prev === id ? null : id))
                                            }
                                            workflowProjects={workflowProjects}
                                            sharedProjectId={sharedProjectId}
                                            onMoveToProject={moveWorkflowToProject}
                                            onMoveComplete={() => setMoveProjectPickerFor(null)}
                                        />
                                    );
                                })}
                                {filteredWorkflowsInProject.length === 0 && (
                                    <div className="text-xs text-mw-text-secondary text-center py-2">
                                        {workflowsInSelectedProject.length === 0
                                            ? 'No workflows in this project'
                                            : workflowsInProjectDrillIn.length === 0
                                              ? 'All workflows in this project are listed under Custom Skills below.'
                                              : workflowNameFilter.trim()
                                                ? 'No matches'
                                                : 'No workflows in this project'}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                    </>
                    )}
                </div>

                <WorkflowPaletteStepSections
                    paletteColors={paletteColors}
                    mode="edit"
                    flowOpen={isFlowOpen}
                    onFlowOpenChange={setIsFlowOpen}
                    primitivesOpen={isPrimitivesOpen}
                    onPrimitivesOpenChange={setIsPrimitivesOpen}
                    skillsOpen={isSkillsOpen}
                    onSkillsOpenChange={setIsSkillsOpen}
                    customSkillWorkflows={customSkillWorkflows}
                    customSkillsOpen={isCustomSkillsOpen}
                    onCustomSkillsOpenChange={setIsCustomSkillsOpen}
                    activeWorkflowId={activeWf?.id ?? null}
                    onCustomSkillWorkflowOpen={openWorkflow}
                    moveProjectPickerFor={moveProjectPickerFor}
                    onToggleMoveProjectPicker={id =>
                        setMoveProjectPickerFor(prev => (prev === id ? null : id))
                    }
                    workflowProjects={workflowProjects}
                    sharedProjectId={sharedProjectId}
                    onMoveWorkflowToProject={moveWorkflowToProject}
                    onAfterMoveWorkflowFromPalette={() => setMoveProjectPickerFor(null)}
                    utilitiesOpen={isUtilitiesOpen}
                    onUtilitiesOpenChange={setIsUtilitiesOpen}
                    sandboxUtilitiesOpen={isSandboxUtilitiesOpen}
                    onSandboxUtilitiesOpenChange={setIsSandboxUtilitiesOpen}
                    controlsOpen={isControlsOpen}
                    onControlsOpenChange={setIsControlsOpen}
                    annotationsOpen={isAnnotationsOpen}
                    onAnnotationsOpenChange={setIsAnnotationsOpen}
                />
                </div>
                {!overlayPanels && (
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

            {/* ==== Canvas ==== */}
            <div
                className="relative z-0 flex-1 flex flex-col min-h-0"
                style={{ minWidth: overlayPanels ? 0 : CENTER_PANEL_MIN_PX }}
            >
                {/* Toolbar */}
                <div className="h-12 border-b border-mw-border bg-mw-card flex items-center px-2 sm:px-4 gap-2 sm:gap-3 shrink-0 min-w-0">
                    {activeWf ? (
                        <>
                            {overlayPanels && (
                                <>
                                    <button
                                        type="button"
                                        className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                        aria-label={compactPaletteOpen ? 'Close step palette' : 'Open step palette'}
                                        title="Palette"
                                        aria-pressed={compactPaletteOpen}
                                        onClick={() => {
                                            if (compactPaletteOpen) {
                                                setCompactPaletteOpen(false);
                                            } else {
                                                setCompactExplorerOpen(false);
                                                setCompactPaletteOpen(true);
                                            }
                                        }}
                                    >
                                        <PanelLeft size={18} />
                                    </button>
                                    {inspectorOpen && (
                                        <button
                                            type="button"
                                            className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                            aria-label={compactExplorerOpen ? 'Close Explorer' : 'Open Explorer'}
                                            title="Explorer"
                                            aria-pressed={compactExplorerOpen}
                                            onClick={() => {
                                                if (compactExplorerOpen) {
                                                    setCompactExplorerOpen(false);
                                                } else {
                                                    setCompactPaletteOpen(false);
                                                    setCompactExplorerOpen(true);
                                                }
                                            }}
                                        >
                                            <PanelRight size={18} />
                                        </button>
                                    )}
                                </>
                            )}
                            {onImmersiveChange && (
                                <button
                                    type="button"
                                    className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                    aria-label={immersive ? 'Exit fullscreen' : 'Enter fullscreen'}
                                    title={immersive ? 'Exit fullscreen' : 'Enter fullscreen'}
                                    aria-pressed={immersive}
                                    onClick={() => onImmersiveChange(!immersive)}
                                >
                                    {immersive ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                                </button>
                            )}
                            {immersive && onOpenMySettings && user && (
                                <button
                                    type="button"
                                    onClick={() => onOpenMySettings()}
                                    className="shrink-0 rounded-full focus:outline-none focus:ring-2 focus:ring-mw-primary focus:ring-offset-2 focus:ring-offset-mw-card"
                                    title="My Settings"
                                    aria-label="My Settings"
                                >
                                    <UserAvatar
                                        username={user.username}
                                        avatarUrl={user.settings?.avatar_url as string | undefined}
                                        size="sm"
                                    />
                                </button>
                            )}
                            <input 
                                value={activeWf.name} 
                                onChange={e => setActiveWf({ ...activeWf, name: e.target.value })} 
                                placeholder="Workflow Name"
                                className="text-sm font-semibold text-mw-text-primary truncate flex-1 min-w-0 bg-transparent border border-transparent hover:border-mw-border focus:border-mw-primary rounded px-2 py-1 transition-colors focus:outline-none focus:ring-1 focus:ring-mw-primary" 
                            />
                            <select
                                value={toolbarPaletteSelectValue}
                                onChange={e =>
                                    setActiveWf({ ...activeWf, palette_id: e.target.value || null })
                                }
                                className="text-xs px-2 py-1.5 border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                title="Palette"
                            >
                                <option value="">Default</option>
                                {paletteOptionsForToolbar.map(p => (
                                    <option key={p.id} value={p.id}>{p.name}</option>
                                ))}
                            </select>
                            {deletingWfId === activeWf.id ? (
                                <div className="flex items-center gap-1.5 ml-2">
                                    <span className="text-xs font-medium text-red-500">Delete?</span>
                                    <button onClick={handleDeleteWf} className="px-2 py-1 text-xs font-medium text-white bg-red-500 hover:bg-red-600 rounded shadow-sm transition-colors">Yes</button>
                                    <button onClick={() => setDeletingWfId(null)} className="px-2 py-1 text-xs font-medium text-mw-text-primary bg-mw-card-alt hover:opacity-90 rounded transition-colors">No</button>
                                </div>
                            ) : (
                                <button onClick={() => setDeletingWfId(activeWf.id)} className="p-1.5 text-mw-text-secondary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors" title="Delete Workflow">
                                    <Trash2 size={14} />
                                </button>
                            )}

                            <button
                                onClick={() => void handleSave()}
                                disabled={isSaving}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-mw-text-primary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50 ml-2"
                            >
                                <Save size={13} /> {isSaving ? 'Saving…' : 'Save'}
                            </button>
                            <button
                                type="button"
                                onClick={() => void handleExportBundleDownload()}
                                disabled={!activeWf || bundleExportBusy}
                                className="flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-mw-text-primary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50"
                                title="Download workflow bundle (nested workflows and referenced resources)"
                            >
                                <Download size={13} />
                                <span className="hidden sm:inline">{bundleExportBusy ? 'Exporting…' : 'Export'}</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => void handleExportBundleCopy()}
                                disabled={!activeWf || bundleExportBusy}
                                className="flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-mw-text-primary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50"
                                title="Copy workflow bundle JSON"
                            >
                                <Copy size={13} />
                            </button>
                            {Object.keys(outputOverrides).length > 0 && (
                                <button
                                    type="button"
                                    onClick={() => setOutputOverrides({})}
                                    className="flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-mw-text-secondary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors"
                                    title="Clear all forced outputs for this session"
                                >
                                    Clear overrides
                                </button>
                            )}
                            <button id="run-workflow-btn" onClick={handleRun} disabled={isRunning} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-mw-success hover:opacity-90 disabled:opacity-50 rounded-lg transition-colors shadow-sm">
                                {isRunning ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} {isRunning ? 'Running…' : 'Run'}
                            </button>
                            {isRunning && lastRunId ? (
                                <button
                                    type="button"
                                    onClick={() => void handleCancelRun()}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-mw-text-primary border border-mw-border bg-mw-card-alt hover:bg-mw-page rounded-lg transition-colors"
                                >
                                    <Ban size={13} /> Cancel run
                                </button>
                            ) : null}
                        </>
                    ) : (
                        <>
                            <span className="text-sm text-mw-text-secondary flex-1 min-w-0">
                                Select or create a workflow to start editing.
                            </span>
                            {onImmersiveChange && (
                                <button
                                    type="button"
                                    className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                                    aria-label={immersive ? 'Exit fullscreen' : 'Enter fullscreen'}
                                    title={immersive ? 'Exit fullscreen' : 'Enter fullscreen'}
                                    aria-pressed={immersive}
                                    onClick={() => onImmersiveChange(!immersive)}
                                >
                                    {immersive ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                                </button>
                            )}
                            {immersive && onOpenMySettings && user && (
                                <button
                                    type="button"
                                    onClick={() => onOpenMySettings()}
                                    className="shrink-0 rounded-full focus:outline-none focus:ring-2 focus:ring-mw-primary focus:ring-offset-2 focus:ring-offset-mw-card"
                                    title="My Settings"
                                    aria-label="My Settings"
                                >
                                    <UserAvatar
                                        username={user.username}
                                        avatarUrl={user.settings?.avatar_url as string | undefined}
                                        size="sm"
                                    />
                                </button>
                            )}
                        </>
                    )}
                </div>
                {saveError ? (
                    <div
                        className="shrink-0 px-4 py-2 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-b border-red-200/80 dark:border-red-800/60 flex items-center justify-between gap-2"
                        role="alert"
                    >
                        <span className="min-w-0 break-words">Save failed: {saveError}</span>
                        <button
                            type="button"
                            onClick={() => setSaveError(null)}
                            className="shrink-0 text-xs font-medium underline hover:opacity-80"
                        >
                            Dismiss
                        </button>
                    </div>
                ) : null}
                {routeLoadError ? (
                    <div
                        className="shrink-0 px-4 py-2 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-b border-red-200/80 dark:border-red-800/60 flex items-center justify-between gap-2"
                        role="alert"
                    >
                        <span className="min-w-0 break-words">{routeLoadError}</span>
                        <button
                            type="button"
                            onClick={() => setRouteLoadError(null)}
                            className="shrink-0 text-xs font-medium underline hover:opacity-80"
                        >
                            Dismiss
                        </button>
                    </div>
                ) : null}
                {workflowImportNotice ? (
                    <div
                        className="shrink-0 px-4 py-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200/80 dark:border-amber-800/60"
                        role="status"
                    >
                        {workflowImportNotice}
                    </div>
                ) : null}

                {/* Flow */}
                <div className="relative flex-1 min-h-0 min-w-0 flex flex-col">
                    {immersive && activeWf && overlayPanels && (
                        <>
                            <button
                                type="button"
                                aria-label={compactPaletteOpen ? 'Close step palette' : 'Open step palette'}
                                aria-pressed={compactPaletteOpen}
                                className="absolute left-0 top-0 bottom-0 w-4 z-10 touch-none border-0 p-0 m-0 bg-mw-border/5 hover:bg-mw-border/10 cursor-default rounded-none"
                                onPointerDown={e => onImmersiveEdgePointerDown('left', e)}
                                onPointerUp={e => onImmersiveEdgePointerUp('left', e)}
                                onPointerCancel={onImmersiveEdgePointerCancel}
                            />
                            <button
                                type="button"
                                aria-label={compactExplorerOpen ? 'Close Explorer' : 'Open Explorer'}
                                aria-pressed={compactExplorerOpen}
                                className="absolute right-0 top-0 bottom-0 w-4 z-10 touch-none border-0 p-0 m-0 bg-mw-border/5 hover:bg-mw-border/10 cursor-default rounded-none"
                                onPointerDown={e => onImmersiveEdgePointerDown('right', e)}
                                onPointerUp={e => onImmersiveEdgePointerUp('right', e)}
                                onPointerCancel={onImmersiveEdgePointerCancel}
                            />
                        </>
                    )}
                    <div
                        ref={reactFlowWrapper}
                        className="flex-1 min-h-0 overflow-hidden touch-none"
                        onDragOver={onDragOver}
                        onDrop={onDrop}
                    >
                    <WorkflowGraphUndoContext.Provider value={workflowGraphUndoContextValue}>
                    <ReactFlow
                        nodes={nodesForFlow} edges={edgesForFlow}
                        onInit={instance => {
                            reactFlowInstanceRef.current = instance;
                        }}
                        defaultEdgeOptions={{ zIndex: 1000 }}
                        connectionMode={ConnectionMode.Loose}
                        deleteKeyCode={null}
                        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                        onNodeDragStart={onNodeDragStart}
                        onNodeDragStop={onNodeDragStop}
                        onConnect={onConnect} onNodeClick={onNodeClick} onEdgeClick={onEdgeClick} onPaneClick={onPaneClick}
                        isValidConnection={isValidConnection}
                        nodeTypes={nodeTypes}
                        minZoom={WORKFLOW_CANVAS_MIN_ZOOM}
                        zoomOnScroll
                        zoomOnPinch
                        panOnScroll={false}
                        zoomOnDoubleClick={false}
                        preventScrolling
                        colorMode={typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? 'dark' : 'light'}
                        proOptions={{ hideAttribution: true }}
                        className="bg-mw-page">
                        <FitViewOnWorkflowCanvasKey fitKey={activeWf?.id ?? null} />
                        <FitViewOnWorkflowCanvasResize fitKey={activeWf?.id ?? null} containerRef={reactFlowWrapper} />
                        <Background />
                        <Controls />
                    </ReactFlow>
                    </WorkflowGraphUndoContext.Provider>
                    </div>
                    {transcribeCapture && isRunning ? (
                        <div
                            className="pointer-events-none absolute inset-x-0 bottom-4 z-30 flex justify-center px-3"
                            role="status"
                        >
                            <div className="pointer-events-auto flex max-w-md flex-col gap-2 rounded-xl border border-mw-border bg-mw-card/95 px-4 py-3 text-sm text-mw-text-primary shadow-lg backdrop-blur">
                                <div className="flex items-center gap-2">
                                    <Mic className="h-4 w-4 shrink-0 text-mw-text-secondary" aria-hidden />
                                    <span className="font-medium">Voice input</span>
                                    {transcribeUi === "recording" ? (
                                        <span className="text-xs text-rose-600 dark:text-rose-400">Recording</span>
                                    ) : null}
                                    {transcribeUi === "uploading" ? (
                                        <span className="inline-flex items-center gap-1 text-xs text-mw-text-secondary">
                                            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading
                                        </span>
                                    ) : null}
                                </div>
                                {transcribeError ? (
                                    <p className="text-xs text-rose-600 dark:text-rose-400">{transcribeError}</p>
                                ) : null}
                                <div className="flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        onClick={handleTranscribeTalk}
                                        disabled={transcribeUi === "recording" || transcribeUi === "uploading"}
                                        className="inline-flex items-center justify-center gap-1 rounded-lg bg-mw-primary px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                                    >
                                        Talk
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleTranscribeStop}
                                        disabled={transcribeUi !== "recording"}
                                        className="inline-flex items-center justify-center gap-1 rounded-lg border border-mw-border bg-mw-page px-3 py-1.5 text-xs font-medium text-mw-text-primary disabled:opacity-50"
                                    >
                                        Stop &amp; send
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) : null}
                    {audioFileInputCapture && isRunning ? (
                        <div
                            className="pointer-events-none absolute inset-x-0 bottom-4 z-30 flex justify-center px-3"
                            role="status"
                        >
                            <div className="pointer-events-auto flex max-w-md flex-col gap-2 rounded-xl border border-mw-border bg-mw-card/95 px-4 py-3 text-sm text-mw-text-primary shadow-lg backdrop-blur">
                                <div className="flex items-center gap-2">
                                    <Upload className="h-4 w-4 shrink-0 text-mw-text-secondary" aria-hidden />
                                    <span className="font-medium">Audio File Input</span>
                                    {audioFileInputUploading ? (
                                        <span className="inline-flex items-center gap-1 text-xs text-mw-text-secondary">
                                            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading
                                        </span>
                                    ) : null}
                                </div>
                                <p className="text-xs text-mw-text-secondary">
                                    Select an MP3, WAV, M4A, OGG, FLAC, or WEBM file to transcribe for this run.
                                </p>
                                {audioFileInputError ? (
                                    <p className="text-xs text-rose-600 dark:text-rose-400">{audioFileInputError}</p>
                                ) : null}
                                <input
                                    type="file"
                                    accept=".mp3,.wav,.m4a,.ogg,.flac,.webm,audio/*"
                                    disabled={audioFileInputUploading}
                                    onChange={e => {
                                        const file = e.currentTarget.files?.[0] ?? null;
                                        void handleAudioFileInputRuntimeFile(file);
                                        e.currentTarget.value = '';
                                    }}
                                    className="block w-full text-xs text-mw-text-primary file:mr-3 file:rounded-lg file:border-0 file:bg-mw-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white disabled:opacity-50"
                                />
                            </div>
                        </div>
                    ) : null}
                    {transcribeFileCapture && isRunning ? (
                        <div
                            className="pointer-events-none absolute inset-x-0 bottom-4 z-30 flex justify-center px-3"
                            role="status"
                        >
                            <div className="pointer-events-auto flex max-w-md flex-col gap-2 rounded-xl border border-mw-border bg-mw-card/95 px-4 py-3 text-sm text-mw-text-primary shadow-lg backdrop-blur">
                                <div className="flex items-center gap-2">
                                    <Upload className="h-4 w-4 shrink-0 text-mw-text-secondary" aria-hidden />
                                    <span className="font-medium">Transcribe File</span>
                                    {transcribeFileUploading ? (
                                        <span className="inline-flex items-center gap-1 text-xs text-mw-text-secondary">
                                            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading
                                        </span>
                                    ) : null}
                                </div>
                                <p className="text-xs text-mw-text-secondary">
                                    Select an MP3, WAV, M4A, OGG, FLAC, or WEBM file. The chosen provider will produce a
                                    rich transcript primitive (segments, optional words & speakers).
                                </p>
                                {transcribeFileError ? (
                                    <p className="text-xs text-rose-600 dark:text-rose-400">{transcribeFileError}</p>
                                ) : null}
                                <input
                                    type="file"
                                    accept=".mp3,.wav,.m4a,.ogg,.flac,.webm,audio/*"
                                    disabled={transcribeFileUploading}
                                    onChange={e => {
                                        const file = e.currentTarget.files?.[0] ?? null;
                                        void handleTranscribeFileRuntimeFile(file);
                                        e.currentTarget.value = '';
                                    }}
                                    className="block w-full text-xs text-mw-text-primary file:mr-3 file:rounded-lg file:border-0 file:bg-mw-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white disabled:opacity-50"
                                />
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>

            {/* ==== Right panel (inspector) ==== */}
            {inspectorOpen && (
                <div
                    className={
                        overlayPanels
                            ? `absolute right-0 top-0 bottom-0 z-50 flex min-w-0 flex-row transition-transform duration-200 ease-out ${
                                  compactExplorerOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
                              }`
                            : 'shrink-0 flex min-w-0'
                    }
                    style={overlayPanels ? { width: 'min(100vw, 24rem)' } : { width: panelWidths.right }}
                >
                    {!overlayPanels && (
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
                    {/* Tabs */}
                    <div className="flex bg-mw-page border-b border-mw-border shrink-0">
                        <button 
                            onClick={() => setInspectorTab('node')}
                            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wide transition-colors ${inspectorTab === 'node' ? 'text-mw-primary border-b-2 border-mw-primary bg-mw-card' : 'text-mw-text-secondary hover:text-mw-text-primary border-b-2 border-transparent'}`}>
                            Explorer
                        </button>
                        <button 
                            onClick={() => setInspectorTab('logs')}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold uppercase tracking-wide transition-colors ${inspectorTab === 'logs' ? 'text-mw-primary border-b-2 border-mw-primary bg-mw-card' : 'text-mw-text-secondary hover:text-mw-text-primary border-b-2 border-transparent'}`}>
                            Run Logs {runResult && <span className={`w-4 h-4 rounded-full ${runResult.status === 'ok' ? 'bg-green-500' : runResult.status === 'partial' ? 'bg-amber-500' : 'bg-red-500'}`}></span>}
                        </button>
                    </div>
                    
                    <div
                        className={`flex-1 min-h-0 flex flex-col ${explorerWorkflowOnly ? 'overflow-hidden' : 'overflow-y-auto'}`}
                    >
                        {inspectorTab === 'node' && nodeDeleteKeyboardMessage ? (
                            <div
                                role="status"
                                className="shrink-0 mx-4 mt-3 px-3 py-2 rounded-lg border border-amber-200/80 dark:border-amber-800/60 text-xs text-amber-900 dark:text-amber-100 bg-amber-50 dark:bg-amber-950/40"
                            >
                                {nodeDeleteKeyboardMessage}
                            </div>
                        ) : null}
                        {inspectorTab === 'node' ? (
                            multiCanvasSelectActive ? (
                                <div className="p-6 space-y-3 text-sm text-mw-text-secondary">
                                    <p className="text-mw-text-primary font-medium">
                                        {selectedCanvasNodes.length} items selected
                                    </p>
                                    {pendingNodeDelete ? (
                                        <div ref={nodeDeleteConfirmRef} className="space-y-3 scroll-mt-4">
                                            <p className="text-xs font-medium text-red-600 dark:text-red-400">
                                                Delete {pendingNodeDelete.ids.length} node
                                                {pendingNodeDelete.ids.length === 1 ? '' : 's'}?
                                            </p>
                                            <ul className="max-h-48 overflow-y-auto rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 divide-y divide-mw-border text-xs text-mw-text-primary font-mono">
                                                {pendingNodeDelete.ids.map(id => {
                                                    const n = nodes.find(x => x.id === id);
                                                    const label = n
                                                        ? String((n.data as { label?: string })?.label ?? '').trim() || '—'
                                                        : '—';
                                                    const ty = n?.type ?? 'node';
                                                    return (
                                                        <li key={id} className="px-3 py-2 break-all">
                                                            <span className="font-sans text-mw-text-secondary">{label}</span>
                                                            {' · '}
                                                            {ty}
                                                            {' · '}
                                                            {id}
                                                        </li>
                                                    );
                                                })}
                                            </ul>
                                            {pendingNodeDelete.skippedStart ? (
                                                <p className="text-xs text-mw-text-secondary">
                                                    The Start node cannot be removed and will remain on the canvas.
                                                </p>
                                            ) : null}
                                            <div className="flex gap-2 pt-1">
                                                <button
                                                    type="button"
                                                    onClick={handleConfirmPendingNodeDelete}
                                                    className="flex-1 py-1.5 text-xs font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                                                >
                                                    Delete
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => setPendingNodeDelete(null)}
                                                    className="flex-1 py-1.5 text-xs font-medium bg-mw-card-alt hover:opacity-90 text-mw-text-primary rounded-lg transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            <p>
                                                Select a single node or connection to edit details in this panel. On the
                                                canvas, use Cmd-click (Mac) or Ctrl-click (Windows) to add or remove nodes
                                                from the selection. Shift-drag draws a selection rectangle. Drag any
                                                selected node to move the whole group.
                                            </p>
                                            <p className="text-xs text-mw-text-secondary">
                                                Tip: press <kbd className="px-1 py-0.5 rounded border border-mw-border bg-mw-card-alt font-mono text-[10px]">Delete</kbd> or{' '}
                                                <kbd className="px-1 py-0.5 rounded border border-mw-border bg-mw-card-alt font-mono text-[10px]">Backspace</kbd> to remove the
                                                selection (confirmation required). The Start node is never removed; at
                                                least one Stop must remain.
                                            </p>
                                        </>
                                    )}
                                </div>
                            ) : selectedNode ? (
                                <div className="p-4 space-y-3 text-sm">
                                    <InspectorSection title="General">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Node</label>
                                            <div
                                                className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card-alt text-mw-text-primary rounded-lg"
                                                title={
                                                    selectedNode.type === 'workflowRef'
                                                        ? 'Referenced workflow name (same as Custom Skills list)'
                                                        : 'Step type as shown in the left palette'
                                                }
                                            >
                                                {selectedNode.type === 'workflowRef'
                                                    ? workflows.find(
                                                          w => w.id === (selectedNode.data as { workflow_id?: string }).workflow_id,
                                                      )?.name?.trim() || 'Workflow'
                                                    : paletteDisplayNameForReactFlowType(
                                                          selectedNode.type ?? 'invalidStep',
                                                      )}
                                            </div>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Node id</label>
                                            <div className="flex items-center gap-1">
                                                <div
                                                    className="flex-1 min-w-0 px-2 py-1.5 text-xs border border-mw-border bg-mw-card-alt text-mw-text-primary rounded-lg font-mono truncate"
                                                    title={selectedNode.id}
                                                >
                                                    {selectedNode.id}
                                                </div>
                                                <button
                                                    type="button"
                                                    className="shrink-0 p-1.5 rounded-lg text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card border border-mw-border"
                                                    aria-label="Copy node id to clipboard"
                                                    onClick={() => {
                                                        void copyWithFeedback(selectedNode.id);
                                                    }}
                                                >
                                                    <Copy size={14} strokeWidth={2} />
                                                </button>
                                            </div>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Label</label>
                                            <input
                                                value={(selectedNode.data as any).label ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => patchSelectedNodeData({ label: e.target.value })}
                                                className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                            />
                                        </div>
                                    </InspectorSection>

                        {selectedNode.type === 'annotationNote' && (() => {
                            const d = selectedNode.data as {
                                text?: string;
                                color?: string | null;
                                label_font_size_px?: number;
                                content_font_size_px?: number;
                                label_align?: string;
                                content_align?: string;
                            };
                            const rawLabelFs = d.label_font_size_px;
                            const labelFsDisplay =
                                typeof rawLabelFs === 'number' && Number.isFinite(rawLabelFs)
                                    ? Math.min(32, Math.max(8, Math.round(rawLabelFs)))
                                    : ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX;
                            const rawFs = d.content_font_size_px;
                            const fsDisplay =
                                typeof rawFs === 'number' && Number.isFinite(rawFs)
                                    ? Math.min(32, Math.max(8, Math.round(rawFs)))
                                    : 12;
                            const colorText = typeof d.color === 'string' ? d.color : '';
                            const normalizedHexForPicker = resolvedHexForAnnotationAccent(
                                paletteColors,
                                colorText,
                                'annotation_note',
                            );
                            return (
                                <InspectorSection title="Note appearance">
                                    <AnnotationStackOrderControls
                                        kind="note"
                                        onMoveBack={() => bumpSelectedAnnotationZIndex(-1)}
                                        onMoveForward={() => bumpSelectedAnnotationZIndex(1)}
                                    />
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Label font size (px)
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            General → Label header on the canvas.
                                        </p>
                                        <input
                                            type="number"
                                            min={8}
                                            max={32}
                                            step={1}
                                            value={labelFsDisplay}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => {
                                                const v = Number(e.target.value);
                                                if (!Number.isFinite(v)) return;
                                                patchSelectedNodeData({
                                                    label_font_size_px: Math.min(32, Math.max(8, Math.round(v))),
                                                });
                                            }}
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Content font size (px)
                                        </label>
                                        <input
                                            type="number"
                                            min={8}
                                            max={32}
                                            step={1}
                                            value={fsDisplay}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => {
                                                const v = Number(e.target.value);
                                                if (!Number.isFinite(v)) return;
                                                patchSelectedNodeData({
                                                    content_font_size_px: Math.min(32, Math.max(8, Math.round(v))),
                                                });
                                            }}
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Label alignment (canvas)
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            General → Label header on the canvas only.
                                        </p>
                                        <select
                                            value={normalizeAnnotationTextAlign(d.label_align)}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e =>
                                                patchSelectedNodeData({
                                                    label_align: normalizeAnnotationTextAlign(e.target.value),
                                                })
                                            }
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        >
                                            <option value="left">Left</option>
                                            <option value="center">Center</option>
                                            <option value="right">Right</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Content alignment (canvas)
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            Note body on the canvas; this field stays left-aligned for editing.
                                        </p>
                                        <select
                                            value={normalizeAnnotationTextAlign(d.content_align)}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e =>
                                                patchSelectedNodeData({
                                                    content_align: normalizeAnnotationTextAlign(e.target.value),
                                                })
                                            }
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        >
                                            <option value="left">Left</option>
                                            <option value="center">Center</option>
                                            <option value="right">Right</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Content
                                        </label>
                                        <textarea
                                            value={d.text ?? ''}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => patchSelectedNodeData({ text: e.target.value })}
                                            rows={4}
                                            spellCheck={false}
                                            className="w-full min-h-[5rem] px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary resize-y"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Accent color
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            Palette key or #RRGGBB; leave empty for default.
                                        </p>
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="text"
                                                value={colorText}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    if (v.trim() === '') {
                                                        patchSelectedNodeData({}, ['color']);
                                                    } else {
                                                        patchSelectedNodeData({ color: v });
                                                    }
                                                }}
                                                placeholder="annotation_note or #hex"
                                                className="min-w-0 flex-1 px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary font-mono"
                                            />
                                            <input
                                                type="color"
                                                aria-label="Pick accent color (hex)"
                                                value={normalizedHexForPicker}
                                                onChange={e => {
                                                    updateSelectedNodeData({ color: e.target.value.toLowerCase() });
                                                }}
                                                className="h-9 w-12 shrink-0 cursor-pointer rounded border border-mw-border bg-mw-card p-0.5"
                                            />
                                        </div>
                                    </div>
                                </InspectorSection>
                            );
                        })()}

                        {selectedNode.type === 'annotationRegion' && (() => {
                            const d = selectedNode.data as {
                                color?: string | null;
                                label_font_size_px?: number;
                                label_align?: string;
                            };
                            const rawFs = d.label_font_size_px;
                            const fsDisplay =
                                typeof rawFs === 'number' && Number.isFinite(rawFs)
                                    ? Math.min(32, Math.max(8, Math.round(rawFs)))
                                    : 11;
                            const colorText = typeof d.color === 'string' ? d.color : '';
                            const normalizedHexForPicker = resolvedHexForAnnotationAccent(
                                paletteColors,
                                colorText,
                                'annotation_region',
                            );
                            return (
                                <InspectorSection title="Region appearance">
                                    <AnnotationStackOrderControls
                                        kind="region"
                                        onMoveBack={() => bumpSelectedAnnotationZIndex(-1)}
                                        onMoveForward={() => bumpSelectedAnnotationZIndex(1)}
                                    />
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Label font size (px)
                                        </label>
                                        <input
                                            type="number"
                                            min={8}
                                            max={32}
                                            step={1}
                                            value={fsDisplay}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => {
                                                const v = Number(e.target.value);
                                                if (!Number.isFinite(v)) return;
                                                patchSelectedNodeData({
                                                    label_font_size_px: Math.min(32, Math.max(8, Math.round(v))),
                                                });
                                            }}
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Label alignment (canvas)
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            Floating label on the region frame.
                                        </p>
                                        <select
                                            value={normalizeAnnotationTextAlign(d.label_align)}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e =>
                                                patchSelectedNodeData({
                                                    label_align: normalizeAnnotationTextAlign(e.target.value),
                                                })
                                            }
                                            className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary"
                                        >
                                            <option value="left">Left</option>
                                            <option value="center">Center</option>
                                            <option value="right">Right</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            Accent color
                                        </label>
                                        <p className="text-[11px] text-mw-text-secondary mb-1">
                                            Palette key or #RRGGBB; leave empty for default.
                                        </p>
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="text"
                                                value={colorText}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    if (v.trim() === '') {
                                                        patchSelectedNodeData({}, ['color']);
                                                    } else {
                                                        patchSelectedNodeData({ color: v });
                                                    }
                                                }}
                                                placeholder="annotation_region or #hex"
                                                className="min-w-0 flex-1 px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary font-mono"
                                            />
                                            <input
                                                type="color"
                                                aria-label="Pick accent color (hex)"
                                                value={normalizedHexForPicker}
                                                onChange={e => {
                                                    updateSelectedNodeData({ color: e.target.value.toLowerCase() });
                                                }}
                                                className="h-9 w-12 shrink-0 cursor-pointer rounded border border-mw-border bg-mw-card p-0.5"
                                            />
                                        </div>
                                    </div>
                                </InspectorSection>
                            );
                        })()}

                        {/* Simple LLM Call nodes */}
                        {selectedNode.type === 'simpleLLMCall' && (() => {
                            const d = selectedNode.data as any;
                            const personaId = d?.persona_id ?? '';
                            const requiredInputs = d?.required_inputs ?? [{ key: 'user_prompt', type: 'string' as const, value: null }];
                            const updateInput = (idx: number, patch: Partial<RequiredInput>, withHistory = true) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                if (withHistory) updateSelectedNodeData({ required_inputs: next });
                                else patchSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <>
                                    <InspectorSection title="Model">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Persona (required)</label>
                                            <select
                                                value={personaId}
                                                onChange={e => {
                                                    const val = e.target.value || null;
                                                    updateSelectedNodeData({ persona_id: val });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">None (select before running)</option>
                                                {personas.map(p => (
                                                    <option key={p.id} value={p.id}>{p.name}</option>
                                                ))}
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">System prompt, model, and creativity come from the Persona.</p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Structure (optional)</label>
                                            <select
                                                value={d?.structure_id ?? ''}
                                                onChange={e => updateSelectedNodeData({ structure_id: e.target.value || null })}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">None (free-form text)</option>
                                                {structures.map(s => (
                                                    <option key={s.id} value={s.id}>{s.name}</option>
                                                ))}
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">Or wire from a Structure primitive for deterministic JSON output.</p>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Prompts">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Additional context (Add context handle)</label>
                                            <textarea
                                                value={(d?.additional_system_prompt_context as string) ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        additional_system_prompt_context: e.target.value || null,
                                                    })
                                                }
                                                rows={4}
                                                placeholder="Optional workflow context (wired or inline)"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Appended to the Persona’s system prompt (one blank line) when sent to the model. <span className="text-mw-text-primary">User prompt</span> is the user turn only. See <span className="text-mw-text-primary">Last Run → Inputs</span> for exact text.
                                            </p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">User Prompt (User Prompt handle)</label>
                                            <textarea
                                                value={(requiredInputs.find((i: RequiredInput) => i.key === 'user_prompt')?.value as string) ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'user_prompt');
                                                    if (idx >= 0) updateInput(idx, { value: e.target.value || null }, false);
                                                }}
                                                rows={4}
                                                placeholder="Leave empty or connect from upstream"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'multimodalLLMCall' && (() => {
                            const d = selectedNode.data as any;
                            const personaId = d?.persona_id ?? '';
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            const mmKeys = ['user_prompt', 'images', 'additional_context', 'structure'] as const;
                            for (const key of mmKeys) {
                                if (!requiredInputs.some((i: RequiredInput) => i.key === key)) {
                                    requiredInputs.push({
                                        key,
                                        type:
                                            key === 'user_prompt'
                                                ? 'string'
                                                : key === 'images'
                                                  ? 'list'
                                                  : key === 'structure'
                                                    ? 'structure'
                                                    : 'string',
                                        value: null,
                                    });
                                }
                            }
                            requiredInputs = requiredInputs.filter((i: RequiredInput) => mmKeys.includes(i.key as (typeof mmKeys)[number]));
                            const updateInput = (idx: number, patch: Partial<RequiredInput>, withHistory = true) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                if (withHistory) updateSelectedNodeData({ required_inputs: next });
                                else patchSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Vision-capable LLM step: wire a list of image artifact refs (e.g. from URL snapshot) plus a user prompt. Uses the same LM Studio path as Simple LLM Call; non-vision models fail with a structured error."
                                    />
                                    <InspectorSection title="Model">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Persona (required)</label>
                                            <select
                                                value={personaId}
                                                onChange={e => {
                                                    const val = e.target.value || null;
                                                    updateSelectedNodeData({ persona_id: val });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">None (select before running)</option>
                                                {personas.map(p => (
                                                    <option key={p.id} value={p.id}>{p.name}</option>
                                                ))}
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">System prompt, default model, and creativity come from the Persona.</p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Model override (optional)</label>
                                            <input
                                                type="text"
                                                value={(d?.model as string) ?? ''}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        model: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="Leave empty to use Persona default_model"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Structure (optional)</label>
                                            <select
                                                value={d?.structure_id ?? ''}
                                                onChange={e => updateSelectedNodeData({ structure_id: e.target.value || null })}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">None (free-form text)</option>
                                                {structures.map(s => (
                                                    <option key={s.id} value={s.id}>{s.name}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Prompts & images">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Additional context (Add context handle)</label>
                                            <textarea
                                                value={(d?.additional_system_prompt_context as string) ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        additional_system_prompt_context: e.target.value || null,
                                                    })
                                                }
                                                rows={3}
                                                placeholder="Optional; appended to system prompt"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">User prompt (User Prompt handle)</label>
                                            <textarea
                                                value={(requiredInputs.find((i: RequiredInput) => i.key === 'user_prompt')?.value as string) ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'user_prompt');
                                                    if (idx >= 0) updateInput(idx, { value: e.target.value || null }, false);
                                                }}
                                                rows={3}
                                                placeholder="Wire or type the user turn"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Images (Images handle)</label>
                                            <p className="text-[10px] text-mw-text-secondary mb-1">
                                                Wire a list of objects with <code className="text-[10px]">artifact_id</code> (e.g. List from Dictionary value on snapshot <code className="text-[10px]">image</code>), or a snapshot output object; see docs.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'textToSpeech' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            requiredInputs = requiredInputs.filter((i: RequiredInput) => i.key === 'text');
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'text')) {
                                requiredInputs.push({ key: 'text', type: 'string', value: null });
                            }
                            const textIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'text');
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Synthesizes speech via the local TTS bridge. Pick a ready model (admins register models under My Settings → TTS models). Wire text or type inline."
                                    />
                                    <InspectorSection title="Model">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                TTS model (required)
                                            </label>
                                            <select
                                                value={d?.tts_model_id ?? ''}
                                                onChange={e =>
                                                    updateSelectedNodeData({ tts_model_id: e.target.value || null })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">Select a model</option>
                                                {ttsModelsReady.map(m => (
                                                    <option key={m.id} value={m.id}>
                                                        {m.display_name} ({m.engine})
                                                    </option>
                                                ))}
                                            </select>
                                            <p className="mt-1 text-[10px] text-mw-text-secondary leading-snug">
                                                With a voice sample below, use a <strong className="text-mw-text-primary">Base</strong> (clone-capable) checkpoint; Voice Design weights are for preview only in Voice Sample Manager.
                                            </p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Voice sample (optional)
                                            </label>
                                            <select
                                                value={d?.voice_sample_id ?? ''}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        voice_sample_id: e.target.value.trim() === '' ? null : e.target.value,
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">None (design / preset path)</option>
                                                {voiceSamplesList.map(s => (
                                                    <option key={s.id} value={s.id}>
                                                        {s.name} ({s.language})
                                                    </option>
                                                ))}
                                            </select>
                                            <p className="mt-1 text-[10px] text-mw-text-secondary leading-snug">
                                                Uses saved reference audio + transcript for voice clone. <code className="text-[10px]">speaker</code> / preset fields in bridge JSON are ignored in clone mode.
                                            </p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Engine override (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.engine ?? ''}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        engine: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="Leave empty to use registry engine"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Text">
                                        <textarea
                                            value={(requiredInputs[textIdx]?.value as string) ?? ''}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => {
                                                const next = [...requiredInputs];
                                                if (textIdx >= 0) next[textIdx] = { ...next[textIdx], value: e.target.value || null };
                                                patchSelectedNodeData({ required_inputs: next });
                                            }}
                                            rows={4}
                                            placeholder="Wire the Text handle or type here"
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
                                        />
                                    </InspectorSection>
                                    <InspectorSection
                                        title="Playback"
                                        description="During Run (stream). Overrides My Settings → Text-to-Speech playback. Run log play/download is always available."
                                    >
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                When to play synthesized audio
                                            </label>
                                            <select
                                                value={(() => {
                                                    const tw = d?.tts_playback_when;
                                                    if (tw === 'inline' || tw === 'manual' || tw === 'after_workflow') {
                                                        return tw;
                                                    }
                                                    if (d?.auto_play_tts_on_node_end === true) return 'inline';
                                                    if (d?.auto_play_tts_on_node_end === false) return 'manual';
                                                    return 'default';
                                                })()}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    if (v === 'default') {
                                                        updateSelectedNodeData({
                                                            tts_playback_when: null,
                                                            auto_play_tts_on_node_end: null,
                                                        });
                                                    } else {
                                                        updateSelectedNodeData({
                                                            tts_playback_when: v as 'inline' | 'manual' | 'after_workflow',
                                                            auto_play_tts_on_node_end: null,
                                                        });
                                                    }
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="default">Use My Settings (default)</option>
                                                <option value="inline">When each node finishes (inline)</option>
                                                <option value="manual">Manual only (run log player)</option>
                                                <option value="after_workflow">After workflow completes (queue, then play in order)</option>
                                            </select>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Bridge options (JSON)">
                                        <TtsBridgeOptionsTextarea
                                            key={selectedNode.id}
                                            ttsOptions={d?.tts_options}
                                            onFocus={recordGraphBeforeMutation}
                                            onCommit={opts => patchSelectedNodeData({ tts_options: opts })}
                                        />
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'transcribeAudio' && (() => {
                            const d = selectedNode.data as {
                                label?: string;
                                language?: string | null;
                                task?: string | null;
                                model?: string | null;
                            };
                            const taskVal = d?.task === 'translate' ? 'translate' : 'transcribe';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Records in the browser during Run (stream). Use Talk, then Stop, to upload audio. Requires the STT bridge; see docs. Output is plain text for downstream steps."
                                    />
                                    <InspectorSection title="Transcription">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Language (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.language ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        language: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="e.g. en — leave empty to auto-detect"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Task</label>
                                            <select
                                                value={taskVal}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        task: e.target.value === 'translate' ? 'translate' : 'transcribe',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            >
                                                <option value="transcribe">Transcribe (same language)</option>
                                                <option value="translate">Translate to English</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Model id (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.model ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        model: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="Bridge default if empty"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'audioFileInput' && (() => {
                            const d = selectedNode.data as {
                                label?: string;
                                audio_artifact_id?: string | null;
                                language?: string | null;
                                task?: string | null;
                                model?: string | null;
                            };
                            const taskVal = d?.task === 'translate' ? 'translate' : 'transcribe';
                            const selectedArtifact = audioFileArtifacts.find(a => a.id === d?.audio_artifact_id) ?? null;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Transcribes a selected audio file through the same STT bridge as Voice input. Output is plain text for downstream steps."
                                    />
                                    <InspectorSection title="Audio file">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Saved file (optional)
                                            </label>
                                            <select
                                                value={d?.audio_artifact_id ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        audio_artifact_id: e.target.value.trim() === '' ? null : e.target.value,
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">Prompt for a file at run time</option>
                                                {audioFileArtifacts.map(a => (
                                                    <option key={a.id} value={a.id}>
                                                        {a.filename} ({Math.ceil(a.size_bytes / 1024)} KB)
                                                    </option>
                                                ))}
                                            </select>
                                            {selectedArtifact ? (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                    Selected: {selectedArtifact.filename} · {selectedArtifact.mime_type}
                                                </p>
                                            ) : (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                    Without a saved file, Run (stream) asks for an upload each time.
                                                </p>
                                            )}
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Upload and use a new file
                                            </label>
                                            <input
                                                type="file"
                                                accept=".mp3,.wav,.m4a,.ogg,.flac,.webm,audio/*"
                                                onChange={e => {
                                                    const file = e.currentTarget.files?.[0] ?? null;
                                                    e.currentTarget.value = '';
                                                    if (!file) return;
                                                    recordGraphBeforeMutation();
                                                    void (async () => {
                                                        try {
                                                            const artifact = await ApiClient.createAudioFileArtifact(file);
                                                            setAudioFileArtifacts(prev => [artifact, ...prev.filter(a => a.id !== artifact.id)]);
                                                            patchSelectedNodeData({ audio_artifact_id: artifact.id });
                                                            showStatusToast('Audio file uploaded');
                                                        } catch (err) {
                                                            const msg = err instanceof Error ? err.message : String(err);
                                                            showStatusToast(msg, true);
                                                        }
                                                    })();
                                                }}
                                                className="block w-full text-xs text-mw-text-primary file:mr-3 file:rounded-lg file:border-0 file:bg-mw-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
                                            />
                                        </div>
                                        {d?.audio_artifact_id ? (
                                            <button
                                                type="button"
                                                onClick={() => patchSelectedNodeData({ audio_artifact_id: null })}
                                                className="inline-flex items-center justify-center rounded-lg border border-mw-border bg-mw-card-alt px-3 py-1.5 text-xs font-medium text-mw-text-primary hover:bg-mw-border/40"
                                            >
                                                Clear saved file
                                            </button>
                                        ) : null}
                                    </InspectorSection>
                                    <InspectorSection title="Transcription">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Language (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.language ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        language: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="e.g. en — leave empty to auto-detect"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Task</label>
                                            <select
                                                value={taskVal}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        task: e.target.value === 'translate' ? 'translate' : 'transcribe',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            >
                                                <option value="transcribe">Transcribe (same language)</option>
                                                <option value="translate">Translate to English</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Model id (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.model ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        model: e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="Bridge default if empty"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'transcribeFile' && (() => {
                            const d = selectedNode.data as {
                                label?: string;
                                provider?: string | null;
                                audio_artifact_id?: string | null;
                                language?: string | null;
                                task?: string | null;
                                prompt?: string | null;
                                diarization_enabled?: boolean | null;
                                include_word_timestamps?: boolean | null;
                                provider_model_id?: string | null;
                            };
                            const taskVal = d?.task === 'translate' ? 'translate' : 'transcribe';
                            const providerVal = (d?.provider ?? 'local_whisper').toString();
                            const selectedProvider = transcriptionProviders.find(p => p.id === providerVal) ?? null;
                            const selectedArtifact = audioFileArtifacts.find(a => a.id === d?.audio_artifact_id) ?? null;
                            const modelOptions = selectedProvider?.models ?? [];
                            const providerOptions =
                                transcriptionProviders.length > 0
                                    ? transcriptionProviders
                                    : [
                                          {
                                              id: 'local_whisper',
                                              label: 'Local Whisper (stt-bridge)',
                                              capabilities: [],
                                              is_synchronous: true,
                                              requires_api_key: false,
                                              api_key_field: null,
                                              notes: null,
                                              models: [],
                                          } satisfies TranscriptionProviderItem,
                                      ];
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Transcribes an audio file through the selected provider and emits a Transcript primitive (segments, optional words & speakers). Long-running cloud jobs survive client disconnects via the persisted transcription poller."
                                    />
                                    <InspectorSection title="Provider">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Speech-to-text provider
                                            </label>
                                            <select
                                                value={providerVal}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const newPid = e.target.value;
                                                    const p = providerOptions.find(x => x.id === newPid) ?? null;
                                                    const models = p?.models ?? [];
                                                    let nextModel: string | null = null;
                                                    if (models.length > 0) {
                                                        const def = models.find(m => m.is_default);
                                                        nextModel = (def ?? models[0]).id;
                                                    }
                                                    patchSelectedNodeData({
                                                        provider: newPid,
                                                        provider_model_id: nextModel,
                                                    });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            >
                                                {providerOptions.map(p => (
                                                    <option key={p.id} value={p.id}>
                                                        {p.label}
                                                    </option>
                                                ))}
                                            </select>
                                            {selectedProvider?.notes ? (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">{selectedProvider.notes}</p>
                                            ) : null}
                                            {selectedProvider?.requires_api_key ? (
                                                <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-400">
                                                    This provider requires an API key. Add one under{' '}
                                                    <strong className="font-medium">My Settings → API Settings</strong>{' '}
                                                    (
                                                    <code className="text-[10px]">{selectedProvider.api_key_field ?? selectedProvider.id}</code>
                                                    ). Audio is uploaded over HTTPS to the provider for processing.
                                                </p>
                                            ) : (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                    Audio stays on this server and is processed by the local stt-bridge.
                                                </p>
                                            )}
                                            {modelOptions.length > 0 ? (
                                                <div className="mt-3">
                                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                        Speech model
                                                    </label>
                                                    <select
                                                        value={d?.provider_model_id ?? ''}
                                                        onFocus={recordGraphBeforeMutation}
                                                        onChange={e =>
                                                            patchSelectedNodeData({
                                                                provider_model_id:
                                                                    e.target.value.trim() === ''
                                                                        ? null
                                                                        : e.target.value.trim(),
                                                            })
                                                        }
                                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                                    >
                                                        <option value="">Server default</option>
                                                        {modelOptions.map(m => (
                                                            <option key={m.id} value={m.id}>
                                                                {m.label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    {(() => {
                                                        const mid = d?.provider_model_id;
                                                        const sel = mid
                                                            ? modelOptions.find(m => m.id === mid)
                                                            : null;
                                                        const desc = sel?.description;
                                                        return desc ? (
                                                            <p className="mt-1 text-[10px] text-mw-text-secondary">{desc}</p>
                                                        ) : null;
                                                    })()}
                                                    <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                        Server default follows{' '}
                                                        <code className="text-[10px]">ASSEMBLYAI_SPEECH_MODELS</code> on
                                                        the API host.
                                                    </p>
                                                </div>
                                            ) : (
                                                <p className="mt-3 text-[10px] text-mw-text-secondary">
                                                    This provider does not expose separate speech models here; local
                                                    STT uses the bridge&apos;s configured weights.
                                                </p>
                                            )}
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Audio file">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Saved file (optional)
                                            </label>
                                            <select
                                                value={d?.audio_artifact_id ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        audio_artifact_id:
                                                            e.target.value.trim() === '' ? null : e.target.value,
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="">Prompt for a file at run time</option>
                                                {audioFileArtifacts.map(a => (
                                                    <option key={a.id} value={a.id}>
                                                        {a.filename} ({Math.ceil(a.size_bytes / 1024)} KB)
                                                    </option>
                                                ))}
                                            </select>
                                            {selectedArtifact ? (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                    Selected: {selectedArtifact.filename} · {selectedArtifact.mime_type}
                                                </p>
                                            ) : (
                                                <p className="mt-1 text-[10px] text-mw-text-secondary">
                                                    Without a saved file, Run (stream) asks for an upload each time.
                                                </p>
                                            )}
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Upload and use a new file
                                            </label>
                                            <input
                                                type="file"
                                                accept=".mp3,.wav,.m4a,.ogg,.flac,.webm,audio/*"
                                                onChange={e => {
                                                    const file = e.currentTarget.files?.[0] ?? null;
                                                    e.currentTarget.value = '';
                                                    if (!file) return;
                                                    recordGraphBeforeMutation();
                                                    void (async () => {
                                                        try {
                                                            const artifact = await ApiClient.createAudioFileArtifact(file);
                                                            setAudioFileArtifacts(prev => [
                                                                artifact,
                                                                ...prev.filter(a => a.id !== artifact.id),
                                                            ]);
                                                            patchSelectedNodeData({ audio_artifact_id: artifact.id });
                                                            showStatusToast('Audio file uploaded');
                                                        } catch (err) {
                                                            const msg = err instanceof Error ? err.message : String(err);
                                                            showStatusToast(msg, true);
                                                        }
                                                    })();
                                                }}
                                                className="block w-full text-xs text-mw-text-primary file:mr-3 file:rounded-lg file:border-0 file:bg-mw-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
                                            />
                                        </div>
                                        {d?.audio_artifact_id ? (
                                            <button
                                                type="button"
                                                onClick={() => patchSelectedNodeData({ audio_artifact_id: null })}
                                                className="inline-flex items-center justify-center rounded-lg border border-mw-border bg-mw-card-alt px-3 py-1.5 text-xs font-medium text-mw-text-primary hover:bg-mw-border/40"
                                            >
                                                Clear saved file
                                            </button>
                                        ) : null}
                                    </InspectorSection>
                                    <InspectorSection title="Transcription">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Language (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={d?.language ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        language:
                                                            e.target.value.trim() === '' ? null : e.target.value.trim(),
                                                    })
                                                }
                                                placeholder="e.g. en — leave empty to auto-detect"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Task</label>
                                            <select
                                                value={taskVal}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        task:
                                                            e.target.value === 'translate' ? 'translate' : 'transcribe',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            >
                                                <option value="transcribe">Transcribe (same language)</option>
                                                <option value="translate">Translate to English</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Bias prompt / vocab hint (optional)
                                            </label>
                                            <textarea
                                                rows={2}
                                                value={d?.prompt ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        prompt:
                                                            e.target.value.trim() === '' ? null : e.target.value,
                                                    })
                                                }
                                                placeholder="Names, jargon, or context to bias the recognizer"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                        </div>
                                        <label className="flex items-center gap-2 text-xs text-mw-text-primary">
                                            <input
                                                type="checkbox"
                                                checked={Boolean(d?.diarization_enabled)}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        diarization_enabled: e.currentTarget.checked,
                                                    })
                                                }
                                            />
                                            Enable speaker diarization
                                        </label>
                                        <label className="flex items-center gap-2 text-xs text-mw-text-primary">
                                            <input
                                                type="checkbox"
                                                checked={Boolean(d?.include_word_timestamps)}
                                                onChange={e =>
                                                    patchSelectedNodeData({
                                                        include_word_timestamps: e.currentTarget.checked,
                                                    })
                                                }
                                            />
                                            Include word-level timestamps
                                        </label>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'gmailListMessages' && (() => {
                            const d = selectedNode.data as any;
                            const gmailKeys = ['after', 'before', 'unread_only', 'query', 'max_results'] as const;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            requiredInputs = requiredInputs.filter((i: RequiredInput) =>
                                gmailKeys.includes(i.key as (typeof gmailKeys)[number]),
                            );
                            for (const key of gmailKeys) {
                                if (!requiredInputs.some((i: RequiredInput) => i.key === key)) {
                                    if (key === 'max_results') {
                                        requiredInputs.push({ key: 'max_results', type: 'int', value: d?.max_results ?? 10 });
                                    } else if (key === 'unread_only') {
                                        requiredInputs.push({
                                            key: 'unread_only',
                                            type: 'boolean',
                                            value: d?.unread_only ?? false,
                                        });
                                    } else if (key === 'after') {
                                        requiredInputs.push({ key: 'after', type: 'datetime', value: d?.after ?? null });
                                    } else if (key === 'before') {
                                        requiredInputs.push({ key: 'before', type: 'datetime', value: d?.before ?? null });
                                    } else {
                                        requiredInputs.push({ key: 'query', type: 'string', value: null });
                                    }
                                }
                            }
                            const maxInline = requiredInputs.find((i: RequiredInput) => i.key === 'max_results')?.value;
                            const afterVal = requiredInputs.find((i: RequiredInput) => i.key === 'after')?.value;
                            const beforeVal = requiredInputs.find((i: RequiredInput) => i.key === 'before')?.value;
                            const unreadIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'unread_only');
                            const unreadVal = unreadIdx >= 0 ? requiredInputs[unreadIdx]?.value : false;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description={
                                            <>
                                                Lists Gmail messages (read-only). <strong className="text-mw-text-primary">Time &
                                                limits</strong> uses native date and time plus optional raw RFC3339; wall-clock interpretation
                                                follows <strong className="text-mw-text-primary">My Profile → Workflow time zone</strong>.
                                                See the help (i) for how <code className="text-[10px]">after:</code> /{' '}
                                                <code className="text-[10px]">before:</code> are derived. Connect Google under My Settings →
                                                Google for workflows.
                                            </>
                                        }
                                    />
                                    <InspectorSection title="Time & limits">
                                        <GmailBoundaryDateFields
                                            afterValue={afterVal as string | null | undefined}
                                            beforeValue={beforeVal as string | null | undefined}
                                            timeZone={resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined)}
                                            onAfterChange={v => {
                                                const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'after');
                                                if (idx >= 0) {
                                                    const next = [...requiredInputs];
                                                    next[idx] = { ...next[idx], value: v };
                                                    updateSelectedNodeData({ required_inputs: next, after: v });
                                                }
                                            }}
                                            onBeforeChange={v => {
                                                const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'before');
                                                if (idx >= 0) {
                                                    const next = [...requiredInputs];
                                                    next[idx] = { ...next[idx], value: v };
                                                    updateSelectedNodeData({ required_inputs: next, before: v });
                                                }
                                            }}
                                        />
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={unreadVal === true}
                                                onChange={e => {
                                                    const v = e.target.checked;
                                                    const next = [...requiredInputs];
                                                    if (unreadIdx >= 0) next[unreadIdx] = { ...next[unreadIdx], value: v };
                                                    updateSelectedNodeData({ required_inputs: next, unread_only: v });
                                                }}
                                                className="rounded border-mw-border"
                                            />
                                            <span className="text-xs text-mw-text-primary">Unread only (<code className="text-[10px]">is:unread</code>)</span>
                                        </label>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Max results (1–100)</label>
                                            <input
                                                type="number"
                                                min={1}
                                                max={100}
                                                value={typeof maxInline === 'number' ? maxInline : Number(maxInline) || 10}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = Math.max(1, Math.min(100, parseInt(e.target.value, 10) || 10));
                                                    const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'max_results');
                                                    const next = [...requiredInputs];
                                                    if (idx >= 0) next[idx] = { ...next[idx], value: v };
                                                    patchSelectedNodeData({ required_inputs: next, max_results: v });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection
                                        title="Inbox categories"
                                        titleAside={
                                            <ContextHelpModal
                                                title="Inbox category filters"
                                                triggerLabel="Inbox category filters help"
                                            >
                                                <GmailInboxCategoriesHelpContent />
                                            </ContextHelpModal>
                                        }
                                    >
                                        <GmailListCategoryFields
                                            nodeData={d as Record<string, unknown>}
                                            accountInboxFocus={normalizeGmailInboxFocus(user?.settings?.gmail_workflow_inbox_focus)}
                                            onPatch={(patch, remove) => updateSelectedNodeData(patch, remove)}
                                        />
                                    </InspectorSection>
                                    <InspectorSection title="Search">
                                        <div>
                                            <div className="flex items-center gap-1 mb-1">
                                                <label className="text-xs font-medium text-mw-text-secondary">Query (optional)</label>
                                                <ContextHelpModal
                                                    title="Gmail search query"
                                                    triggerLabel="Gmail search syntax help"
                                                >
                                                    <GmailQueryHelpContent />
                                                </ContextHelpModal>
                                            </div>
                                            <input
                                                value={
                                                    String(
                                                        requiredInputs.find((i: RequiredInput) => i.key === 'query')?.value ??
                                                            '',
                                                    )
                                                }
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value || null;
                                                    const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'query');
                                                    const next = [...requiredInputs];
                                                    if (idx >= 0) next[idx] = { ...next[idx], value: v };
                                                    patchSelectedNodeData({ required_inputs: next, query: v });
                                                }}
                                                placeholder="Gmail search operators; combined with filters above"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'googleDocsGetDocument' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs)
                                ? [...d.required_inputs]
                                : [];
                            requiredInputs = requiredInputs.filter(
                                (i: RequiredInput) => i.key === 'document_url_or_id',
                            );
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'document_url_or_id')) {
                                requiredInputs.push({ key: 'document_url_or_id', type: 'string', value: null });
                            }
                            const urlVal =
                                requiredInputs.find((i: RequiredInput) => i.key === 'document_url_or_id')?.value ??
                                d?.document_url_or_id ??
                                '';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Fetches a Google Doc (read-only) using your workflow Google connection. Output includes a curated document_payload for the Parse utility. Connect Google under My Settings → Google for workflows."
                                    />
                                    <InspectorSection title="Document">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Document URL or ID
                                            </label>
                                            <input
                                                value={String(urlVal ?? '')}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value || null;
                                                    const idx = requiredInputs.findIndex(
                                                        (i: RequiredInput) => i.key === 'document_url_or_id',
                                                    );
                                                    const next = [...requiredInputs];
                                                    if (idx >= 0) next[idx] = { ...next[idx], value: v };
                                                    patchSelectedNodeData({
                                                        required_inputs: next,
                                                        document_url_or_id: v,
                                                    });
                                                }}
                                                placeholder="https://docs.google.com/document/d/… or document id"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                        <label className="flex items-center gap-2 cursor-pointer mt-2">
                                            <input
                                                type="checkbox"
                                                checked={d?.include_tabs_content !== false}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        include_tabs_content: e.target.checked,
                                                    })
                                                }
                                                className="rounded border-mw-border"
                                            />
                                            <span className="text-xs text-mw-text-primary">Include document tabs content</span>
                                        </label>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'googleDocsParseDocument' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs)
                                ? [...d.required_inputs]
                                : [];
                            requiredInputs = requiredInputs.filter((i: RequiredInput) => i.key === 'document');
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'document')) {
                                requiredInputs.push({ key: 'document', type: 'dictionary', value: null });
                            }
                            const strategy = d?.chunk_strategy ?? 'structure';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Splits a Google Docs Get Document output into generic chunks (text, tables, images). Wire the Get Document dictionary output to the document input."
                                    />
                                    <InspectorSection title="Chunking">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Chunk strategy
                                            </label>
                                            <select
                                                value={strategy}
                                                onChange={e =>
                                                    updateSelectedNodeData({ chunk_strategy: e.target.value })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            >
                                                <option value="structure">Structure (default)</option>
                                                <option value="tab">One chunk per tab</option>
                                                <option value="flat">Single flat text chunk</option>
                                            </select>
                                        </div>
                                        <div className="mt-2">
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                Max text chars per chunk (optional)
                                            </label>
                                            <input
                                                type="number"
                                                min={0}
                                                value={d?.max_chunk_text_chars ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const raw = e.target.value;
                                                    const v = raw === '' ? null : Math.max(0, parseInt(raw, 10) || 0);
                                                    patchSelectedNodeData({ max_chunk_text_chars: v });
                                                }}
                                                placeholder="Default from server"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'calendarListEvents' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            requiredInputs = requiredInputs.filter(
                                (i: RequiredInput) => i.key === 'time_min' || i.key === 'time_max',
                            );
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'time_min')) {
                                requiredInputs.push({ key: 'time_min', type: 'datetime', value: null });
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'time_max')) {
                                requiredInputs.push({ key: 'time_max', type: 'datetime', value: null });
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const tminIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'time_min');
                            const tmaxIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'time_max');
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Lists calendar events in a time window (read-only). Use date and time below—stored as RFC3339 for the Calendar API—using your My Profile workflow time zone, or wire time_min / time_max from upstream."
                                    />
                                    <InspectorSection title="Calendar">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Calendar ID</label>
                                            <input
                                                value={d?.calendar_id ?? 'primary'}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        calendar_id: e.target.value.trim() || 'primary',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">Use primary or a calendar email address.</p>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Time & limits">
                                        <CalendarWindowDateTimeFields
                                            timeMinValue={requiredInputs[tminIdx]?.value as string | null | undefined}
                                            timeMaxValue={requiredInputs[tmaxIdx]?.value as string | null | undefined}
                                            timeZone={resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined)}
                                            onTimeMinChange={v => {
                                                if (tminIdx >= 0) {
                                                    updateInput(tminIdx, { value: v });
                                                }
                                            }}
                                            onTimeMaxChange={v => {
                                                if (tmaxIdx >= 0) {
                                                    updateInput(tmaxIdx, { value: v });
                                                }
                                            }}
                                        />
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'fetchUrl' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            requiredInputs = requiredInputs.filter((i: RequiredInput) => i.key === 'url');
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'url')) {
                                requiredInputs.push({ key: 'url', type: 'string', value: null });
                            }
                            const urlIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'url');
                            const urlFromInput = requiredInputs[urlIdx]?.value;
                            const displayUrl =
                                (typeof urlFromInput === 'string' && urlFromInput.trim() !== '' ? urlFromInput : null) ??
                                (typeof d?.url === 'string' ? d.url : '') ??
                                '';
                            const pol = d?.cache_policy;
                            const cachePolicy: 'default' | 'refresh' | 'bypass' =
                                pol === 'refresh' || pol === 'bypass' ? pol : 'default';
                            const hdrs =
                                d?.headers && typeof d.headers === 'object' && !Array.isArray(d.headers)
                                    ? (d.headers as Record<string, string>)
                                    : undefined;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Fetches a URL on the API server and returns status, final URL, headers, and text body. Non-2xx responses still succeed the step (see status_code). Use cache policy to reuse prior successful responses. Requests run in the API process—do not use for untrusted targets without understanding operator risk."
                                    />
                                    <InspectorSection title="Request">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">URL</label>
                                            <input
                                                value={displayUrl}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    const next = [...requiredInputs];
                                                    if (urlIdx >= 0) next[urlIdx] = { ...next[urlIdx], value: v || null };
                                                    patchSelectedNodeData({ required_inputs: next, url: v });
                                                }}
                                                placeholder="https://…"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Method</label>
                                            <select
                                                value={String(d?.method ?? 'GET').toUpperCase()}
                                                onChange={e => updateSelectedNodeData({ method: e.target.value })}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            >
                                                {['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'].map(m => (
                                                    <option key={m} value={m}>
                                                        {m}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Headers (JSON object)</label>
                                            <FetchUrlHeadersTextarea
                                                key={selectedNode.id}
                                                headers={hdrs}
                                                onFocusBeforeEdit={recordGraphBeforeMutation}
                                                onCommit={flat => updateSelectedNodeData({ headers: flat })}
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Timeout (ms, optional)</label>
                                            <input
                                                type="number"
                                                min={1}
                                                value={d?.timeout_ms != null && d.timeout_ms !== '' ? String(d.timeout_ms) : ''}
                                                onChange={e => {
                                                    const t = e.target.value.trim();
                                                    if (t === '') {
                                                        updateSelectedNodeData({ timeout_ms: null });
                                                        return;
                                                    }
                                                    const n = parseInt(t, 10);
                                                    updateSelectedNodeData({ timeout_ms: Number.isFinite(n) && n > 0 ? n : null });
                                                }}
                                                placeholder="(server default)"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Cache">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Policy</label>
                                            <select
                                                value={cachePolicy}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        cache_policy: e.target.value as 'default' | 'refresh' | 'bypass',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            >
                                                <option value="default">default (use cache if present)</option>
                                                <option value="refresh">refresh (fetch and update cache)</option>
                                                <option value="bypass">bypass (always fetch, do not store)</option>
                                            </select>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'captureUrlSnapshot' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            requiredInputs = requiredInputs.filter((i: RequiredInput) => i.key === 'url');
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'url')) {
                                requiredInputs.push({ key: 'url', type: 'string', value: null });
                            }
                            const urlIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'url');
                            const urlFromInput = requiredInputs[urlIdx]?.value;
                            const displayUrl =
                                (typeof urlFromInput === 'string' && urlFromInput.trim() !== '' ? urlFromInput : null) ??
                                (typeof d?.url === 'string' ? d.url : '') ??
                                '';
                            const pol = d?.cache_policy;
                            const cachePolicy: 'default' | 'refresh' | 'bypass' =
                                pol === 'refresh' || pol === 'bypass' ? pol : 'default';
                            const wu = d?.wait_until;
                            const waitUntil: 'load' | 'domcontentloaded' | 'networkidle' =
                                wu === 'domcontentloaded' || wu === 'networkidle' ? wu : 'load';
                            const fullPage = d?.full_page === undefined || d?.full_page === null ? true : Boolean(d.full_page);
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Renders the URL in headless Chromium and stores a PNG artifact (image reference + metadata). Does not interpret page content. Security: same trust model as Fetch URL (API can reach internal URLs)."
                                    />
                                    <InspectorSection title="Page">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">URL</label>
                                            <input
                                                value={displayUrl}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    const next = [...requiredInputs];
                                                    if (urlIdx >= 0) next[urlIdx] = { ...next[urlIdx], value: v || null };
                                                    patchSelectedNodeData({ required_inputs: next, url: v });
                                                }}
                                                placeholder="https://…"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                        <div className="flex items-center gap-2 mt-2">
                                            <input
                                                id="cap-fullpage"
                                                type="checkbox"
                                                checked={fullPage}
                                                onChange={e => updateSelectedNodeData({ full_page: e.target.checked })}
                                            />
                                            <label htmlFor="cap-fullpage" className="text-xs text-mw-text-secondary">
                                                Full page screenshot
                                            </label>
                                        </div>
                                        <div className="grid grid-cols-2 gap-2 mt-2">
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">Viewport W</label>
                                                <input
                                                    type="number"
                                                    min={1}
                                                    value={d?.viewport_width != null && d.viewport_width !== '' ? String(d.viewport_width) : ''}
                                                    onChange={e => {
                                                        const t = e.target.value.trim();
                                                        if (t === '') {
                                                            updateSelectedNodeData({ viewport_width: null });
                                                            return;
                                                        }
                                                        const n = parseInt(t, 10);
                                                        updateSelectedNodeData({ viewport_width: Number.isFinite(n) && n > 0 ? n : null });
                                                    }}
                                                    placeholder="default"
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">Viewport H</label>
                                                <input
                                                    type="number"
                                                    min={1}
                                                    value={d?.viewport_height != null && d.viewport_height !== '' ? String(d.viewport_height) : ''}
                                                    onChange={e => {
                                                        const t = e.target.value.trim();
                                                        if (t === '') {
                                                            updateSelectedNodeData({ viewport_height: null });
                                                            return;
                                                        }
                                                        const n = parseInt(t, 10);
                                                        updateSelectedNodeData({ viewport_height: Number.isFinite(n) && n > 0 ? n : null });
                                                    }}
                                                    placeholder="default"
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                                />
                                            </div>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Wait until</label>
                                            <select
                                                value={waitUntil}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        wait_until: e.target.value as 'load' | 'domcontentloaded' | 'networkidle',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            >
                                                <option value="load">load</option>
                                                <option value="domcontentloaded">domcontentloaded</option>
                                                <option value="networkidle">networkidle</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Timeout (ms, optional)</label>
                                            <input
                                                type="number"
                                                min={1}
                                                value={d?.timeout_ms != null && d.timeout_ms !== '' ? String(d.timeout_ms) : ''}
                                                onChange={e => {
                                                    const t = e.target.value.trim();
                                                    if (t === '') {
                                                        updateSelectedNodeData({ timeout_ms: null });
                                                        return;
                                                    }
                                                    const n = parseInt(t, 10);
                                                    updateSelectedNodeData({ timeout_ms: Number.isFinite(n) && n > 0 ? n : null });
                                                }}
                                                placeholder="(server default)"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Cache">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Policy</label>
                                            <select
                                                value={cachePolicy}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        cache_policy: e.target.value as 'default' | 'refresh' | 'bypass',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg"
                                            >
                                                <option value="default">default (use cache if present)</option>
                                                <option value="refresh">refresh (capture and update cache)</option>
                                                <option value="bypass">bypass (capture, do not store cache)</option>
                                            </select>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {/* List to String utility nodes */}
                        {selectedNode.type === 'listToString' && (() => {
                            const d = selectedNode.data as {
                                use_text_join?: boolean;
                                add_line_breaks_between_items?: boolean;
                            };
                            const useJson = d?.use_text_join !== true;
                            const lineBreaksOn = d?.add_line_breaks_between_items !== false;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Converts list input to a single string for prompts (joined lines or spaces), or to a pretty-printed JSON array for pairing with String to List. Wire a List primitive or Start list slot to the input handle."
                                    />
                                    <InspectorSection title="Output format">
                                        <div className="flex flex-col gap-2">
                                            <label className="flex items-center gap-2 text-xs text-mw-text-primary cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    checked={useJson}
                                                    onChange={e =>
                                                        updateSelectedNodeData({
                                                            use_text_join: e.target.checked ? false : true,
                                                            ...(e.target.checked ? {} : { add_line_breaks_between_items: true }),
                                                        })
                                                    }
                                                    className="rounded border-mw-border"
                                                />
                                                <span>Output as JSON array</span>
                                            </label>
                                            <p className="text-[10px] text-mw-text-secondary">
                                                Use JSON when feeding <strong className="font-medium text-mw-text-primary">String to List</strong> for a round-trip. Otherwise leave off for plain joined text.
                                            </p>
                                            <label
                                                className={`flex items-center gap-2 text-xs cursor-pointer ${
                                                    useJson ? 'text-mw-text-muted pointer-events-none opacity-60' : 'text-mw-text-primary'
                                                }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={lineBreaksOn}
                                                    disabled={useJson}
                                                    onChange={e => updateSelectedNodeData({ add_line_breaks_between_items: e.target.checked })}
                                                    className="rounded border-mw-border"
                                                />
                                                <span>Add line breaks between items</span>
                                            </label>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'stringToList' && (
                            <InspectorSection
                                title="About"
                                description="Parses a JSON array string into a list. Wire a String primitive, LLM output, or Start string slot to the input. For a round-trip with List to String, set that node to Output as JSON array."
                            />
                        )}

                        {/* Len from List utility nodes */}
                        {selectedNode.type === 'lenFromList' && (
                            <InspectorSection
                                title="About"
                                description="Returns the length of the list. Wire a List primitive or Start list slot to the list input."
                            />
                        )}
                        {selectedNode.type === 'randomItemFromList' && (
                            <InspectorSection
                                title="About"
                                description="Returns one uniformly random element from the wired list (output type follows the picked element: string, list, dictionary, int, or boolean). Empty lists fail the step. Uses a cryptographic index choice per run."
                            />
                        )}

                        {selectedNode.type === 'sandboxTickItems' && (() => {
                            const d = selectedNode.data as { item_type?: 'all' | 'food' };
                            const itemType = d?.item_type === 'food' ? 'food' : 'all';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Returns world.items as a list of serialized item dicts from a wired SandboxTickInput (Start sandbox_tick or a tick-shaped dictionary). Optionally filter by item type."
                                    />
                                    <InspectorSection title="Item type">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">item_type</label>
                                            <select
                                                value={itemType}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        item_type: e.target.value as 'all' | 'food',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="all">All</option>
                                                <option value="food">Food</option>
                                            </select>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}
                        {selectedNode.type === 'sandboxWorldGrid' && (
                            <InspectorSection
                                title="About"
                                description="Returns board size as { width, height } from a wired SandboxTickInput (same tick wiring as other sandbox tick utilities)."
                            />
                        )}
                        {selectedNode.type === 'sandboxAvailableCells' && (
                            <InspectorSection
                                title="About"
                                description="Returns a list of { x, y } cell dicts for every grid cell not occupied by the pet or any item (row-major order), from a wired SandboxTickInput."
                            />
                        )}
                        {selectedNode.type === 'sandboxTickPet' && (
                            <InspectorSection
                                title="About"
                                description="Returns the validated pet subtree (hunger, energy, mood, position, intent) as a dictionary—use for reliable wiring instead of ad-hoc tick slicing."
                            />
                        )}
                        {selectedNode.type === 'sandboxNearestItemByType' && (() => {
                            const d = selectedNode.data as { required_inputs?: RequiredInput[] };
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'sandbox_tick')) {
                                requiredInputs = [
                                    ...requiredInputs,
                                    { key: 'sandbox_tick', type: 'dictionary', value: null },
                                ];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'item_type')) {
                                requiredInputs = [
                                    ...requiredInputs,
                                    { key: 'item_type', type: 'string', value: 'food' },
                                ];
                            }
                            const itemIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'item_type');
                            const rawVal = requiredInputs[itemIdx]?.value;
                            const itemType =
                                typeof rawVal === 'string' && rawVal.trim().toLowerCase() === 'all'
                                    ? 'all'
                                    : 'food';
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Returns one serialized item dict as dictionary output, or an empty object {} when no item matches. Minimum Manhattan distance from the pet to items matching item_type; ties break by world.items order. Unlike sandbox_filter_items_by_type, this picks a single nearest item (same geometry as Get Closest Item)."
                                    />
                                    <InspectorSection title="Item type">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                item_type
                                            </label>
                                            <select
                                                value={itemType}
                                                onChange={e => {
                                                    const v = e.target.value as 'all' | 'food';
                                                    const idx = requiredInputs.findIndex(
                                                        (i: RequiredInput) => i.key === 'item_type',
                                                    );
                                                    if (idx >= 0) updateInput(idx, { value: v });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="all">All</option>
                                                <option value="food">Food</option>
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Or wire the item_type input handle.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}
                        {selectedNode.type === 'sandboxClosestItem' && (() => {
                            const d = selectedNode.data as { required_inputs?: RequiredInput[] };
                            let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'sandbox_tick')) {
                                requiredInputs = [
                                    ...requiredInputs,
                                    { key: 'sandbox_tick', type: 'dictionary', value: null },
                                ];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'item_type')) {
                                requiredInputs = [
                                    ...requiredInputs,
                                    { key: 'item_type', type: 'string', value: 'food' },
                                ];
                            }
                            const itemIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'item_type');
                            const rawVal = requiredInputs[itemIdx]?.value;
                            const itemType =
                                typeof rawVal === 'string' && rawVal.trim().toLowerCase() === 'all'
                                    ? 'all'
                                    : 'food';
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Same output as Sandbox nearest item by type: one serialized item dict, or {} when no item matches. Use whichever palette label you prefer."
                                    />
                                    <InspectorSection title="Item type">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                item_type
                                            </label>
                                            <select
                                                value={itemType}
                                                onChange={e => {
                                                    const v = e.target.value as 'all' | 'food';
                                                    const idx = requiredInputs.findIndex(
                                                        (i: RequiredInput) => i.key === 'item_type',
                                                    );
                                                    if (idx >= 0) updateInput(idx, { value: v });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="all">All</option>
                                                <option value="food">Food</option>
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Or wire the item_type input handle.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}
                        {selectedNode.type === 'sandboxDecisionMoveTo' && (
                            <InspectorSection
                                title="About"
                                description="Builds a DecisionIntent with action move_to. Wire exactly one of target_item_id or target_cell (same rules as sandbox_decision_intent)."
                            />
                        )}
                        {selectedNode.type === 'sandboxFilterItemsByType' && (
                            <InspectorSection
                                title="About"
                                description="Filters a list of serialized sandbox items by type (V1: food). Wire items and optional item_type, or set item_type inline."
                            />
                        )}
                        {selectedNode.type === 'sandboxDecisionIntent' && (
                            <InspectorSection
                                title="About"
                                description="Builds and validates a DecisionIntent dictionary for Stop. Wire action and optional targets, or set defaults inline."
                            />
                        )}
                        {selectedNode.type === 'sandboxStarterDecision' && (
                            <InspectorSection
                                title="About"
                                description="Runs the built-in starter deterministic policy (same priorities as the legacy Sandbox behavior primitive)."
                            />
                        )}
                        {selectedNode.type === 'sandboxPetHunger' && (
                            <InspectorSection
                                title="About"
                                description="Reads pet.hunger from a wired SandboxTickInput (Start sandbox_tick or a tick-shaped dictionary)."
                            />
                        )}
                        {selectedNode.type === 'sandboxPetEnergy' && (
                            <InspectorSection
                                title="About"
                                description="Reads pet.energy from a wired SandboxTickInput (Start sandbox_tick or a tick-shaped dictionary)."
                            />
                        )}
                        {selectedNode.type === 'sandboxPetCell' && (
                            <InspectorSection
                                title="About"
                                description="Returns pet.position as a dictionary { x, y } for wiring into Sandbox is nearby8 (cell_a / cell_b) or other cell-aware steps—same tick wiring as pet hunger/energy."
                            />
                        )}
                        {selectedNode.type === 'sandboxIsNearby8' && (
                            <InspectorSection
                                title="About"
                                description="True when two grid cells are 8-neighbors (including diagonals), excluding the same cell. Each input expects a JSON object with integer x and y."
                            />
                        )}
                        {selectedNode.type === 'sandboxFirstNearbyFood' && (
                            <InspectorSection
                                title="About"
                                description="Returns at most one food item: the first in world.items order that is adjacent to the pet (starter eat-nearby ordering)."
                            />
                        )}
                        {selectedNode.type === 'sandboxFirstFoodWorldOrder' && (
                            <InspectorSection
                                title="About"
                                description="Returns at most one food item: the first food in world.items iteration order (starter seek / foods[0])."
                            />
                        )}

                        {selectedNode.type === 'intToString' && (
                            <InspectorSection
                                title="About"
                                description="Converts an integer to its decimal string (e.g. for prompts or Stop string outputs). Wire an Int primitive, int math output, Len from List, or Start int slot. String inputs must be a single parseable integer (same rules as int slots elsewhere)."
                            />
                        )}

                        {/* List Item by Index utility nodes */}
                        {selectedNode.type === 'listItemByIndex' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'index')) requiredInputs = [...requiredInputs, { key: 'index', type: 'int' as const, value: 0 }];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'list')) requiredInputs = [...requiredInputs, { key: 'list', type: 'list' as const, value: null }];
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const indexInput = requiredInputs.find((i: RequiredInput) => i.key === 'index');
                            const indexVal = indexInput?.value ?? 0;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Returns the item at the given index in the list. Wire index (int) and list inputs, or set index inline. Out-of-bounds indices raise an error."
                                    />
                                    <InspectorSection title="Index">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Index (index handle)</label>
                                            <input
                                                type="number"
                                                min={0}
                                                value={typeof indexVal === 'number' ? indexVal : 0}
                                                onChange={e => {
                                                    const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'index');
                                                    const val = parseInt(e.target.value, 10);
                                                    if (idx >= 0) updateInput(idx, { value: isNaN(val) ? 0 : val });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">Or wire from an Int primitive or Len from List.</p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'addToList' && (
                            <InspectorSection
                                title="About"
                                description="Appends a value to a list (any primitive or structured item). Wire list (required) and value. In a For loop body, list state carries across iterations so you can accumulate without a List primitive holding state."
                            />
                        )}

                        {selectedNode.type === 'addDays' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'input')) {
                                requiredInputs = [...requiredInputs, { key: 'input', type: 'datetime' as const, value: null }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'days')) {
                                requiredInputs = [...requiredInputs, { key: 'days', type: 'int' as const, value: 0 }];
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const daysIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'days');
                            const daysVal = daysIdx >= 0 ? requiredInputs[daysIdx]?.value : 0;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Adds a signed number of whole days to an RFC3339 instant (UTC-aware timedelta). Wire input from a DateTime primitive or another datetime output; set days inline (e.g. -5 for five days earlier) or wire an Int."
                                    />
                                    <InspectorSection title="Days">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Days (days handle)</label>
                                            <input
                                                type="number"
                                                value={typeof daysVal === 'number' ? daysVal : 0}
                                                onChange={e => {
                                                    const v = parseInt(e.target.value, 10);
                                                    if (daysIdx >= 0) updateInput(daysIdx, { value: Number.isNaN(v) ? 0 : v });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">Negative values subtract days from the instant.</p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'readDocumentProperty' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'target_property')) {
                                requiredInputs = [...requiredInputs, { key: 'target_property', type: 'string' as const, value: '' }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'document')) {
                                requiredInputs = [...requiredInputs, { key: 'document', type: 'document' as const, value: null }];
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const tpInput = requiredInputs.find((i: RequiredInput) => i.key === 'target_property');
                            const tpIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'target_property');
                            const tpStr = tpInput?.value != null ? String(tpInput.value) : '';
                            const ovt = d?.output_value_type;
                            const outputValueType =
                                ovt === 'string' ||
                                ovt === 'list' ||
                                ovt === 'dictionary' ||
                                ovt === 'boolean' ||
                                ovt === 'int' ||
                                ovt === 'datetime'
                                    ? ovt
                                    : 'string';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Reads a field from a Document primitive output (id, name, description, body). Wire the Document output to the document handle; set target_property (e.g. body) and output type."
                                    />
                                    <InspectorSection title="Target property">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                target_property (target_property handle)
                                            </label>
                                            <input
                                                type="text"
                                                value={tpStr}
                                                onChange={e => {
                                                    if (tpIdx >= 0) updateInput(tpIdx, { value: e.target.value });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                placeholder="e.g. body"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Output type">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Primitive type of value</label>
                                            <select
                                                value={outputValueType}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        output_value_type: e.target.value as
                                                            | 'string'
                                                            | 'list'
                                                            | 'dictionary'
                                                            | 'boolean'
                                                            | 'int'
                                                            | 'datetime',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="string">String</option>
                                                <option value="list">List</option>
                                                <option value="dictionary">Dictionary</option>
                                                <option value="boolean">Boolean</option>
                                                <option value="int">Int</option>
                                                <option value="datetime">DateTime</option>
                                            </select>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'loadDocument' && (
                            <InspectorSection
                                title="About"
                                description="Load a saved document at run time. Provide exactly one of document_id or document_name (wire a handle or set inline). Outputs the same document shape as the Document primitive."
                            />
                        )}
                        {selectedNode.type === 'upsertDocument' && (() => {
                            const d = selectedNode.data as any;
                            const requiredInputs = normalizeUpsertDocumentRequiredInputs(d?.required_inputs ?? null);
                            const updateInputIdx = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const nameIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'name');
                            const contentIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'content');
                            const wmIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'write_mode');
                            const exIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'existing_document_id');

                            const nameStr =
                                nameIdx >= 0 && requiredInputs[nameIdx]?.value != null
                                    ? String(requiredInputs[nameIdx].value)
                                    : '';
                            const contentStr =
                                contentIdx >= 0 && requiredInputs[contentIdx]?.value != null
                                    ? String(requiredInputs[contentIdx].value)
                                    : '';
                            const wmRaw =
                                wmIdx >= 0 && requiredInputs[wmIdx]?.value != null
                                    ? String(requiredInputs[wmIdx].value).trim().toLowerCase()
                                    : 'replace';
                            const writeModeVal =
                                wmRaw === 'append' ? 'append' : wmRaw === 'merge_json' ? 'merge_json' : 'replace';
                            const existingIdStr =
                                exIdx >= 0 && requiredInputs[exIdx]?.value != null
                                    ? String(requiredInputs[exIdx].value)
                                    : '';

                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Persist text into Configure → Documents. Document name must be unique among visible documents. Wired inputs override inline values when a wire delivers a value."
                                    />
                                    <InspectorSection title="Document name">
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                            name handle
                                        </label>
                                        <input
                                            type="text"
                                            value={nameStr}
                                            onChange={e => {
                                                if (nameIdx >= 0)
                                                    updateInputIdx(nameIdx, { value: e.target.value });
                                            }}
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                            placeholder="e.g. Episode 42 transcript"
                                        />
                                        <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                            Or wire a string into the canvas name handle for a dynamic title.
                                        </p>
                                    </InspectorSection>
                                    {contentIdx >= 0 ? (
                                        <InspectorSection title="Document body (optional inline)">
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                content handle
                                            </label>
                                            <textarea
                                                value={contentStr}
                                                onChange={e => {
                                                    if (contentIdx >= 0)
                                                        updateInputIdx(contentIdx, { value: e.target.value });
                                                }}
                                                rows={6}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 font-mono whitespace-pre-wrap"
                                                placeholder={
                                                    requiredInputs.length <= 2
                                                        ? 'Leave empty and wire transcript text…'
                                                        : 'Leave empty and wire upstream text…'
                                                }
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Usually wired from transcription or LLM output; use this only for static preview text or small snippets.
                                            </p>
                                        </InspectorSection>
                                    ) : null}
                                    {exIdx >= 0 ? (
                                        <InspectorSection title="Existing row (optional)">
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                existing_document_id
                                            </label>
                                            <input
                                                type="text"
                                                value={existingIdStr}
                                                onChange={e => {
                                                    const t = e.target.value.trim();
                                                    if (exIdx >= 0) {
                                                        updateInputIdx(exIdx, {
                                                            value:
                                                                t === '' ? null : t,
                                                        });
                                                    }
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 font-mono"
                                                placeholder="UUID of an existing document you own (optional)"
                                            />
                                        </InspectorSection>
                                    ) : null}
                                    {wmIdx >= 0 ? (
                                        <InspectorSection title="Write mode">
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                write_mode
                                            </label>
                                            <select
                                                value={writeModeVal}
                                                onChange={e => {
                                                    if (wmIdx >= 0) updateInputIdx(wmIdx, { value: e.target.value });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                            >
                                                <option value="replace">replace — set body from content</option>
                                                <option value="append">append — add after existing body</option>
                                                <option value="merge_json">
                                                    merge_json — merge JSON objects (both sides JSON)
                                                </option>
                                            </select>
                                        </InspectorSection>
                                    ) : null}
                                </>
                            );
                        })()}
                        {selectedNode.type === 'parseDocumentBody' && (
                            <InspectorSection
                                title="About"
                                description="Parses the document body text as JSON. Root must be an object or array. Wire a Document output to the document handle."
                            />
                        )}
                        {selectedNode.type === 'htmlParseBasic' && (() => {
                            const d = selectedNode.data as {
                                granularity?: string | null;
                                content_root_css?: string | null;
                            };
                            const g = d?.granularity;
                            const granSelect =
                                g === 'list_items' || g === 'articles' ? g : 'default';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Parses raw HTML into title, text blocks, and links (structural; no main-content or boilerplate removal). Title always comes from the full document. Optional content_root_css limits blocks, links, and segment extraction to a subtree. Wire a string (e.g. Fetch URL body via Dictionary value by key) to the html handle."
                                    />
                                    <InspectorSection
                                        title="Options"
                                        description="Granularity default matches legacy output only. list_items and articles add segment_text_blocks and parse_options. content_root_css is a CSS selector (e.g. main, #content); if set and no node matches, the step errors."
                                    >
                                        <div className="mb-2">
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                granularity
                                            </label>
                                            <select
                                                value={granSelect}
                                                onChange={e => {
                                                    const v = e.target.value;
                                                    if (v === 'default') {
                                                        updateSelectedNodeData({}, ['granularity']);
                                                    } else {
                                                        updateSelectedNodeData({ granularity: v });
                                                    }
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="default">default (legacy output shape)</option>
                                                <option value="list_items">list_items</option>
                                                <option value="articles">articles</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                                content_root_css
                                            </label>
                                            <input
                                                type="text"
                                                value={
                                                    typeof d?.content_root_css === 'string'
                                                        ? d.content_root_css
                                                        : ''
                                                }
                                                onChange={e => {
                                                    const t = e.target.value;
                                                    if (t.trim() === '') {
                                                        updateSelectedNodeData({}, ['content_root_css']);
                                                    } else {
                                                        updateSelectedNodeData({ content_root_css: t });
                                                    }
                                                }}
                                                placeholder="main, .content, #default – leave empty for full page"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 font-mono"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}
                        {selectedNode.type === 'writeObjectToDocumentBody' && (
                            <InspectorSection
                                title="About"
                                description="Serializes a list or dictionary to deterministic JSON text suitable for storing in a document body."
                            />
                        )}
                        {selectedNode.type === 'appendValueToDocument' && (
                            <InspectorSection
                                title="About"
                                description="Appends a serialized value to the document body text (does not persist). Chain to Upsert Document to save."
                            />
                        )}
                        {selectedNode.type === 'validateAgainstStructure' && (() => {
                            const d = selectedNode.data as { structure_id?: string | null };
                            const sid = d?.structure_id ?? '';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Validates a value against a Structure JSON Schema. Wire a Structure primitive to structure, or set structure_id (UUID) below when not wiring."
                                    />
                                    <InspectorSection title="Structure id (optional)">
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">structure_id</label>
                                        <input
                                            type="text"
                                            value={sid}
                                            onChange={e => updateSelectedNodeData({ structure_id: e.target.value || null })}
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 font-mono"
                                            placeholder="UUID when not wiring Structure"
                                        />
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'dictionaryValueByKey' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'key')) {
                                requiredInputs = [...requiredInputs, { key: 'key', type: 'string' as const, value: '' }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'dictionary')) {
                                requiredInputs = [...requiredInputs, { key: 'dictionary', type: 'dictionary' as const, value: null }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'fallback')) {
                                requiredInputs = [...requiredInputs, { key: 'fallback', type: 'any' as const, value: null }];
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const keyInput = requiredInputs.find((i: RequiredInput) => i.key === 'key');
                            const keyIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'key');
                            const keyStr = keyInput?.value != null ? String(keyInput.value) : '';
                            const ovt = d?.output_value_type;
                            const outputValueType =
                                ovt === 'string' ||
                                ovt === 'list' ||
                                ovt === 'dictionary' ||
                                ovt === 'boolean' ||
                                ovt === 'int' ||
                                ovt === 'datetime'
                                    ? ovt
                                    : 'list';
                            const fallbackTextareaValue = Object.prototype.hasOwnProperty.call(d, 'fallback_value')
                                ? JSON.stringify(d.fallback_value, null, 2)
                                : '';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Reads a value by key from a dictionary. Set output type to match the value. If the key is missing or the value is null, a configured fallback (optional static JSON below, or the fallback input when wired) is used; a wire to fallback overrides static. If the key exists and the value is the wrong JSON type, the step still errors (fallback is not used for type mismatch)."
                                    />
                                    <InspectorSection title="Key">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Key (key handle)</label>
                                            <input
                                                type="text"
                                                value={keyStr}
                                                onChange={e => {
                                                    if (keyIdx >= 0) updateInput(keyIdx, { value: e.target.value });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                placeholder="e.g. randomIntList"
                                            />
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Output type">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Primitive type of value</label>
                                            <select
                                                value={outputValueType}
                                                onChange={e =>
                                                    updateSelectedNodeData({
                                                        output_value_type: e.target.value as
                                                            | 'string'
                                                            | 'list'
                                                            | 'dictionary'
                                                            | 'boolean'
                                                            | 'int'
                                                            | 'datetime',
                                                    })
                                                }
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            >
                                                <option value="string">String</option>
                                                <option value="list">List</option>
                                                <option value="dictionary">Dictionary</option>
                                                <option value="boolean">Boolean</option>
                                                <option value="int">Int</option>
                                                <option value="datetime">DateTime</option>
                                            </select>
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Must match the JSON type at that key (int excludes booleans). Same type rules apply to fallback when used.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection
                                        title="Fallback (optional)"
                                        description="Valid JSON only. Cleared field removes static fallback. Optional fallback input handle overrides this when connected."
                                    >
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">Static fallback (JSON)</label>
                                        <textarea
                                            rows={4}
                                            defaultValue={fallbackTextareaValue}
                                            key={
                                                `${selectedNode.id}-fb-` +
                                                (Object.prototype.hasOwnProperty.call(d, 'fallback_value')
                                                    ? JSON.stringify(d.fallback_value)
                                                    : 'none')
                                            }
                                            onBlur={e => {
                                                const t = e.target.value.trim();
                                                if (!t) {
                                                    updateSelectedNodeData({}, ['fallback_value']);
                                                    return;
                                                }
                                                try {
                                                    const v = JSON.parse(t) as unknown;
                                                    updateSelectedNodeData({ fallback_value: v });
                                                } catch {
                                                    /* keep previous value; user can fix and blur again */
                                                }
                                            }}
                                            className="w-full min-h-[5rem] px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 font-mono"
                                            placeholder='e.g. [] or "default"'
                                        />
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'dictionarySetValueByKey' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'dictionary')) {
                                requiredInputs = [...requiredInputs, { key: 'dictionary', type: 'dictionary' as const, value: null }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'key')) {
                                requiredInputs = [...requiredInputs, { key: 'key', type: 'string' as const, value: '' }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'value')) {
                                requiredInputs = [...requiredInputs, { key: 'value', type: 'any' as const, value: null }];
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const keyInput = requiredInputs.find((i: RequiredInput) => i.key === 'key');
                            const keyIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'key');
                            const keyStr = keyInput?.value != null ? String(keyInput.value) : '';
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Shallow-copies the input dictionary and sets one top-level key to the resolved value (any type). Wire dictionary, key, and value; use static key here when not wiring the key handle. Output is always a dictionary."
                                    />
                                    <InspectorSection title="Key">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Key (key handle)</label>
                                            <input
                                                type="text"
                                                value={keyStr}
                                                onChange={e => {
                                                    if (keyIdx >= 0) updateInput(keyIdx, { value: e.target.value });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                placeholder="e.g. summaries"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Wire the value handle from list outputs, primitives, or other steps; static JSON in the graph for value is also supported.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {['addInts', 'subtractInts', 'multiplyInts', 'divideInts', 'moduloInts', 'minInts', 'maxInts'].includes(selectedNode.type ?? '') &&
                            (() => {
                                const d = selectedNode.data as any;
                                let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                                if (!requiredInputs.some((i: RequiredInput) => i.key === 'input_a')) {
                                    requiredInputs = [...requiredInputs, { key: 'input_a', type: 'int' as const, value: 0 }];
                                }
                                if (!requiredInputs.some((i: RequiredInput) => i.key === 'input_b')) {
                                    requiredInputs = [...requiredInputs, { key: 'input_b', type: 'int' as const, value: 0 }];
                                }
                                const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                    const next = [...requiredInputs];
                                    next[idx] = { ...next[idx], ...patch };
                                    updateSelectedNodeData({ required_inputs: next });
                                };
                                const inputAIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'input_a');
                                const inputBIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'input_b');
                                const aVal = inputAIdx >= 0 ? requiredInputs[inputAIdx]?.value : 0;
                                const bVal = inputBIdx >= 0 ? requiredInputs[inputBIdx]?.value : 0;
                                const aboutDivide =
                                    selectedNode.type === 'divideInts'
                                        ? 'Integer division truncates toward zero (e.g. -7/3 → -2). input_b must not be zero.'
                                        : selectedNode.type === 'moduloInts'
                                          ? 'Python-style %; divisor input_b must not be zero.'
                                          : 'Wire two int sources or set A and B inline.';
                                return (
                                    <>
                                        <InspectorSection title="About" description={aboutDivide} />
                                        <InspectorSection title="Inputs">
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">A (input_a)</label>
                                                <input
                                                    type="number"
                                                    value={typeof aVal === 'number' ? aVal : 0}
                                                    onChange={e => {
                                                        const v = parseInt(e.target.value, 10);
                                                        if (inputAIdx >= 0) updateInput(inputAIdx, { value: isNaN(v) ? 0 : v });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">B (input_b)</label>
                                                <input
                                                    type="number"
                                                    value={typeof bVal === 'number' ? bVal : 0}
                                                    onChange={e => {
                                                        const v = parseInt(e.target.value, 10);
                                                        if (inputBIdx >= 0) updateInput(inputBIdx, { value: isNaN(v) ? 0 : v });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                />
                                            </div>
                                        </InspectorSection>
                                    </>
                                );
                            })()}

                        {/* Basic Conditional control nodes */}
                        {selectedNode.type === 'basicConditional' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'condition')) {
                                requiredInputs = [...requiredInputs, { key: 'condition', type: 'boolean' as const, value: null }];
                            }
                            const conditionInput = requiredInputs.find((i: RequiredInput) => i.key === 'condition');
                            const conditionValue = conditionInput?.value ?? d?.condition;
                            const boolVal = conditionValue === true || (typeof conditionValue === 'string' && conditionValue.toLowerCase() === 'true');
                            const updateCondition = (val: boolean | null) => {
                                const idx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'condition');
                                if (idx >= 0) {
                                    const next = [...requiredInputs];
                                    next[idx] = { ...next[idx], value: val };
                                    updateSelectedNodeData({ required_inputs: next });
                                } else {
                                    updateSelectedNodeData({ required_inputs: [...requiredInputs, { key: 'condition', type: 'boolean' as const, value: val }] });
                                }
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Wire or set condition. True triggers True branch; False triggers False branch."
                                    />
                                    <InspectorSection title="Condition">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Condition (Condition handle)</label>
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="checkbox"
                                                    id="cond-true"
                                                    checked={boolVal === true}
                                                    onChange={e => updateCondition(e.target.checked)}
                                                    className="w-4 h-4 rounded border-mw-border text-emerald-600 focus:ring-emerald-500"
                                                />
                                                <label htmlFor="cond-true" className="text-xs text-mw-text-primary">True (or wire from Boolean/upstream)</label>
                                            </div>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {/* Is? control nodes */}
                        {selectedNode.type === 'isControl' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'input_a')) requiredInputs = [...requiredInputs, { key: 'input_a', type: 'string' as const, value: null }];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'input_b')) requiredInputs = [...requiredInputs, { key: 'input_b', type: 'string' as const, value: null }];
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const inputAIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'input_a');
                            const inputBIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'input_b');
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Compares for equality; any type (string, list, dictionary, or wired from upstream)."
                                    />
                                    <InspectorSection title="Inputs">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Input A (A handle)</label>
                                            <input
                                                type="text"
                                                value={(inputAIdx >= 0 ? requiredInputs[inputAIdx]?.value : null) as string ?? ''}
                                                onChange={e => inputAIdx >= 0 && updateInput(inputAIdx, { value: e.target.value || null })}
                                                placeholder="Or wire from upstream"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Input B (B handle)</label>
                                            <input
                                                type="text"
                                                value={(inputBIdx >= 0 ? requiredInputs[inputBIdx]?.value : null) as string ?? ''}
                                                onChange={e => inputBIdx >= 0 && updateInput(inputBIdx, { value: e.target.value || null })}
                                                placeholder="Or wire from upstream"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-500"
                                            />
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'isEmptyControl' && (
                            <InspectorSection
                                title="About"
                                description="Branches True when the wired value is an empty list [] or empty object {}; False when it has at least one element or key. Value must be a list or dictionary."
                            />
                        )}

                        {/* Gt?, Lt?, Gte?, Lte? control nodes */}
                        {['gtControl', 'ltControl', 'gteControl', 'lteControl'].includes(selectedNode.type ?? '') && (
                            <InspectorSection
                                title="About"
                                description={
                                    <>
                                        {selectedNode.type === 'gtControl' && 'A > B: True if A is greater than B.'}
                                        {selectedNode.type === 'ltControl' && 'A < B: True if A is less than B.'}
                                        {selectedNode.type === 'gteControl' && 'A >= B: True if A is greater than or equal to B.'}
                                        {selectedNode.type === 'lteControl' && 'A <= B: True if A is less than or equal to B.'}
                                        {' Wire A and B from Int, Len from List, or other numeric/string sources.'}
                                    </>
                                }
                            />
                        )}

                        {/* And, Or, Xor control nodes */}
                        {['andControl', 'orControl', 'xorControl'].includes(selectedNode.type ?? '') && (
                            <InspectorSection
                                title="About"
                                description={
                                    <>
                                        {selectedNode.type === 'andControl' && 'Outputs true when both A and B are true.'}
                                        {selectedNode.type === 'orControl' && 'Outputs true when A or B (or both) is true.'}
                                        {selectedNode.type === 'xorControl' && 'Outputs true when exactly one of A or B is true.'}
                                        {' Wire A and B from Boolean primitives or condition branches.'}
                                    </>
                                }
                            />
                        )}

                        {selectedNode.type === 'notControl' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'input')) {
                                requiredInputs = [...requiredInputs, { key: 'input', type: 'boolean' as const, value: null }];
                            }
                            const inputIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'input');
                            const inputVal = inputIdx >= 0 ? requiredInputs[inputIdx]?.value : null;
                            const boolVal = inputVal === true || (typeof inputVal === 'string' && inputVal.toLowerCase() === 'true');
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Logical NOT: output is the opposite of the boolean input."
                                    />
                                    <InspectorSection title="Input">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Value (input handle)</label>
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="checkbox"
                                                    id="not-input"
                                                    checked={boolVal === true}
                                                    onChange={e => {
                                                        if (inputIdx >= 0) updateInput(inputIdx, { value: e.target.checked });
                                                    }}
                                                    className="w-4 h-4 rounded border-mw-border text-indigo-600 focus:ring-indigo-500"
                                                />
                                                <label htmlFor="not-input" className="text-xs text-mw-text-primary">True (or wire from Boolean/upstream)</label>
                                            </div>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'betweenControl' && (() => {
                            const d = selectedNode.data as any;
                            const requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            const ensure = (key: string) => {
                                if (!requiredInputs.some((i: RequiredInput) => i.key === key)) {
                                    requiredInputs.push({ key, type: 'int' as const, value: 0 });
                                }
                            };
                            ensure('low');
                            ensure('value');
                            ensure('high');
                            const updateInput = (idx: number, patch: Partial<RequiredInput>) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            const lowIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'low');
                            const valueIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'value');
                            const highIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'high');
                            const num = (v: unknown) => (typeof v === 'number' ? v : 0);
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="True branch when low ≤ value ≤ high (inclusive). Requires low ≤ high or the step errors."
                                    />
                                    <InspectorSection title="Bounds">
                                        <div className="space-y-2">
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">low</label>
                                                <input
                                                    type="number"
                                                    value={num(lowIdx >= 0 ? requiredInputs[lowIdx]?.value : 0)}
                                                    onChange={e => {
                                                        const v = parseInt(e.target.value, 10);
                                                        if (lowIdx >= 0) updateInput(lowIdx, { value: isNaN(v) ? 0 : v });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">value</label>
                                                <input
                                                    type="number"
                                                    value={num(valueIdx >= 0 ? requiredInputs[valueIdx]?.value : 0)}
                                                    onChange={e => {
                                                        const v = parseInt(e.target.value, 10);
                                                        if (valueIdx >= 0) updateInput(valueIdx, { value: isNaN(v) ? 0 : v });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-xs font-medium text-mw-text-secondary block mb-1">high</label>
                                                <input
                                                    type="number"
                                                    value={num(highIdx >= 0 ? requiredInputs[highIdx]?.value : 0)}
                                                    onChange={e => {
                                                        const v = parseInt(e.target.value, 10);
                                                        if (highIdx >= 0) updateInput(highIdx, { value: isNaN(v) ? 0 : v });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                                />
                                            </div>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'tryCatchControl' && (() => {
                            const d = selectedNode.data as { label?: string; required_inputs?: RequiredInput[] };
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [
                                { key: 'value', type: 'any', value: null },
                            ];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'value')) {
                                requiredInputs = [...requiredInputs, { key: 'value', type: 'any', value: null }];
                            }
                            const inputIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'value');
                            const rawValPiece =
                                inputIdx >= 0 && requiredInputs[inputIdx]?.value !== undefined
                                    ? requiredInputs[inputIdx].value
                                    : null;
                            const rawValDisplay =
                                rawValPiece === null || rawValPiece === undefined
                                    ? ''
                                    : typeof rawValPiece === 'string'
                                      ? rawValPiece
                                      : String(rawValPiece);
                            const updateInput = (patch: Partial<RequiredInput>) => {
                                if (inputIdx >= 0) {
                                    const next = [...requiredInputs];
                                    next[inputIdx] = { ...next[inputIdx], ...patch };
                                    updateSelectedNodeData({ required_inputs: next });
                                }
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="Try wires to the guarded body; Catch runs after a failing step inside Try. Outputs: value on success (optional wired input); envelope summarizes success vs caught errors."
                                    />
                                    <InspectorSection title="Optional value (wired)">
                                        <p className="text-[10px] text-mw-text-secondary mb-2">
                                            Normally leave empty and rely on upstream outputs; wire the left handle only when you want a surfaced value on successful runs.
                                        </p>
                                        <input
                                            type="text"
                                            value={rawValDisplay}
                                            placeholder="manual test value (prefer wiring from upstream)"
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e => {
                                                const t = e.target.value;
                                                updateInput({ value: t.trim() === '' ? null : t });
                                            }}
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                        />
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'forLoopControl' && (() => {
                            type IterMode = 'sequential' | 'parallel' | 'batched';
                            const d = selectedNode.data as {
                                iteration_mode?: IterMode;
                                parallel_iterations?: boolean;
                                batch_size?: number;
                                continue_on_error?: boolean;
                                max_iterations?: number;
                                required_inputs?: RequiredInput[];
                            };
                            let iter: IterMode = 'sequential';
                            if (typeof d.iteration_mode === 'string') {
                                if (d.iteration_mode === 'parallel' || d.iteration_mode === 'batched')
                                    iter = d.iteration_mode;
                                else if (d.iteration_mode === 'sequential') iter = 'sequential';
                            } else if (d.parallel_iterations === true) {
                                iter = 'parallel';
                            }
                            const batchSizeRaw =
                                typeof d.batch_size === 'number' && Number.isFinite(d.batch_size)
                                    ? Math.max(1, Math.floor(d.batch_size))
                                    : 2;
                            const maxIterationsRaw =
                                typeof d.max_iterations === 'number' && Number.isFinite(d.max_iterations)
                                    ? Math.max(1, Math.floor(d.max_iterations))
                                    : '';
                            const onIterChange = (next: IterMode) => {
                                if (next === 'parallel') {
                                    updateSelectedNodeData(
                                        {
                                            iteration_mode: 'parallel',
                                            parallel_iterations: true,
                                            batch_size: undefined,
                                            continue_on_error: undefined,
                                        },
                                        ['batch_size', 'continue_on_error'],
                                    );
                                } else if (next === 'batched') {
                                    updateSelectedNodeData(
                                        {
                                            iteration_mode: 'batched',
                                            parallel_iterations: undefined,
                                            batch_size: batchSizeRaw,
                                        },
                                        ['parallel_iterations'],
                                    );
                                } else {
                                    updateSelectedNodeData(
                                        {
                                            iteration_mode: 'sequential',
                                            parallel_iterations: undefined,
                                            batch_size: undefined,
                                            continue_on_error: undefined,
                                        },
                                        ['parallel_iterations', 'batch_size', 'continue_on_error'],
                                    );
                                }
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description={
                                            <>
                                                Wire the <strong className="font-medium text-mw-text-primary">list</strong>{' '}
                                                input from a List node or any list output.
                                                Use <strong className="font-medium text-mw-text-primary">signal</strong> and{' '}
                                                <strong className="font-medium text-mw-text-primary">item</strong> to drive the
                                                loop body (e.g. Workflow ref): each list element is exposed on{' '}
                                                <strong className="font-medium text-mw-text-primary">item</strong> for one body
                                                run. The{' '}
                                                <strong className="font-medium text-mw-text-primary">summary</strong> output carries
                                                an aggregated dictionary when batches or continuation options are enabled.
                                            </>
                                        }
                                    />
                                    <InspectorSection title="Execution mode">
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">Iterations</label>
                                        <select
                                            value={iter}
                                            onChange={e => onIterChange(e.target.value as IterMode)}
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            aria-label="For loop iteration mode"
                                        >
                                            <option value="sequential">Sequential (one item at a time)</option>
                                            <option value="parallel">Parallel (every item concurrently)</option>
                                            <option value="batched">Batched (chunks of items)</option>
                                        </select>
                                        {iter === 'parallel' ?
                                            <p className="text-[10px] text-mw-text-secondary mt-2 leading-snug">
                                                Each list item runs the loop body concurrently (isolated per item).
                                                Nested For Loops inside the parallel body remain disallowed on the server.
                                            </p>
                                        : iter === 'batched' ?
                                            <>
                                                <div className="mt-2 space-y-1">
                                                    <label className="text-xs font-medium text-mw-text-secondary block">
                                                        Batch size
                                                    </label>
                                                    <input
                                                        type="number"
                                                        min={1}
                                                        value={batchSizeRaw}
                                                        onFocus={recordGraphBeforeMutation}
                                                        onChange={e => {
                                                            const v = parseInt(e.target.value, 10);
                                                            if (Number.isNaN(v)) return;
                                                            updateSelectedNodeData({
                                                                batch_size: Math.max(1, Math.floor(v)),
                                                            });
                                                        }}
                                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                                    />
                                                    <label className="flex items-start gap-2 mt-3 cursor-pointer">
                                                        <input
                                                            type="checkbox"
                                                            checked={d.continue_on_error === true}
                                                            onChange={e =>
                                                                updateSelectedNodeData({
                                                                    continue_on_error: e.target.checked ? true : undefined,
                                                                })
                                                            }
                                                            className="mt-0.5 w-4 h-4 rounded border border-mw-border text-amber-600 focus:ring-amber-500"
                                                        />
                                                        <span>
                                                            <span className="text-xs font-medium text-mw-text-primary">
                                                                Continue batch on inner errors (summary records failures)
                                                            </span>
                                                            <p className="text-[10px] text-mw-text-secondary mt-0.5 leading-snug">
                                                                When unchecked, one failing iteration stops the batched loop.
                                                                When checked, successes and errors are surfaced on the{' '}
                                                                <strong className="font-medium text-mw-text-primary">summary</strong>{' '}
                                                                output.
                                                            </p>
                                                        </span>
                                                    </label>
                                                </div>
                                            </>
                                        :   null}
                                        <div className="mt-3 space-y-1">
                                            <label className="text-xs font-medium text-mw-text-secondary block">
                                                Max iterations (optional cap)
                                            </label>
                                            <input
                                                type="number"
                                                min={1}
                                                placeholder="no extra cap beyond server/graph limits"
                                                value={maxIterationsRaw === '' ? '' : maxIterationsRaw}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const trimmed = e.target.value.trim();
                                                    if (trimmed === '') {
                                                        updateSelectedNodeData({ max_iterations: undefined });
                                                        return;
                                                    }
                                                    const v = parseInt(trimmed, 10);
                                                    updateSelectedNodeData({
                                                        max_iterations: Number.isNaN(v)
                                                            ? undefined
                                                            : Math.max(1, Math.floor(v)),
                                                    });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary">
                                                Additional guard on iteration count besides global execution ceilings.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {selectedNode.type === 'forLoopEndControl' && (() => {
                            const d = selectedNode.data as { for_loop_id?: string; exports?: string[]; label?: string };
                            const exportsStr = Array.isArray(d.exports) ? d.exports.join(', ') : 'odds, evens';
                            return (
                                <InspectorSection title="For Loop End">
                                    <div className="space-y-3">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Paired For Loop node id</label>
                                            <input
                                                type="text"
                                                value={d.for_loop_id ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => patchSelectedNodeData({ for_loop_id: e.target.value.trim() })}
                                                placeholder="Same id as the For Loop node to pair with"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-1">
                                                Wiring <strong className="font-medium text-mw-text-primary">signal_out</strong> from the For Loop to this step&apos;s{' '}
                                                <strong className="font-medium text-mw-text-primary">trigger</strong> sets this automatically; override here if needed. Use{' '}
                                                <strong className="font-medium text-mw-text-primary">General → Node id</strong> on the For Loop to copy its id.
                                            </p>
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Export keys (comma-separated)</label>
                                            <input
                                                type="text"
                                                value={exportsStr}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const parts = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                                                    patchSelectedNodeData({ exports: parts.length > 0 ? parts : ['odds', 'evens'] });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-1">
                                                Wire each key as a target handle from body nodes. Connect <strong className="font-medium text-mw-text-primary">signal</strong> from the paired For Loop after the body is built.
                                            </p>
                                        </div>
                                    </div>
                                </InspectorSection>
                            );
                        })()}

                        {/* Prepend Text utility nodes */}
                        {selectedNode.type === 'prependText' && (() => {
                            const d = selectedNode.data as any;
                            let requiredInputs: RequiredInput[] = d?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'target_string')) requiredInputs = [...requiredInputs, { key: 'target_string', type: 'string' as const, value: null }];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'text_to_prepend')) requiredInputs = [...requiredInputs, { key: 'text_to_prepend', type: 'string' as const, value: null }];
                            const updateInput = (idx: number, patch: Partial<RequiredInput>, withHistory = true) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                if (withHistory) updateSelectedNodeData({ required_inputs: next });
                                else patchSelectedNodeData({ required_inputs: next });
                            };
                            const targetIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'target_string');
                            const prependIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'text_to_prepend');
                            return (
                                <InspectorSection title="Text">
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">Target String (Target handle)</label>
                                        <textarea
                                            value={(targetIdx >= 0 ? requiredInputs[targetIdx]?.value : null) as string ?? ''}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e =>
                                                targetIdx >= 0 && updateInput(targetIdx, { value: e.target.value || null }, false)
                                            }
                                            rows={3}
                                            placeholder="Or connect from upstream"
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-amber-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">Text to Prepend (Prepend handle)</label>
                                        <textarea
                                            value={(prependIdx >= 0 ? requiredInputs[prependIdx]?.value : null) as string ?? ''}
                                            onFocus={recordGraphBeforeMutation}
                                            onChange={e =>
                                                prependIdx >= 0 && updateInput(prependIdx, { value: e.target.value || null }, false)
                                            }
                                            rows={3}
                                            placeholder="Or connect from upstream"
                                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-amber-500"
                                        />
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="prepend-add-line"
                                            checked={d?.add_additional_line ?? false}
                                            onChange={e => updateSelectedNodeData({ add_additional_line: e.target.checked })}
                                            className="w-4 h-4 rounded border-mw-border text-amber-600 focus:ring-amber-500"
                                        />
                                        <label htmlFor="prepend-add-line" className="text-xs font-medium text-mw-text-primary">Add additional line (blank line between prepended text and target)</label>
                                    </div>
                                </InspectorSection>
                            );
                        })()}

                        {selectedNode.type === 'stringTrunc' && (() => {
                            let requiredInputs: RequiredInput[] = (selectedNode.data as any)?.required_inputs ?? [];
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'target_string')) {
                                requiredInputs = [...requiredInputs, { key: 'target_string', type: 'string' as const, value: null }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'start_index')) {
                                requiredInputs = [...requiredInputs, { key: 'start_index', type: 'int' as const, value: 0 }];
                            }
                            if (!requiredInputs.some((i: RequiredInput) => i.key === 'end_index')) {
                                requiredInputs = [...requiredInputs, { key: 'end_index', type: 'int' as const, value: -1 }];
                            }
                            const updateInput = (idx: number, patch: Partial<RequiredInput>, withHistory = true) => {
                                const next = [...requiredInputs];
                                next[idx] = { ...next[idx], ...patch };
                                if (withHistory) updateSelectedNodeData({ required_inputs: next });
                                else patchSelectedNodeData({ required_inputs: next });
                            };
                            const targetIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'target_string');
                            const startIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'start_index');
                            const endIdx = requiredInputs.findIndex((i: RequiredInput) => i.key === 'end_index');
                            const startVal = startIdx >= 0 ? requiredInputs[startIdx]?.value : 0;
                            const endVal = endIdx >= 0 ? requiredInputs[endIdx]?.value : -1;
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="0-based indices. end_index is inclusive unless it is -1 (meaning through end of string). start_index must be ≥ 0. Cap long text with start 0 and a fixed end_index."
                                    />
                                    <InspectorSection title="Substring">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Target (target_string handle)</label>
                                            <textarea
                                                value={(targetIdx >= 0 ? requiredInputs[targetIdx]?.value : null) as string ?? ''}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e =>
                                                    targetIdx >= 0 && updateInput(targetIdx, { value: e.target.value || null }, false)
                                                }
                                                rows={3}
                                                placeholder="Or connect from upstream"
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-teal-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Start index (start_index handle)</label>
                                            <input
                                                type="number"
                                                min={0}
                                                step={1}
                                                value={typeof startVal === 'number' ? startVal : 0}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = parseInt(e.target.value, 10);
                                                    if (startIdx >= 0) updateInput(startIdx, { value: Number.isNaN(v) ? 0 : v }, false);
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">End index (end_index handle)</label>
                                            <input
                                                type="number"
                                                step={1}
                                                value={typeof endVal === 'number' ? endVal : -1}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = parseInt(e.target.value, 10);
                                                    if (endIdx >= 0) updateInput(endIdx, { value: Number.isNaN(v) ? -1 : v }, false);
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">-1 = through end of string; otherwise inclusive end.</p>
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {/* String Primitive nodes */}
                        {selectedNode.type === 'stringPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Text</label>
                                    <textarea
                                        value={(selectedNode.data as any).text ?? ''}
                                        onFocus={recordGraphBeforeMutation}
                                        onChange={e => patchSelectedNodeData({ text: e.target.value })}
                                        rows={5}
                                        className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-sky-500"
                                    />
                                </div>
                            </InspectorSection>
                        )}

                        {/* List Primitive nodes */}
                        {selectedNode.type === 'listPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                        <label className="text-xs font-medium text-mw-text-secondary">List Data (JSON Array)</label>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setListPrimitiveNormalizeError('');
                                                const r = normalizeText(listPrimitiveEditorJson, 'list');
                                                if (r.ok) {
                                                    updateSelectedNodeData({ data: r.value });
                                                    setListPrimitiveEditorJson(r.formatted);
                                                } else {
                                                    setListPrimitiveNormalizeError(r.error);
                                                }
                                            }}
                                            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline shrink-0"
                                        >
                                            Normalize JSON
                                        </button>
                                    </div>
                                    <textarea
                                        value={listPrimitiveEditorJson}
                                        onFocus={recordGraphBeforeMutation}
                                        onChange={e => {
                                            const v = e.target.value;
                                            setListPrimitiveEditorJson(v);
                                            try {
                                                patchSelectedNodeData({ data: JSON.parse(v) });
                                            } catch {
                                                /* ignore */
                                            }
                                        }}
                                        rows={6}
                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-pink-500"
                                    />
                                    {listPrimitiveNormalizeError ? (
                                        <p className="text-[10px] text-red-600 dark:text-red-400 mt-1">{listPrimitiveNormalizeError}</p>
                                    ) : null}
                                    <p className="text-[10px] text-mw-text-secondary mt-0.5">Order is preserved—feed into <strong className="font-medium text-mw-text-primary">For Loop</strong> or list utilities as an iterable sequence. Use <strong className="font-medium text-mw-text-primary">Normalize JSON</strong> after pasting noisy output (fences, prose, <code className="text-mw-text-primary">---</code>).</p>
                                </div>
                            </InspectorSection>
                        )}

                        {/* Dictionary Primitive nodes */}
                        {selectedNode.type === 'dictionaryPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                        <label className="text-xs font-medium text-mw-text-secondary">Dictionary Data (JSON Object)</label>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setDictPrimitiveNormalizeError('');
                                                const r = normalizeText(dictPrimitiveEditorJson, 'dictionary');
                                                if (r.ok) {
                                                    updateSelectedNodeData({ data: r.value });
                                                    setDictPrimitiveEditorJson(r.formatted);
                                                } else {
                                                    setDictPrimitiveNormalizeError(r.error);
                                                }
                                            }}
                                            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline shrink-0"
                                        >
                                            Normalize JSON
                                        </button>
                                    </div>
                                    <textarea
                                        value={dictPrimitiveEditorJson}
                                        onFocus={recordGraphBeforeMutation}
                                        onChange={e => {
                                            const v = e.target.value;
                                            setDictPrimitiveEditorJson(v);
                                            try {
                                                patchSelectedNodeData({ data: JSON.parse(v) });
                                            } catch {
                                                /* ignore */
                                            }
                                        }}
                                        rows={6}
                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card text-mw-text-primary rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-fuchsia-500"
                                    />
                                    {dictPrimitiveNormalizeError ? (
                                        <p className="text-[10px] text-red-600 dark:text-red-400 mt-1">{dictPrimitiveNormalizeError}</p>
                                    ) : null}
                                </div>
                            </InspectorSection>
                        )}

                        {/* Boolean Primitive nodes */}
                        {selectedNode.type === 'booleanPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Value</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={(selectedNode.data as any).value === true}
                                            onChange={e => updateSelectedNodeData({ value: e.target.checked })}
                                            className="w-4 h-4 rounded border-mw-border text-emerald-600 focus:ring-emerald-500"
                                        />
                                        <span className="text-xs text-mw-text-primary">True (or wire from upstream)</span>
                                    </div>
                                </div>
                            </InspectorSection>
                        )}

                        {/* Int Primitive nodes */}
                        {selectedNode.type === 'intPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Value</label>
                                    <input
                                        type="number"
                                        value={(selectedNode.data as any).value ?? 0}
                                        onFocus={recordGraphBeforeMutation}
                                        onChange={e => patchSelectedNodeData({ value: parseInt(e.target.value, 10) || 0 })}
                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
                                    />
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'dateTimePrimitive' && (
                            <InspectorSection title="Value">
                                <div className="space-y-2">
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={Boolean((selectedNode.data as any).use_now)}
                                            onChange={e => updateSelectedNodeData({ use_now: e.target.checked })}
                                            className="rounded border-mw-border"
                                        />
                                        <span className="text-xs text-mw-text-primary">Use current time when run (UTC)</span>
                                    </label>
                                    <p className="text-[10px] text-mw-text-secondary">
                                        When enabled and the node has no incoming wire, the run uses the server instant. An upstream datetime still
                                        overrides this.
                                    </p>
                                    <div className={(selectedNode.data as any).use_now ? 'opacity-50 pointer-events-none' : ''}>
                                        <SingleDateTimeField
                                            label="Instant (RFC3339)"
                                            value={(selectedNode.data as any).iso ?? null}
                                            timeZone={resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined)}
                                            onChange={v => updateSelectedNodeData({ iso: v })}
                                        />
                                    </div>
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'decisionActionPrimitive' && (
                            <InspectorSection title="Action">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Decision action</label>
                                    <select
                                        value={(selectedNode.data as any).action ?? DEFAULT_SANDBOX_DECISION_ACTION}
                                        onChange={e => updateSelectedNodeData({ action: e.target.value })}
                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                    >
                                        {SANDBOX_DECISION_ACTIONS.map(a => (
                                            <option key={a} value={a}>
                                                {a}
                                            </option>
                                        ))}
                                    </select>
                                    <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                        Output is a string for <strong>sandbox_decision_intent</strong> <code>action</code>. Optional string wire to
                                        <strong> override</strong> must still be one of these values.
                                    </p>
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'sandboxTickPrimitive' && (
                            <InspectorSection title="Sandbox tick">
                                <p className="text-xs text-mw-text-secondary">
                                    Outputs the current <strong>SandboxTickInput</strong> as a dictionary when the workflow runs in the Sandbox (server
                                    injects the tick). For editor test runs, wire <strong>Start</strong>’s <code>sandbox_tick</code> (or any tick-shaped
                                    dictionary) into <strong>override</strong>, or provide tick via run overrides.
                                </p>
                            </InspectorSection>
                        )}

                        {/* Structure Primitive nodes */}
                        {selectedNode.type === 'structurePrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Structure</label>
                                    <select
                                        value={(selectedNode.data as any).structure_id ?? ''}
                                        onChange={e => updateSelectedNodeData({ structure_id: e.target.value })}
                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                    >
                                        <option value="">Select a Structure</option>
                                        {structures.map(s => (
                                            <option key={s.id} value={s.id}>{s.name}</option>
                                        ))}
                                    </select>
                                    <p className="text-[10px] text-mw-text-secondary mt-0.5">Connect to Simple LLM Call Structure handle for structured JSON output.</p>
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'documentPrimitive' && (
                            <InspectorSection title="Value">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Document</label>
                                    <select
                                        value={(selectedNode.data as any).document_id ?? ''}
                                        onChange={e => updateSelectedNodeData({ document_id: e.target.value })}
                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                                    >
                                        <option value="">Select a Document</option>
                                        {documents.map(doc => (
                                            <option key={doc.id} value={doc.id}>{doc.name}</option>
                                        ))}
                                    </select>
                                    <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                        Create Documents under Configure → Documents. Wire <strong>output</strong> to Read Document Property (document handle) or to Stop when Required output type is <strong>Document</strong>. To persist a string as a new or updated document use the palette <strong>Save text as Document</strong> (same as Upsert with <strong>name</strong> + <strong>content</strong>).
                                    </p>
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'imagePrimitive' && (
                            <InspectorSection title="Image">
                                <div className="space-y-2">
                                    <input
                                        ref={imagePrimitiveFileInputRef}
                                        type="file"
                                        accept="image/png,image/jpeg,image/webp"
                                        className="hidden"
                                        onChange={async e => {
                                            const file = e.target.files?.[0];
                                            e.target.value = '';
                                            if (!file) return;
                                            try {
                                                const r = await ApiClient.postUrlSnapshotImageUpload(file);
                                                updateSelectedNodeData({ artifact_id: r.artifact_id });
                                            } catch (err) {
                                                console.error('Image upload failed', err);
                                            }
                                        }}
                                    />
                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            type="button"
                                            onClick={() => imagePrimitiveFileInputRef.current?.click()}
                                            className="px-2 py-1 text-xs rounded-lg border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-border/30"
                                        >
                                            Choose image
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => updateSelectedNodeData({ artifact_id: '' })}
                                            className="px-2 py-1 text-xs rounded-lg border border-mw-border text-mw-text-secondary hover:bg-mw-border/30"
                                        >
                                            Clear
                                        </button>
                                    </div>
                                    {(selectedNode.data as { artifact_id?: string }).artifact_id ? (
                                        <p className="text-[10px] font-mono text-mw-text-secondary break-all">
                                            {(selectedNode.data as { artifact_id?: string }).artifact_id}
                                        </p>
                                    ) : (
                                        <p className="text-[10px] text-mw-text-secondary">No file selected — or wire the <strong>image</strong> input from an upstream step.</p>
                                    )}
                                    <p className="text-[10px] text-mw-text-secondary">
                                        Wire <strong>image</strong> from URL snapshot to override a manual file. <strong>output</strong> carries normalized metadata for Multimodal LLM.
                                    </p>
                                </div>
                            </InspectorSection>
                        )}

                        {selectedNode.type === 'gmailPrimitive' && (
                            <InspectorSection title="Message (JSON)">
                                <div>
                                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">Static message object</label>
                                    <textarea
                                        value={(() => {
                                            const m = (selectedNode.data as any).message;
                                            try {
                                                return JSON.stringify(m && typeof m === 'object' ? m : {}, null, 2);
                                            } catch {
                                                return '{}';
                                            }
                                        })()}
                                        onChange={e => {
                                            const raw = e.target.value.trim();
                                            if (!raw) {
                                                updateSelectedNodeData({ message: {} });
                                                return;
                                            }
                                            try {
                                                const parsed = JSON.parse(raw);
                                                updateSelectedNodeData({
                                                    message: parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {},
                                                });
                                            } catch {
                                                /* keep previous until valid JSON */
                                            }
                                        }}
                                        rows={10}
                                        spellCheck={false}
                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
                                    />
                                    <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                        Curated Gmail fields (e.g. <code className="text-[10px]">id</code>, <code className="text-[10px]">subject</code>,{' '}
                                        <code className="text-[10px]">body_text</code>). Wire the <strong>gmail</strong> input to override with an upstream message, or use Stop / Start with type <strong>Gmail</strong>.
                                    </p>
                                </div>
                            </InspectorSection>
                        )}

                        {/* Start nodes — Required Inputs */}
                        {selectedNode.type === 'start' && (() => {
                            const rawInputs = (selectedNode.data as any).required_inputs;
                            const inputs: RequiredInput[] = rawInputs === undefined
                                ? [{ key: 'user_input', type: 'string', value: (selectedNode.data as any).text ?? null }]
                                : (rawInputs ?? []);
                            const updateInput = (idx: number, patch: Partial<RequiredInput>, withHistory = true) => {
                                const next = [...inputs];
                                next[idx] = { ...next[idx], ...patch };
                                if (withHistory) updateSelectedNodeData({ required_inputs: next });
                                else patchSelectedNodeData({ required_inputs: next });
                            };
                            const addInput = () => {
                                const key = nextUniqueStartSlotKey(inputs);
                                updateSelectedNodeData({ required_inputs: [...inputs, { key, type: 'string', value: null }] });
                            };
                            const removeInput = (idx: number) => {
                                const next = inputs.filter((_, i) => i !== idx);
                                setStartSlotKeyError({});
                                updateSelectedNodeData({ required_inputs: next });
                            };
                            return (
                                <InspectorSection title="Workflow inputs">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-medium text-mw-text-secondary">Slots</span>
                                        <button type="button" onClick={addInput} className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">+ Add</button>
                                    </div>
                                    {inputs.map((inp, idx) => (
                                        <div key={`input-${idx}`} className="border border-mw-border rounded-lg p-2 space-y-2">
                                            <div className="flex gap-2 items-center flex-wrap">
                                                <input
                                                    value={inp.key}
                                                    aria-invalid={Boolean(startSlotKeyError[idx])}
                                                    onFocus={recordGraphBeforeMutation}
                                                    onChange={e => {
                                                        const trimmed = e.target.value.trim();
                                                        const err = validateStartSlotKey(trimmed, inputs, idx);
                                                        if (err) {
                                                            setStartSlotKeyError(prev => ({ ...prev, [idx]: err }));
                                                            return;
                                                        }
                                                        setStartSlotKeyError(prev => {
                                                            const nextErr = { ...prev };
                                                            delete nextErr[idx];
                                                            return nextErr;
                                                        });
                                                        updateInput(idx, { key: trimmed }, false);
                                                    }}
                                                    placeholder="Key (e.g. user_input)"
                                                    className={`flex-1 min-w-0 px-2 py-1 text-xs border bg-mw-card rounded ${
                                                        startSlotKeyError[idx] ? 'border-red-500 dark:border-red-400' : 'border-mw-border'
                                                    }`}
                                                />
                                                <span className="text-[10px] text-mw-text-secondary shrink-0">(output handle)</span>
                                                <select
                                                    value={inp.type}
                                                    onChange={e =>
                                                        updateInput(idx, {
                                                            type: e.target.value as RequiredInput['type'],
                                                            value: null,
                                                        })
                                                    }
                                                    className="px-2 py-1 text-xs border border-mw-border bg-mw-card rounded"
                                                >
                                                    <option value="string">String</option>
                                                    <option value="list">List</option>
                                                    <option value="dictionary">Dictionary</option>
                                                    <option value="structure">Structure</option>
                                                    <option value="document">Document</option>
                                                    <option value="gmail">Gmail</option>
                                                    <option value="boolean">Boolean</option>
                                                    <option value="int">Int</option>
                                                    <option value="datetime">DateTime</option>
                                                    <option value="any">Any</option>
                                                </select>
                                                <button type="button" onClick={() => removeInput(idx)} className="text-red-500 hover:text-red-600 text-xs px-1">×</button>
                                            </div>
                                            {startSlotKeyError[idx] ? (
                                                <p className="text-[10px] text-red-600 dark:text-red-400" role="alert">
                                                    {startSlotKeyError[idx]}
                                                </p>
                                            ) : null}
                                            {inp.type === 'string' && (
                                                <textarea
                                                    value={typeof inp.value === 'string' ? inp.value : ''}
                                                    onFocus={recordGraphBeforeMutation}
                                                    onChange={e => updateInput(idx, { value: e.target.value || null }, false)}
                                                    rows={3}
                                                    placeholder="Leave empty to prompt at run time"
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded resize-none"
                                                />
                                            )}
                                            {inp.type === 'list' && (
                                                <div className="space-y-1">
                                                    <div className="flex justify-end">
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setStartListDictNormalizeError(prev => ({ ...prev, [idx]: '' }));
                                                                const raw = startListDictEditorJson[idx] ?? '';
                                                                const r = normalizeText(raw, 'list');
                                                                if (r.ok) {
                                                                    updateInput(idx, { value: r.value });
                                                                    setStartListDictEditorJson(prev => ({
                                                                        ...prev,
                                                                        [idx]: r.formatted,
                                                                    }));
                                                                } else {
                                                                    setStartListDictNormalizeError(prev => ({
                                                                        ...prev,
                                                                        [idx]: r.error,
                                                                    }));
                                                                }
                                                            }}
                                                            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                                                        >
                                                            Normalize JSON
                                                        </button>
                                                    </div>
                                                    <textarea
                                                        value={
                                                            Object.prototype.hasOwnProperty.call(startListDictEditorJson, idx)
                                                                ? startListDictEditorJson[idx]
                                                                : inp.value == null
                                                                  ? ''
                                                                  : Array.isArray(inp.value)
                                                                    ? JSON.stringify(inp.value, null, 2)
                                                                    : ''
                                                        }
                                                        onFocus={recordGraphBeforeMutation}
                                                        onChange={e => {
                                                            const v = e.target.value;
                                                            setStartListDictEditorJson(prev => ({ ...prev, [idx]: v }));
                                                            const t = v.trim();
                                                            if (t === '') {
                                                                updateInput(idx, { value: null }, false);
                                                                return;
                                                            }
                                                            try {
                                                                const parsed = JSON.parse(v);
                                                                if (Array.isArray(parsed)) updateInput(idx, { value: parsed }, false);
                                                            } catch {
                                                                /* ignore */
                                                            }
                                                        }}
                                                        rows={3}
                                                        placeholder="Leave empty to prompt at run time. Type e.g. [] for an explicit empty list."
                                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card rounded resize-none"
                                                    />
                                                    {startListDictNormalizeError[idx] ? (
                                                        <p className="text-[10px] text-red-600 dark:text-red-400">
                                                            {startListDictNormalizeError[idx]}
                                                        </p>
                                                    ) : null}
                                                </div>
                                            )}
                                            {(inp.type === 'dictionary' || inp.type === 'gmail') && (
                                                <div className="space-y-1">
                                                    <div className="flex justify-end">
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setStartListDictNormalizeError(prev => ({ ...prev, [idx]: '' }));
                                                                const raw = startListDictEditorJson[idx] ?? '';
                                                                const r = normalizeText(raw, 'dictionary');
                                                                if (r.ok) {
                                                                    updateInput(idx, { value: r.value });
                                                                    setStartListDictEditorJson(prev => ({
                                                                        ...prev,
                                                                        [idx]: r.formatted,
                                                                    }));
                                                                } else {
                                                                    setStartListDictNormalizeError(prev => ({
                                                                        ...prev,
                                                                        [idx]: r.error,
                                                                    }));
                                                                }
                                                            }}
                                                            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                                                        >
                                                            Normalize JSON
                                                        </button>
                                                    </div>
                                                    <textarea
                                                        value={
                                                            Object.prototype.hasOwnProperty.call(startListDictEditorJson, idx)
                                                                ? startListDictEditorJson[idx]
                                                                : inp.value == null
                                                                  ? ''
                                                                  : typeof inp.value === 'object' &&
                                                                      !Array.isArray(inp.value)
                                                                    ? JSON.stringify(inp.value, null, 2)
                                                                    : ''
                                                        }
                                                        onFocus={recordGraphBeforeMutation}
                                                        onChange={e => {
                                                            const v = e.target.value;
                                                            setStartListDictEditorJson(prev => ({ ...prev, [idx]: v }));
                                                            const t = v.trim();
                                                            if (t === '') {
                                                                updateInput(idx, { value: null }, false);
                                                                return;
                                                            }
                                                            try {
                                                                const parsed = JSON.parse(v);
                                                                if (
                                                                    typeof parsed === 'object' &&
                                                                    parsed !== null &&
                                                                    !Array.isArray(parsed)
                                                                ) {
                                                                    updateInput(idx, { value: parsed }, false);
                                                                }
                                                            } catch {
                                                                /* ignore */
                                                            }
                                                        }}
                                                        rows={3}
                                                        placeholder="Leave empty to prompt at run time. Type e.g. {} for an explicit empty object."
                                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card rounded resize-none"
                                                    />
                                                    {startListDictNormalizeError[idx] ? (
                                                        <p className="text-[10px] text-red-600 dark:text-red-400">
                                                            {startListDictNormalizeError[idx]}
                                                        </p>
                                                    ) : null}
                                                </div>
                                            )}
                                            {inp.type === 'boolean' && (
                                                <select
                                                    value={
                                                        inp.value === true
                                                            ? 'true'
                                                            : inp.value === false
                                                              ? 'false'
                                                              : ''
                                                    }
                                                    onChange={e => {
                                                        const v = e.target.value;
                                                        if (v === '') updateInput(idx, { value: null });
                                                        else updateInput(idx, { value: v === 'true' });
                                                    }}
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded"
                                                >
                                                    <option value="">At run time…</option>
                                                    <option value="true">True</option>
                                                    <option value="false">False</option>
                                                </select>
                                            )}
                                            {inp.type === 'int' && (
                                                <input
                                                    type="number"
                                                    value={typeof inp.value === 'number' ? inp.value : ''}
                                                    onFocus={recordGraphBeforeMutation}
                                                    onChange={e =>
                                                        updateInput(
                                                            idx,
                                                            { value: e.target.value === '' ? null : parseInt(e.target.value, 10) },
                                                            false,
                                                        )
                                                    }
                                                    placeholder="Leave empty to prompt at run"
                                                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded"
                                                />
                                            )}
                                            {inp.type === 'datetime' && (
                                                <SingleDateTimeField
                                                    label="Value (optional)"
                                                    value={typeof inp.value === 'string' ? inp.value : null}
                                                    timeZone={resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined)}
                                                    onChange={v => updateInput(idx, { value: v })}
                                                />
                                            )}
                                            {(inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure') && (
                                                <div className="space-y-1">
                                                    <div className="flex justify-end">
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setStartListDictNormalizeError(prev => ({ ...prev, [idx]: '' }));
                                                                const raw = startListDictEditorJson[idx] ?? '';
                                                                try {
                                                                    const pre = stripCommonJsonWrappers(raw);
                                                                    const parsed = JSON.parse(pre) as RequiredInput['value'];
                                                                    updateInput(idx, { value: parsed });
                                                                    setStartListDictEditorJson(prev => ({
                                                                        ...prev,
                                                                        [idx]: JSON.stringify(parsed, null, 2),
                                                                    }));
                                                                } catch (e) {
                                                                    setStartListDictNormalizeError(prev => ({
                                                                        ...prev,
                                                                        [idx]: e instanceof Error ? e.message : 'Invalid JSON',
                                                                    }));
                                                                }
                                                            }}
                                                            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                                                        >
                                                            Normalize JSON
                                                        </button>
                                                    </div>
                                                    <textarea
                                                        value={
                                                            Object.prototype.hasOwnProperty.call(startListDictEditorJson, idx)
                                                                ? startListDictEditorJson[idx]
                                                                : inp.value == null
                                                                  ? ''
                                                                  : JSON.stringify(inp.value, null, 2)
                                                        }
                                                        onFocus={recordGraphBeforeMutation}
                                                        onChange={e => {
                                                            const v = e.target.value;
                                                            setStartListDictEditorJson(prev => ({ ...prev, [idx]: v }));
                                                            const t = v.trim();
                                                            if (t === '') {
                                                                updateInput(idx, { value: null }, false);
                                                                return;
                                                            }
                                                            try {
                                                                updateInput(
                                                                    idx,
                                                                    { value: JSON.parse(v) as RequiredInput['value'] },
                                                                    false,
                                                                );
                                                            } catch {
                                                                /* ignore incomplete JSON */
                                                            }
                                                        }}
                                                        rows={3}
                                                        placeholder={
                                                            inp.type === 'document'
                                                                ? 'JSON shape for a document output, or leave empty to prompt at run time.'
                                                                : inp.type === 'structure'
                                                                  ? 'JSON schema object, or leave empty to prompt at run time.'
                                                                  : 'Any JSON value. Leave empty to prompt at run time.'
                                                        }
                                                        className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card rounded resize-none"
                                                    />
                                                    {startListDictNormalizeError[idx] ? (
                                                        <p className="text-[10px] text-red-600 dark:text-red-400">
                                                            {startListDictNormalizeError[idx]}
                                                        </p>
                                                    ) : null}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </InspectorSection>
                            );
                        })()}

                        {/* Stop nodes — Required Output (exactly one) */}
                        {selectedNode.type === 'stop' && (() => {
                            const rawOutputs = (selectedNode.data as any).required_outputs;
                            const outputs: RequiredOutput[] = Array.isArray(rawOutputs) && rawOutputs.length > 0
                                ? rawOutputs
                                : [{ key: 'output', type: 'string' }];
                            const out = outputs[0] ?? { key: 'output', type: 'string' as const };
                            const patchOutput = (patch: Partial<RequiredOutput>) => {
                                patchSelectedNodeData({ required_outputs: [{ ...out, ...patch }] });
                            };
                            const updateOutput = (patch: Partial<RequiredOutput>) => {
                                recordGraphBeforeMutation();
                                patchOutput(patch);
                            };
                            return (
                                <>
                                    <InspectorSection
                                        title="About"
                                        description="The Stop node gathers the final output from upstream. Define the expected output type for this workflow."
                                    />
                                    <InspectorSection title="Multi-Stop / sandbox">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">stop_priority</label>
                                            <input
                                                type="number"
                                                value={Number((selectedNode.data as any).stop_priority ?? 0)}
                                                onFocus={recordGraphBeforeMutation}
                                                onChange={e => {
                                                    const v = parseInt(e.target.value, 10);
                                                    patchSelectedNodeData({
                                                        stop_priority: Number.isFinite(v) ? v : 0,
                                                    });
                                                }}
                                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                            />
                                            <p className="text-[10px] text-mw-text-secondary mt-1">
                                                When several Stop nodes succeed, the sandbox uses the highest priority; ties use run step order, then node id.
                                            </p>
                                        </div>
                                    </InspectorSection>
                                    <InspectorSection title="Output">
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Required output</label>
                                            <div className="border border-mw-border rounded-lg p-2 flex gap-2 items-center flex-wrap">
                                                <input
                                                    value={out.key}
                                                    onFocus={recordGraphBeforeMutation}
                                                    onChange={e => patchOutput({ key: e.target.value })}
                                                    placeholder="Key (e.g. output)"
                                                    className="flex-1 min-w-0 px-2 py-1 text-xs border border-mw-border bg-mw-card rounded"
                                                />
                                                <span className="text-[10px] text-mw-text-secondary shrink-0">(handle)</span>
                                                <select value={out.type} onChange={e => updateOutput({ type: e.target.value as RequiredOutput['type'] })}
                                                    className="px-2 py-1 text-xs border border-mw-border bg-mw-card rounded">
                                                    <option value="string">String</option>
                                                    <option value="list">List</option>
                                                    <option value="dictionary">Dictionary</option>
                                                    <option value="structure">Structure</option>
                                                    <option value="document">Document</option>
                                                    <option value="gmail">Gmail</option>
                                                    <option value="audio">Audio</option>
                                                    <option value="boolean">Boolean</option>
                                                    <option value="int">Int</option>
                                                    <option value="datetime">DateTime</option>
                                                    <option value="any">Any</option>
                                                </select>
                                            </div>
                                            <p className="text-[10px] text-mw-text-secondary mt-1.5">
                                                Wire from the upstream step’s <strong>data</strong> output (often labeled{' '}
                                                <code className="text-[10px] bg-mw-card-alt px-0.5 rounded">output</code>), not the{' '}
                                                <strong>▶</strong> signal output, to the left handle that matches the key above.
                                            </p>
                                            {out.type === 'list' ? (
                                                <p className="text-[10px] text-mw-text-secondary mt-1.5">
                                                    Gmail List returns a <code className="text-[10px] bg-mw-card-alt px-0.5 rounded">messages</code> envelope;
                                                    the run unwraps it to a plain list when Stop expects List (including when multiple wires reach Stop).
                                                </p>
                                            ) : null}
                                        </div>
                                    </InspectorSection>
                                </>
                            );
                        })()}

                        {/* Workflow nodes */}
                        {selectedNode.type === 'workflowRef' &&
                            (() => {
                                const wfId = (selectedNode.data as any).workflow_id;
                                const refWf = workflows.find(w => w.id === wfId);
                                const isCustomSkill = Boolean(refWf?.expose_as_custom_skill);
                                const stepKindLabel = isCustomSkill ? 'Custom Skill' : 'Workflow';
                                return (
                                    <InspectorSection title={isCustomSkill ? 'Custom Skill' : 'Nested workflow'}>
                                        <div>
                                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">{stepKindLabel}</label>
                                            <div className="text-sm text-mw-text-primary bg-mw-card-alt rounded-lg px-2 py-1.5">
                                                {(selectedNode.data as any).label ?? 'Workflow'}
                                            </div>
                                            {refWf ? (
                                                <button
                                                    type="button"
                                                    onClick={() => openWorkflow(refWf)}
                                                    className="mt-1.5 text-xs text-teal-600 dark:text-teal-400 hover:underline"
                                                >
                                                    Open workflow
                                                </button>
                                            ) : null}
                                            <p className="text-[10px] text-mw-text-secondary mt-0.5">
                                                Wire each data input to the matching target handle on the left (keys match the
                                                referenced workflow’s Start slots). Outputs use the right handles (keys match that
                                                workflow’s Stop required outputs).
                                            </p>
                                        </div>
                                    </InspectorSection>
                                );
                            })()}

                        {/* ── Last Run section ─────────────────────────────── */}
                        {showInspectorLastRunExplorerSection(selectedNode.type) && (() => {
                            const nodeLog = lastRunNodeData[selectedNode.id];
                            const isActiveNode = runningNodeIds.has(selectedNode.id);
                            const inputsPayloadEditor = nodeLog
                                ? lastRunInputsPayload(nodeLog.details as Record<string, unknown> | undefined)
                                : null;
                            const showInputsFirstEditor =
                                !!inputsPayloadEditor &&
                                !!nodeLog &&
                                (nodeLog.status !== 'ok' || (nodeLog.error != null && nodeLog.error !== ''));
                            const inputsPanelEditor = inputsPayloadEditor ? (
                                <div className="mt-2">
                                    <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1">
                                        Inputs
                                    </div>
                                    <RunInputsExplorer payload={inputsPayloadEditor} />
                                </div>
                            ) : null;
                            return (
                                <div className={`${INSPECTOR_SURFACE_CLASS} mt-1`}>
                                    <div className="flex items-center justify-between mb-2 -mt-0.5">
                                        <button
                                            onClick={() => setIsLastRunOpen(p => !p)}
                                            className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                                        >
                                            {isLastRunOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                                            Last Run
                                            {isActiveNode && <span className="ml-1 w-1.5 h-1.5 rounded-full bg-mw-primary animate-ping inline-block" />}
                                        </button>
                                        {Object.keys(lastRunNodeData).length > 0 && (
                                            <button
                                                onClick={() => { setLastRunNodeData({}); setLastRunId(null); setIsLastRunOpen(false); }}
                                                className="text-[10px] text-mw-text-secondary hover:text-red-500 transition-colors px-1.5 py-0.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                                            >
                                                Clear
                                            </button>
                                        )}
                                    </div>
                                    {isLastRunOpen && (
                                        <div className="space-y-2">
                                            {selectedNode && !loopBodyNodeIds.has(selectedNode.id) && (
                                                <div className="flex flex-wrap gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => setOutputOverrideModalOpen(true)}
                                                        className="text-[10px] font-medium px-2 py-1 rounded border border-mw-border text-mw-text-primary hover:bg-mw-card-alt"
                                                    >
                                                        Override output
                                                    </button>
                                                    {outputOverrides[selectedNode.id] !== undefined && (
                                                        <button
                                                            type="button"
                                                            onClick={() =>
                                                                setOutputOverrides(prev => {
                                                                    const n = { ...prev };
                                                                    delete n[selectedNode.id];
                                                                    return n;
                                                                })
                                                            }
                                                            className="text-[10px] font-medium px-2 py-1 rounded border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
                                                        >
                                                            Clear override
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                            {selectedNode && loopBodyNodeIds.has(selectedNode.id) && (
                                                <p className="text-[10px] text-mw-text-secondary">
                                                    Output overrides are not available for steps inside a For Loop body or a Try /
                                                    Catch branch interior.
                                                </p>
                                            )}
                                            {!nodeLog && !isActiveNode && (
                                                <p className="text-xs text-mw-text-secondary italic">
                                                    No recorded execution for this step yet. Any session output override
                                                    above is applied when you Run.
                                                </p>
                                            )}
                                            {isActiveNode && (
                                                <div className="flex items-center gap-2 text-xs text-mw-primary">
                                                    <Loader2 size={12} className="animate-spin" /> Running…
                                                </div>
                                            )}
                                            {nodeLog && (
                                                <div className="space-y-1.5">
                                                    <div className="flex items-center gap-1.5">
                                                        {nodeLog.status === 'ok'
                                                            ? <CheckCircle2 size={12} className="text-emerald-500" />
                                                            : <XCircle size={12} className="text-red-500" />}
                                                        <span className={`text-xs font-medium ${nodeLog.status === 'ok' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                                                            {nodeLog.status === 'ok' ? 'Completed' : 'Failed'}
                                                            {nodeLog.latency_ms != null && ` · ${nodeLog.latency_ms.toFixed(0)}ms`}
                                                        </span>
                                                        {nodeLog.details?.forced_output ? (
                                                            <span className="text-[10px] font-semibold uppercase text-amber-700 dark:text-amber-300 ml-1">
                                                                Overridden
                                                            </span>
                                                        ) : null}
                                                    </div>
                                                    {nodeLog.error && (
                                                        <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded p-2 font-mono break-all">
                                                            {nodeLog.error}
                                                        </div>
                                                    )}
                                                    {showInputsFirstEditor && inputsPanelEditor}
                                                    {nodeLog.details?.sub_workflow_node_results && (
                                                        <div className="mt-2">
                                                            <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1.5">Sub-workflow: {nodeLog.details.sub_workflow_name ?? 'Sub-workflow'}</div>
                                                            <div className="space-y-1.5">
                                                                {(nodeLog.details.sub_workflow_node_results as any[]).map((sr: any) => {
                                                                    const stepLabel = (nodeLog.details?.sub_workflow_node_labels as Record<string, string>)?.[sr.node_id] ?? sr.node_id;
                                                                    return (
                                                                        <div key={sr.node_id} className="flex items-start gap-2 text-xs bg-mw-card-alt rounded p-2 border border-mw-border">
                                                                            {sr.status === 'ok' ? <CheckCircle2 size={12} className="text-emerald-500 shrink-0 mt-0.5" /> : <XCircle size={12} className="text-red-500 shrink-0 mt-0.5" />}
                                                                            <div className="flex-1 min-w-0">
                                                                                <span className="font-medium text-mw-text-primary">{stepLabel}</span>
                                                                                {sr.latency_ms != null && <span className="text-mw-text-secondary ml-1">{sr.latency_ms.toFixed(0)}ms</span>}
                                                                                {sr.error && <div className="text-red-600 dark:text-red-400 mt-1 text-[11px] whitespace-pre-wrap break-all">{sr.error}</div>}
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        </div>
                                                    )}
                                                    {nodeLog.output && (
                                                        <div>
                                                            <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1">
                                                                Output
                                                            </div>
                                                            <WorkflowNodeRunOutputBody
                                                                nodeId={nodeLog.node_id}
                                                                output={nodeLog.output}
                                                                details={nodeLog.details as Record<string, unknown> | undefined}
                                                                userSettings={user?.settings as Record<string, unknown> | undefined}
                                                                markdownRows={12}
                                                            />
                                                        </div>
                                                    )}
                                                    {!showInputsFirstEditor && inputsPanelEditor}
                                                    {(nodeLog.details as any)?.skill_diagnostics != null && (
                                                        <details className="mt-2 group/diag">
                                                            <summary className="cursor-pointer text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary select-none list-none flex items-center gap-1">
                                                                <ChevronRight size={12} className="group-open/diag:rotate-90 transition-transform shrink-0" />
                                                                Skill diagnostics (vendor response)
                                                            </summary>
                                                            <div className="mt-1.5">
                                                                <JsonTreeView data={(nodeLog.details as any).skill_diagnostics} defaultExpandedDepth={2} />
                                                            </div>
                                                        </details>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                                    {selectedNode.type !== 'start' && (selectedNode.type !== 'stop' || stopNodeCount > 1) && (
                                        <div
                                            ref={
                                                pendingNodeDelete &&
                                                pendingNodeDelete.ids.length === 1 &&
                                                pendingNodeDelete.ids[0] === selectedNode.id
                                                    ? nodeDeleteConfirmRef
                                                    : undefined
                                            }
                                            className="mt-1 rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 px-3 py-3 scroll-mt-4"
                                        >
                                            {pendingNodeDelete &&
                                            pendingNodeDelete.ids.length === 1 &&
                                            pendingNodeDelete.ids[0] === selectedNode.id ? (
                                                <div className="space-y-2">
                                                    <div className="text-xs font-medium text-red-600 dark:text-red-400">
                                                        Delete this node?
                                                    </div>
                                                    <div className="text-xs rounded-lg border border-mw-border bg-mw-card px-2 py-1.5 font-mono text-mw-text-primary break-all">
                                                        <span className="font-sans text-mw-text-secondary">
                                                            {String((selectedNode.data as { label?: string })?.label ?? '').trim() || '—'}
                                                        </span>
                                                        {' · '}
                                                        {selectedNode.type ?? 'node'}
                                                        {' · '}
                                                        {selectedNode.id}
                                                    </div>
                                                    {pendingNodeDelete.skippedStart ? (
                                                        <p className="text-xs text-mw-text-secondary">
                                                            The Start node cannot be removed and will remain on the canvas.
                                                        </p>
                                                    ) : null}
                                                    <div className="flex gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={handleConfirmPendingNodeDelete}
                                                            className="flex-1 py-1.5 text-xs font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                                                        >
                                                            Delete
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => setPendingNodeDelete(null)}
                                                            className="flex-1 py-1.5 text-xs font-medium bg-mw-card-alt hover:opacity-90 text-mw-text-primary rounded-lg transition-colors"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="flex justify-center">
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            const plan = planCanvasNodeDeletion([selectedNode], nodes);
                                                            if (plan.ok) {
                                                                setPendingNodeDelete({
                                                                    ids: plan.ids,
                                                                    skippedStart: plan.skippedStart,
                                                                });
                                                            }
                                                        }}
                                                        className="inline-flex items-center justify-center gap-2 py-2 px-3 text-xs font-medium text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                                    >
                                                        <Trash2 size={14} /> Remove Node
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ) : selectedEdge ? (
                                <EdgeInspectorPanel
                                    edge={selectedEdge}
                                    nodes={nodes}
                                    edges={edges}
                                    lastRunNodeData={lastRunNodeData}
                                    runResult={runResult}
                                    deletingEdgeId={deletingEdgeId}
                                    onRequestDelete={() => setDeletingEdgeId(selectedEdge.id)}
                                    onCancelDelete={() => setDeletingEdgeId(null)}
                                    onConfirmDelete={handleDeleteEdge}
                                />
                            ) : activeWf ? (
                                <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
                                    <WorkflowExplorerWorkflowMetadata
                                        workflow={activeWf}
                                        nodeCount={nodes.length}
                                        edgeCount={edges.length}
                                        lastRunId={lastRunId}
                                        onExposeAsCustomSkillChange={handleExposeCustomSkillChange}
                                        executionLimitsEnvelope={workflowExecutionEnvelope}
                                        graphExecutionLimitsDraft={activeWf.graph.execution_limits ?? undefined}
                                        runExecutionLimitsDraft={runExecutionLimitsOverrides}
                                        onGraphExecutionLimitsChange={patchGraphExecutionLimits}
                                        onRunExecutionLimitsChange={setRunExecutionLimitsOverrides}
                                    />
                                </div>
                            ) : (
                                <div className="p-6 text-center text-sm text-mw-text-secondary">Select a node or connection on the canvas to configure it.</div>
                            )
                        ) : (
                            /* RUN LOGS TAB */
                            <div className="p-4 space-y-4">
                                {!runResult && !isRunning && (
                                    <div className="text-center text-sm text-mw-text-secondary mt-4">Run the workflow to see execution logs here.</div>
                                )}
                                {isRunning && (
                                    <div className="flex items-center justify-center gap-2 text-sm text-mw-primary my-4">
                                        <Loader2 size={16} className="animate-spin" /> Running Workflow...
                                    </div>
                                )}
                                {runResult && (
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between bg-mw-card-alt px-3 py-2 rounded-lg border border-mw-border">
                                            <span className="text-xs font-semibold text-mw-text-primary">Overall Status</span>
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${runResult.status === 'ok' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : runResult.status === 'partial' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400' : runResult.status === 'running' ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-800 dark:text-sky-300' : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'}`}>
                                                {runResult.status.toUpperCase()}
                                            </span>
                                        </div>

                                        {runResult.error ? (
                                            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-900/10 dark:text-red-300 whitespace-pre-wrap">
                                                {runResult.error}
                                            </div>
                                        ) : null}

                                        <WorkflowRunLogsNodeResultsList
                                            node_results={runResult.node_results}
                                            getNodeLabel={nodeId => {
                                                const node = nodes.find(n => n.id === nodeId);
                                                return (node?.data as { label?: string } | undefined)?.label ?? nodeId;
                                            }}
                                            userSettings={user?.settings as Record<string, unknown> | undefined}
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    </div>
                </div>
            )}

            {/* ==== Required Inputs wizard (before run, one slot per step) ==== */}
            {runInputWizard && (() => {
                const w = runInputWizard;
                const inp = w.queue[w.index];
                const total = w.queue.length;
                const stepNum = w.index + 1;
                const isLast = w.index >= total - 1;
                const canSubmit =
                    inp.type === 'list' || inp.type === 'dictionary'
                        ? (() => {
                              const parsed = parseRunWizardListOrDictJson(inp.type, runWizardListDictRaw);
                              return parsed != null && isValidRunWizardDraft(inp.type, parsed);
                          })()
                        : inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure'
                          ? (() => {
                                const parsed = parseRunWizardAnyJson(runWizardListDictRaw);
                                return parsed !== undefined && isValidRunWizardDraft(inp.type, parsed);
                            })()
                          : isValidRunWizardDraft(inp.type, runWizardStepDraft);
                return (
                    <div className="absolute inset-0 z-20 flex items-center justify-center">
                        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={clearRunInputWizard} />
                        <div className="relative w-full max-w-md mx-4 bg-mw-card rounded-xl border border-mw-border shadow-2xl p-5">
                            <h3 className="text-base font-bold text-mw-text-primary mb-1">Provide required inputs</h3>
                            <p className="text-xs text-mw-text-secondary mb-4">
                                Step {stepNum} of {total} — <span className="font-medium text-mw-text-primary">{inp.key}</span>
                                <span className="text-mw-text-secondary"> ({inp.type})</span>
                            </p>
                            <div className="mb-5" key={`${w.index}-${inp.key}`}>
                                {inp.type === 'string' && (
                                    <textarea
                                        value={typeof runWizardStepDraft === 'string' ? runWizardStepDraft : ''}
                                        onChange={e => setRunWizardStepDraft(e.target.value)}
                                        rows={4}
                                        placeholder="Required for this run"
                                        className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                    />
                                )}
                                {(inp.type === 'list' ||
                                    inp.type === 'dictionary' ||
                                    inp.type === 'any' ||
                                    inp.type === 'document' ||
                                    inp.type === 'structure') && (
                                    <div className="space-y-1">
                                        <div className="flex justify-end">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setRunWizardJsonNormalizeError('');
                                                    if (inp.type === 'any' || inp.type === 'document' || inp.type === 'gmail' || inp.type === 'structure') {
                                                        try {
                                                            const pre = stripCommonJsonWrappers(runWizardListDictRaw);
                                                            const parsed = JSON.parse(pre) as unknown;
                                                            setRunWizardListDictRaw(JSON.stringify(parsed, null, 2));
                                                        } catch (e) {
                                                            setRunWizardJsonNormalizeError(
                                                                e instanceof Error ? e.message : 'Invalid JSON',
                                                            );
                                                        }
                                                    } else {
                                                        const r =
                                                            inp.type === 'list' ?
                                                                normalizeText(runWizardListDictRaw, 'list')
                                                            :   normalizeText(runWizardListDictRaw, 'dictionary');
                                                        if (r.ok) {
                                                            setRunWizardListDictRaw(r.formatted);
                                                        } else {
                                                            setRunWizardJsonNormalizeError(r.error);
                                                        }
                                                    }
                                                }}
                                                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                                            >
                                                Normalize JSON
                                            </button>
                                        </div>
                                        <textarea
                                            value={runWizardListDictRaw}
                                            onChange={e => setRunWizardListDictRaw(e.target.value)}
                                            rows={4}
                                            placeholder={
                                                inp.type === 'any' ?
                                                    'Any JSON value (string, number, boolean, null, array, object).'
                                                :   'JSON array or object. Type freely; Continue/Run when valid. Use [] or {} for empty.'
                                            }
                                            className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                        />
                                        {runWizardJsonNormalizeError ? (
                                            <p className="text-[10px] text-red-600 dark:text-red-400">
                                                {runWizardJsonNormalizeError}
                                            </p>
                                        ) : null}
                                    </div>
                                )}
                                {inp.type === 'boolean' && (
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="run-wizard-bool"
                                            checked={runWizardStepDraft === true}
                                            onChange={e => setRunWizardStepDraft(e.target.checked)}
                                            className="w-4 h-4 rounded border-mw-border text-emerald-600"
                                        />
                                        <label htmlFor="run-wizard-bool" className="text-xs text-mw-text-primary">
                                            True (leave unchecked for false)
                                        </label>
                                    </div>
                                )}
                                {inp.type === 'int' && (
                                    <input
                                        type="number"
                                        value={
                                            typeof runWizardStepDraft === 'number' && !Number.isNaN(runWizardStepDraft)
                                                ? runWizardStepDraft
                                                : ''
                                        }
                                        onChange={e => {
                                            const v = e.target.value;
                                            setRunWizardStepDraft(v === '' ? null : parseInt(v, 10));
                                        }}
                                        placeholder="Integer"
                                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                                    />
                                )}
                                {inp.type === 'datetime' && (
                                    <SingleDateTimeField
                                        label={inp.key}
                                        value={typeof runWizardStepDraft === 'string' ? runWizardStepDraft : null}
                                        timeZone={resolveWorkflowTimeZone(
                                            user?.settings as Record<string, unknown> | undefined,
                                        )}
                                        onChange={v => setRunWizardStepDraft(v)}
                                    />
                                )}
                            </div>
                            <div className="flex flex-wrap gap-2 justify-end">
                                <button
                                    type="button"
                                    onClick={clearRunInputWizard}
                                    className="px-3 py-1.5 text-xs font-medium text-mw-text-primary bg-mw-card-alt rounded-lg"
                                >
                                    Cancel
                                </button>
                                {w.index > 0 && (
                                    <button
                                        type="button"
                                        onClick={handleRunWizardBack}
                                        className="px-3 py-1.5 text-xs font-medium text-mw-text-primary bg-mw-card-alt rounded-lg"
                                    >
                                        Back
                                    </button>
                                )}
                                <button
                                    type="button"
                                    disabled={!canSubmit}
                                    onClick={handleRunWizardPrimary}
                                    className="px-3 py-1.5 text-xs font-medium text-white bg-mw-success hover:opacity-90 disabled:opacity-50 rounded-lg"
                                >
                                    {isLast ? 'Run' : 'Continue'}
                                </button>
                            </div>
                        </div>
                    </div>
                );
            })()}

            {selectedNode && (
                <OutputOverrideModal
                    isOpen={outputOverrideModalOpen}
                    onClose={() => setOutputOverrideModalOpen(false)}
                    nodeLabel={String((selectedNode.data as { label?: string }).label ?? selectedNode.id)}
                    initialValue={outputOverrides[selectedNode.id]}
                    onSave={value => {
                        setOutputOverrides(prev => ({ ...prev, [selectedNode.id]: value }));
                    }}
                />
            )}

            <WorkflowImportModal
                isOpen={workflowImportModalOpen}
                onClose={() => setWorkflowImportModalOpen(false)}
                onImport={handleImportWorkflow}
                onImportBundle={handleImportWorkflowBundle}
            />
        </div>
    );
};
