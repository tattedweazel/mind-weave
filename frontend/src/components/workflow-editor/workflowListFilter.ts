/**
 * Prefix filter for workflow / project names (case-insensitive), matching palette
 * section Filters in WorkflowPaletteStepSections.
 */
export function filterNamesByPrefix<T extends { name: string }>(items: readonly T[], query: string): T[] {
    const q = query.trim().toLowerCase();
    if (!q) return [...items];
    return items.filter(i => i.name.toLowerCase().startsWith(q));
}
