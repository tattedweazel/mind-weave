/**
 * Mirrors backend `for_loop_body_node_ids` / loop-boundary rules so the UI can
 * disable output overrides for nodes inside a for-loop body (v1).
 */

export interface LoopBodyGraphNode {
    id: string;
    kind?: string;
    control_type?: string;
    data?: { for_loop_id?: string };
}

export interface LoopBodyGraphEdge {
    source: string;
    target: string;
    sourceHandle?: string | null;
    targetHandle?: string | null;
}

function forLoopEndIds(nodes: LoopBodyGraphNode[]): Set<string> {
    const s = new Set<string>();
    for (const n of nodes) {
        if (n.kind === 'control' && n.control_type === 'for_loop_end') {
            s.add(n.id);
        }
    }
    return s;
}

function iterationSeedTargets(
    forLoopId: string,
    edges: LoopBodyGraphEdge[],
    endIds: Set<string>,
): Set<string> {
    const seeds = new Set<string>();
    for (const e of edges) {
        if (e.source !== forLoopId) continue;
        if (endIds.has(e.target)) continue;
        const sh = e.sourceHandle || '';
        const th = e.targetHandle || '';
        if (sh === 'signal_out' && th === 'trigger') {
            seeds.add(e.target);
        } else if (sh === 'item') {
            seeds.add(e.target);
        }
    }
    return seeds;
}

function forwardClosureFromSeeds(
    seeds: Set<string>,
    edges: LoopBodyGraphEdge[],
    banned: Set<string>,
    endIds: Set<string>,
): Set<string> {
    const result = new Set<string>();
    const queue: string[] = [];
    for (const s of seeds) {
        if (banned.has(s) || endIds.has(s)) continue;
        result.add(s);
        queue.push(s);
    }
    while (queue.length) {
        const u = queue.shift()!;
        for (const e of edges) {
            if (e.source !== u) continue;
            const v = e.target;
            if (banned.has(v) || endIds.has(v)) continue;
            if (!result.has(v)) {
                result.add(v);
                queue.push(v);
            }
        }
    }
    return result;
}

/** Node ids inside the body of the given For Loop control node (excludes For Loop End). */
export function forLoopBodyNodeIds(
    forLoopId: string,
    edges: LoopBodyGraphEdge[],
    nodes: LoopBodyGraphNode[],
): Set<string> {
    const endIds = forLoopEndIds(nodes);
    const seeds = iterationSeedTargets(forLoopId, edges, endIds);
    return forwardClosureFromSeeds(seeds, edges, new Set([forLoopId]), endIds);
}

/** Union of all loop bodies in the graph (for override UI). */
export function unionLoopBodyNodeIds(graph: {
    nodes?: LoopBodyGraphNode[];
    edges?: LoopBodyGraphEdge[];
}): Set<string> {
    const nodes = graph.nodes ?? [];
    const edges = graph.edges ?? [];
    const forLoopIds = nodes.filter(n => n.kind === 'control' && n.control_type === 'for_loop').map(n => n.id);
    const out = new Set<string>();
    for (const fid of forLoopIds) {
        const body = forLoopBodyNodeIds(fid, edges, nodes);
        for (const b of body) {
            out.add(b);
        }
    }
    return out;
}
