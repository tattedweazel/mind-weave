/**
 * Whether the workflow editor right inspector column should be mounted.
 * Tied to a loaded workflow so workflow metadata (id, etc.) is always reachable
 * without requiring a node selection or a completed run.
 */
export function isWorkflowInspectorOpen(activeWf: unknown): boolean {
    return activeWf != null;
}
