/**
 * Read-only workflow canvas + inspector for exploring a persisted run (Explore modal).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    applyNodeChanges,
    Background,
    Controls,
    ReactFlow,
    ConnectionMode,
    type Node,
    type Edge,
    type NodeChange,
} from '@xyflow/react';
import {
    FitViewOnWorkflowCanvasKey,
    FitViewOnWorkflowCanvasResize,
    WORKFLOW_CANVAS_MIN_ZOOM,
} from './FitViewOnWorkflowCanvas';
import { useCompactViewport } from '../../hooks/useCompactViewport';
import { PanelRight } from 'lucide-react';
import '@xyflow/react/dist/style.css';
import type {
    GraphNode as AppGraphNode,
    GraphEdge as AppGraphEdge,
    NodeRunResult,
    Palette,
    Structure,
    DocumentListItem,
    WorkflowDefinition,
    WorkflowDefinitionListItemHydrated,
} from '../../api/types';
import { useAuth } from '../../contexts/AuthContext';
import {
    DEFAULT_PALETTE_COLORS,
    normalizeWorkflowPaletteColors,
    resolveFallbackWorkflowPalette,
} from '../../domain/paletteDefaults';
import { appEdgeToFlow, appNodeToFlow } from './graphConverters';
import { canonicalStopFromGraph } from './workflowStopCanonical';
import { nodeTypes } from './nodeTypes';
import { OutputOverrideModal } from './OutputOverrideModal';
import { enrichNodesForCanvasFlow, styleEdgesForCanvas } from './workflowCanvasEnrichment';
import { partitionCanvasSelection } from './workflowCanvasSelection';
import { unionLoopBodyNodeIds } from '../../domain/workflowLoopBodyNodeIds';
import { CENTER_PANEL_MIN_PX } from './workflowEditorPanelLayout';
import { WorkflowRunLastRunSection } from './WorkflowRunLastRunSection';

export interface WorkflowRunReplayViewProps {
    workflow: WorkflowDefinition;
    /** When the selected run changes (including another run of the same workflow), the canvas refits. */
    runId: string | null;
    allWorkflows: WorkflowDefinitionListItemHydrated[];
    palettes: Palette[];
    structures: Structure[];
    documents: DocumentListItem[];
    lastRunNodeData: Record<string, NodeRunResult>;
    /** Session forced outputs for Re-run (badges + Explorer override UI). */
    outputOverrides?: Record<string, unknown>;
    onOutputOverridesChange?: (next: Record<string, unknown>) => void;
}

