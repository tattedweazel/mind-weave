import type { WorkflowDefinition, WorkflowDefinitionListItemHydrated } from '../api/types';

export function workflowListEntryHasGraph(w: WorkflowDefinitionListItemHydrated | undefined): boolean {
    if (!w) return false;
    const g = w.graph;
    return g != null && Array.isArray(g.nodes);
}

export function mergeWorkflowDefinitionIntoList(
    list: WorkflowDefinitionListItemHydrated[],
    full: WorkflowDefinition,
): WorkflowDefinitionListItemHydrated[] {
    const i = list.findIndex(x => x.id === full.id);
    if (i === -1) {
        return [...list, full];
    }
    return list.map((x, idx) => (idx === i ? { ...x, ...full } : x));
}
