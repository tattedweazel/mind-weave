import type { WorkflowDefinition } from '../../api/types';

/** Minimal graph node shape for Stop selection (editor + replay). */
export type StopLikeGraphNode = {
    kind?: string;
    id?: string;
    data?: { stop_priority?: number; required_outputs?: { key: string; type: string }[] };
};

/**
 * Pick the Stop node that defines sub-workflow output typing and sandbox priority semantics:
 * highest `data.stop_priority` (default 0), then lexicographically smallest `id` on tie.
 */
export function canonicalStopFromGraph(graph: WorkflowDefinition['graph'] | null | undefined): StopLikeGraphNode | undefined {
    const nodes = graph?.nodes;
    if (!Array.isArray(nodes)) return undefined;
    const stops = nodes.filter(n => (n as { kind?: string }).kind === 'stop') as StopLikeGraphNode[];
    if (stops.length === 0) return undefined;
    return [...stops].sort((a, b) => {
        const pa = Number((a.data as { stop_priority?: number } | undefined)?.stop_priority ?? 0);
        const pb = Number((b.data as { stop_priority?: number } | undefined)?.stop_priority ?? 0);
        if (pb !== pa) return pb - pa;
        return String(a.id ?? '').localeCompare(String(b.id ?? ''));
    })[0];
}