export function WorkflowRunReplayView({
    workflow,
    runId,
    allWorkflows,
    palettes,
    structures,
    documents,
    lastRunNodeData,
    outputOverrides = {},
    onOutputOverridesChange,
}: WorkflowRunReplayViewProps) {
    const { user } = useAuth();
    const compact = useCompactViewport();
    const [compactExplorerOpen, setCompactExplorerOpen] = useState(false);
    const reactFlowWrapperRef = useRef<HTMLDivElement>(null);
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [outputOverrideModalOpen, setOutputOverrideModalOpen] = useState(false);

    const activePalette = useMemo(() => {
        if (!workflow.palette_id) {
            return resolveFallbackWorkflowPalette(palettes);
        }
        return palettes.find(p => p.id === workflow.palette_id) ?? null;
    }, [workflow.palette_id, palettes]);

    const paletteColors = useMemo(() => {
        if (!activePalette?.colors) return DEFAULT_PALETTE_COLORS;
        return normalizeWorkflowPaletteColors(activePalette.colors);
    }, [activePalette]);

    const graphBuilt = useMemo(() => {
        const responseNodeIds = new Set(
            (workflow.graph.nodes as AppGraphNode[])
                .filter(n => (n as any).kind === 'utility' && (n as any).utility_type === 'response')
                .map(n => n.id),
        );
        const filteredNodes = (workflow.graph.nodes as AppGraphNode[]).filter(n => !responseNodeIds.has(n.id));
        const filteredEdges = workflow.graph.edges.filter(
            (e: { source: string; target: string }) => !responseNodeIds.has(e.source) && !responseNodeIds.has(e.target),
        );
        const flowNodes = filteredNodes.map(n => appNodeToFlow(n));
        const enrichedForEdges = flowNodes.map(n => {
            if (n.type === 'workflowRef') {
                const d = n.data as any;
                const refWf = allWorkflows.find(w => w.id === d?.workflow_id);
                const stopNode = canonicalStopFromGraph((refWf as WorkflowDefinition | undefined)?.graph);
                const rawOutputs = stopNode?.data?.required_outputs;
                const subWorkflowRequiredOutputs =
                    Array.isArray(rawOutputs) && rawOutputs.length > 0 ? rawOutputs : [{ key: 'output', type: 'string' as const }];
                return { ...n, data: { ...d, subWorkflowRequiredOutputs } };
            }
            return n;
        });
        const es = filteredEdges.map((e: AppGraphEdge, i: number) => appEdgeToFlow(e, i, enrichedForEdges, paletteColors, filteredEdges));
        return { nodes: flowNodes, edges: es };
    }, [workflow, allWorkflows, paletteColors]);

    useEffect(() => {
        setNodes(graphBuilt.nodes.map(n => ({ ...n, selected: false })));
        setEdges(graphBuilt.edges);
    }, [graphBuilt]);

    useEffect(() => {
        if (!compact) setCompactExplorerOpen(false);
    }, [compact]);

    const loopBodyNodeIds = useMemo(
        () =>
            unionLoopBodyNodeIds({
                nodes: (workflow.graph.nodes ?? []) as { id: string; kind?: string; control_type?: string; data?: { for_loop_id?: string } }[],
                edges: (workflow.graph.edges ?? []) as { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }[],
            }),
        [workflow],
    );

    const { explorerTargetNode: selectedNode } = useMemo(() => partitionCanvasSelection(nodes), [nodes]);

    const nodesForFlow = useMemo(
        () =>
            enrichNodesForCanvasFlow(nodes, edges, paletteColors, allWorkflows, structures, documents).map(
                n => ({
                    ...n,
                    data: {
                        ...(n.data as object),
                        outputOverrideActive: outputOverrides[n.id] !== undefined,
                    },
                }),
            ) as Node[],
        [nodes, edges, paletteColors, allWorkflows, structures, documents, outputOverrides],
    );

    const edgesForFlow = useMemo(
        () => styleEdgesForCanvas(edges, nodesForFlow, paletteColors, null),
        [edges, nodesForFlow, paletteColors],
    );

    const onNodesChange = useCallback((changes: NodeChange[]) => {
        setNodes(ns => applyNodeChanges(changes, ns));
    }, []);

    const onPaneClick = useCallback(() => {
        setNodes(ns => ns.map(n => ({ ...n, selected: false })));
    }, []);

    const nodeLog = selectedNode ? lastRunNodeData[selectedNode.id] : undefined;

    const fitCanvasKey =
        runId != null && runId !== '' ? `${workflow.id}:${runId}` : workflow.id;

    return (
        <div className="relative flex flex-1 min-h-0 overflow-hidden">
            {compact && compactExplorerOpen && (
                <button
                    type="button"
                    className="absolute inset-0 z-40 bg-black/40 border-0 p-0 cursor-default"
                    aria-label="Close Explorer panel"
                    onClick={() => setCompactExplorerOpen(false)}
                />
            )}
            <div className="flex-1 flex flex-col min-h-0" style={{ minWidth: compact ? 0 : CENTER_PANEL_MIN_PX }}>
                <div className="h-9 border-b border-mw-border bg-mw-card flex items-center px-2 sm:px-3 gap-2 shrink-0 min-w-0 justify-between">
                    <span className="text-xs font-medium text-mw-text-secondary truncate min-w-0">{workflow.name}</span>
                    {compact && (
                        <button
                            type="button"
                            className="shrink-0 p-2 rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-page"
                            aria-label="Open Explorer"
                            title="Explorer"
                            onClick={() => setCompactExplorerOpen(true)}
                        >
                            <PanelRight size={18} />
                        </button>
                    )}
                </div>
                <div ref={reactFlowWrapperRef} className="flex-1 min-h-0 touch-none">
                    <ReactFlow
                        nodes={nodesForFlow}
                        edges={edgesForFlow}
                        defaultEdgeOptions={{ zIndex: 1000 }}
                        connectionMode={ConnectionMode.Loose}
                        deleteKeyCode={null}
                        multiSelectionKeyCode={null}
                        onNodesChange={onNodesChange}
                        onPaneClick={onPaneClick}
                        nodeTypes={nodeTypes}
                        nodesDraggable={false}
                        nodesConnectable={false}
                        elementsSelectable
                        edgesReconnectable={false}
                        minZoom={WORKFLOW_CANVAS_MIN_ZOOM}
                        zoomOnScroll
                        zoomOnPinch
                        panOnScroll={false}
                        zoomOnDoubleClick={false}
                        preventScrolling
                        colorMode={
                            typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? 'dark' : 'light'
                        }
                        proOptions={{ hideAttribution: true }}
                        className="bg-mw-page"
                    >
                        <FitViewOnWorkflowCanvasKey fitKey={fitCanvasKey} />
                        <FitViewOnWorkflowCanvasResize fitKey={fitCanvasKey} containerRef={reactFlowWrapperRef} />
                        <Background />
                        <Controls />
                    </ReactFlow>
                </div>
            </div>
            <div
                className={
                    compact
                        ? `absolute right-0 top-0 bottom-0 z-50 flex flex-col border-l border-mw-border bg-mw-card overflow-hidden transition-transform duration-200 ease-out ${
                              compactExplorerOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
                          }`
                        : 'w-[min(420px,40vw)] shrink-0 border-l border-mw-border bg-mw-card flex flex-col overflow-hidden'
                }
                style={compact ? { width: 'min(100vw, 24rem)' } : undefined}
            >
                <div className="p-3 border-b border-mw-border shrink-0">
                    <h3 className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">Explorer</h3>
                    <p className="text-[10px] text-mw-text-secondary mt-0.5">
                        Select a node to view recorded inputs and outputs.
                    </p>
                </div>
                <div className="flex-1 overflow-y-auto min-h-0 p-3">
                    {selectedNode && onOutputOverridesChange && !loopBodyNodeIds.has(selectedNode.id) && (
                        <div className="flex flex-wrap gap-2 mb-3">
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
                                    onClick={() => {
                                        const n = { ...outputOverrides };
                                        delete n[selectedNode.id];
                                        onOutputOverridesChange(n);
                                    }}
                                    className="text-[10px] font-medium px-2 py-1 rounded border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
                                >
                                    Clear override
                                </button>
                            )}
                        </div>
                    )}
                    {selectedNode && loopBodyNodeIds.has(selectedNode.id) && onOutputOverridesChange && (
                        <p className="text-[10px] text-mw-text-secondary mb-3">
                            Output overrides are not available for steps inside a loop body.
                        </p>
                    )}
                    {selectedNode && onOutputOverridesChange && (
                        <OutputOverrideModal
                            isOpen={outputOverrideModalOpen}
                            onClose={() => setOutputOverrideModalOpen(false)}
                            nodeLabel={String((selectedNode.data as { label?: string }).label ?? selectedNode.id)}
                            initialValue={outputOverrides[selectedNode.id]}
                            onSave={value => {
                                onOutputOverridesChange({ ...outputOverrides, [selectedNode.id]: value });
                            }}
                        />
                    )}
                    {selectedNode ? (
                        <WorkflowRunLastRunSection nodeLog={nodeLog} userSettings={user?.settings as Record<string, unknown> | undefined} />
                    ) : (
                        <p className="text-sm text-mw-text-secondary text-center mt-6">Select a node on the canvas.</p>
                    )}
                </div>
            </div>
        </div>
    );
}
