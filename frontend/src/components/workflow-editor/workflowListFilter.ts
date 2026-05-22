import type { WorkflowDefinitionListItem } from '../../api/types';

/**
 * Prefix filter for workflow / project names (case-insensitive), matching palette
 * section Filters in WorkflowPaletteStepSections.
 */
export function filterNamesByPrefix<T extends { name: string }>(items: readonly T[], query: string): T[] {
    const q = query.trim().toLowerCase();
    if (!q) return [...items];
    return items.filter(i => i.name.toLowerCase().startsWith(q));
}

export type WorkflowListSort = 'updated' | 'name';

/** Sort workflow list rows (matches WorkflowEditor project drill-in ordering). */
export function sortWorkflowListItems(
    workflows: readonly WorkflowDefinitionListItem[],
    sort: WorkflowListSort,
): WorkflowDefinitionListItem[] {
    if (sort === 'name') {
        return [...workflows].sort((a, b) => {
            const byName = a.name.localeCompare(b.name);
            if (byName !== 0) return byName;
            return a.id.localeCompare(b.id);
        });
    }
    return [...workflows].sort((a, b) => {
        const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        if (tb !== ta) return tb - ta;
        return a.id.localeCompare(b.id);
    });
}
