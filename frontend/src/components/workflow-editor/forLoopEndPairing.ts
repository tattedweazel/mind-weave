/**
 * For Loop End pairs with a For Loop via `data.for_loop_id` (backend graph validation).
 * The editor sets this when the user wires `signal_out` → `trigger` and clears it when that edge is removed.
 */

import type { Connection } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';

export type PairForLoopEndResult = { targetId: string; forLoopId: string };

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
