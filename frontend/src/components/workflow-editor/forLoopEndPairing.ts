/**
 * For Loop End pairs with a For Loop via `data.for_loop_id` (backend graph validation).
 * The editor sets this when the user wires `signal_out` → `trigger` and clears it when that edge is removed.
 */

import type { Connection } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';

export type PairForLoopEndResult = { targetId: string; forLoopId: string };

/** Default export keys for new For Loop End nodes (single neutral handle). */
export const DEFAULT_FOR_LOOP_END_EXPORTS = ['export'] as const;

function normalizeForLoopEndExports(exports: readonly string[] | undefined): string[] {
    return Array.isArray(exports) && exports.length > 0 ? [...exports] : [...DEFAULT_FOR_LOOP_END_EXPORTS];
}

/**
 * When export keys are renamed in the inspector, remap wired export edges by position
 * so runtime dictionary keys stay aligned with the visible handles.
 */
export function remapForLoopEndExportEdges(
    edges: Edge[],
    forLoopEndNodeId: string,
    oldExports: readonly string[] | undefined,
    newExports: readonly string[] | undefined,
): Edge[] {
    const oldKeys = normalizeForLoopEndExports(oldExports);
    const newKeys = normalizeForLoopEndExports(newExports);
    if (oldKeys.join('\0') === newKeys.join('\0')) return edges;

    return edges.map(edge => {
        if (edge.target !== forLoopEndNodeId || edge.targetHandle === 'trigger') return edge;
        const handle = edge.targetHandle ?? '';
        const idx = oldKeys.indexOf(handle);
        if (idx >= 0 && idx < newKeys.length) {
            const nextHandle = newKeys[idx];
            return nextHandle === handle ? edge : { ...edge, targetHandle: nextHandle };
        }
        if (newKeys.length === 1 && handle && !newKeys.includes(handle)) {
            return { ...edge, targetHandle: newKeys[0] };
        }
        return edge;
    });
}

/** When true, `onConnect` should set For Loop End `data.for_loop_id` to `params.source`. */
export function pairForLoopEndOnConnect(
    params: Pick<Connection, 'source' | 'target' | 'sourceHandle' | 'targetHandle'>,
    sourceNode: Pick<Node, 'type'> | undefined,
    targetNode: Pick<Node, 'type'> | undefined,
): PairForLoopEndResult | null {
    if (!params.source || !params.target || !sourceNode || !targetNode) return null;
    if (sourceNode.type !== 'forLoopControl') return null;
    if (targetNode.type !== 'forLoopEndControl') return null;
    if (params.sourceHandle !== 'signal_out') return null;
    if (params.targetHandle !== 'trigger') return null;
    return { targetId: params.target, forLoopId: params.source };
}

/** Clear `for_loop_id` on For Loop End nodes when their pairing trigger edge is removed. */
export function applyForLoopEndClearOnEdgeRemoved(nodes: Node[], removedEdges: Edge[]): Node[] {
    let out = nodes;
    for (const edge of removedEdges) {
        if (edge.sourceHandle !== 'signal_out' || edge.targetHandle !== 'trigger') continue;
        const target = out.find(n => n.id === edge.target);
        if (!target || target.type !== 'forLoopEndControl') continue;
        const data = (target.data ?? {}) as { for_loop_id?: string };
        if (data.for_loop_id !== edge.source) continue;
        out = out.map(n =>
            n.id === edge.target ?
                { ...n, data: { ...(n.data as object), for_loop_id: '' } }
            :   n,
        );
    }
    return out;
}
