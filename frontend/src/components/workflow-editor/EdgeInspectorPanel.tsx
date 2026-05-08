import { useMemo, useState } from 'react';
import type { Edge, Node } from '@xyflow/react';
import { Trash2 } from 'lucide-react';
import type { NodeRunResult, WorkflowRunResult } from '../../api/types';
import { InspectorSection } from './InspectorSection';
import { JsonTreeView } from './JsonTreeView';
import { EdgePayloadDetailModal } from './EdgePayloadDetailModal';
import { getSourceOutputType } from './graphConverters';
import {
    resolveEdgeDeliveredPayload,
    resolveLatestNodeRun,
    workflowEdgeDataTypeLabel,
    workflowNodeFlowTypeLabel,
} from './edgeInspectorUtils';

export interface EdgeInspectorPanelProps {
    edge: Edge;
    nodes: Node[];
    /** Needed for accurate output typing (e.g. LLM structured output, workflow ref handles). */
    edges: Edge[];
    /** Same map as node Explorer “Last run” (streamed node_end results). */
    lastRunNodeData: Record<string, NodeRunResult>;
    runResult: WorkflowRunResult | null;
    deletingEdgeId: string | null;
    onRequestDelete: () => void;
    onCancelDelete: () => void;
    onConfirmDelete: () => void;
}

function NodeEndSummary({ node }: { node: Node | undefined }) {
    if (!node) {
        return <span className="text-xs text-mw-text-secondary">(Unknown node)</span>;
    }
    const label = String((node.data as { label?: string } | undefined)?.label ?? node.id);
    const role = workflowNodeFlowTypeLabel(node.type);
    return (
        <div className="space-y-0.5 text-xs">
            <div className="font-medium text-mw-text-primary truncate" title={label}>
                {label}
            </div>
            <div className="text-mw-text-secondary">
                {role}
                <span className="text-mw-text-secondary/80 font-mono text-[10px] ml-1.5">({node.id})</span>
            </div>
        </div>
    );
}

export function EdgeInspectorPanel({
    edge,
    nodes,
    edges,
    lastRunNodeData,
    runResult,
    deletingEdgeId,
    onRequestDelete,
    onCancelDelete,
    onConfirmDelete,
}: EdgeInspectorPanelProps) {
    const [payloadModalOpen, setPayloadModalOpen] = useState(false);

    const sourceNode = nodes.find((n) => n.id === edge.source);
    const targetNode = nodes.find((n) => n.id === edge.target);

    const dataTypeKey = useMemo(
        () => getSourceOutputType(nodes, edge.source, edge.sourceHandle ?? undefined, edges),
        [nodes, edges, edge.source, edge.sourceHandle],
    );
    const dataTypeLabel = workflowEdgeDataTypeLabel(dataTypeKey);

    const sourceRun = useMemo(
        () => resolveLatestNodeRun(edge.source, lastRunNodeData, runResult),
        [edge.source, lastRunNodeData, runResult],
    );
    const targetRun = useMemo(
        () => resolveLatestNodeRun(edge.target, lastRunNodeData, runResult),
        [edge.target, lastRunNodeData, runResult],
    );

    const payloadRes = useMemo(
        () =>
            resolveEdgeDeliveredPayload(
                {
                    source: edge.source,
                    target: edge.target,
                    sourceHandle: edge.sourceHandle,
                    targetHandle: edge.targetHandle,
                },
                targetNode?.type,
                sourceRun,
                targetRun,
            ),
        [edge.source, edge.target, edge.sourceHandle, edge.targetHandle, targetNode?.type, sourceRun, targetRun],
    );

    const rawLine =
        payloadRes.kind === 'payload' ?
            typeof payloadRes.value === 'object' && payloadRes.value !== null ?
                JSON.stringify(payloadRes.value, null, 2)
            :   String(payloadRes.value)
        :   null;

    return (
        <div className="p-4 space-y-3 text-sm">
            <InspectorSection
                title="Connection"
                description={
                    <>
                        Handle <span className="font-mono text-mw-text-primary">{edge.sourceHandle ?? '—'}</span>{' '}
                        →{' '}
                        <span className="font-mono text-mw-text-primary">{edge.targetHandle ?? '—'}</span>
                    </>
                }
            >
                <div>
                    <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1">
                        Data type
                    </div>
                    <div className="text-xs font-medium text-mw-text-primary">{dataTypeLabel}</div>
                    <div className="text-[10px] text-mw-text-secondary mt-0.5 font-mono">{dataTypeKey}</div>
                </div>
            </InspectorSection>

            <InspectorSection title="Source node">
                <NodeEndSummary node={sourceNode} />
            </InspectorSection>

            <InspectorSection title="Destination node">
                <NodeEndSummary node={targetNode} />
            </InspectorSection>

            <InspectorSection
                title="Last run"
                description="Value that reached the destination input along this wire (from the last successful resolution we can infer)."
            >
                {payloadRes.kind === 'control_flow' ?
                    <p className="text-xs text-mw-text-secondary leading-snug">{payloadRes.message}</p>
                : payloadRes.kind === 'none' ?
                    <p className="text-xs text-mw-text-secondary leading-snug">{payloadRes.message}</p>
                :   <>
                        <div className="text-[10px] text-mw-text-secondary">
                            Source:{' '}
                            <span className="font-mono text-mw-text-primary">
                                {payloadRes.via === 'resolved_inputs' ? 'target run (resolved_inputs)' : 'source run (output slot)'}
                            </span>
                        </div>
                        <div className="rounded-lg border border-mw-border bg-mw-card-alt max-h-56 overflow-y-auto p-2">
                            {typeof payloadRes.value === 'object' && payloadRes.value !== null ?
                                <JsonTreeView data={payloadRes.value} defaultExpandedDepth={2} />
                            :   <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-mw-text-primary">
                                    {rawLine}
                                </pre>
                            }
                        </div>
                        <button
                            type="button"
                            onClick={() => setPayloadModalOpen(true)}
                            className="w-full py-2 text-xs font-medium text-mw-primary hover:bg-mw-primary-muted rounded-lg transition-colors"
                        >
                            Open full payload view
                        </button>
                    </>
                }
            </InspectorSection>

            {payloadRes.kind === 'payload' && (
                <EdgePayloadDetailModal
                    open={payloadModalOpen}
                    onClose={() => setPayloadModalOpen(false)}
                    title="Edge payload (last run)"
                    payload={payloadRes.value}
                />
            )}

            <div className="pt-2">
                {deletingEdgeId === edge.id ?
                    <div className="space-y-2 rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 px-3 py-3">
                        <div className="text-xs font-medium text-red-600 dark:text-red-400">Are you sure?</div>
                        <div className="flex gap-2">
                            <button
                                type="button"
                                onClick={onConfirmDelete}
                                className="flex-1 py-1.5 text-xs font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                            >
                                Delete
                            </button>
                            <button
                                type="button"
                                onClick={onCancelDelete}
                                className="flex-1 py-1.5 text-xs font-medium bg-mw-card-alt hover:opacity-90 text-mw-text-primary rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                :   <button
                        type="button"
                        onClick={onRequestDelete}
                        className="w-full flex items-center justify-center gap-2 py-2 text-xs font-medium text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                    >
                        <Trash2 size={14} /> Remove Connection
                    </button>
                }
            </div>
        </div>
    );
}
