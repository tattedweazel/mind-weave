import type { WorkflowRunResult } from '../api/types';

/** Merge per-tick sandbox brain runs into sticky client state. */
export function mergeSandboxWorkflowRuns(
    prev: Record<string, WorkflowRunResult | null>,
    tickRuns: Record<string, WorkflowRunResult | null>,
    aliveCreatureIds: readonly string[],
): Record<string, WorkflowRunResult | null> {
    const alive = new Set(aliveCreatureIds);
    const next: Record<string, WorkflowRunResult | null> = {};

    for (const [creatureId, run] of Object.entries(prev)) {
        if (alive.has(creatureId)) {
            next[creatureId] = run;
        }
    }

    for (const [creatureId, run] of Object.entries(tickRuns)) {
        if (alive.has(creatureId) && run != null) {
            next[creatureId] = run;
        }
    }

    return next;
}

/** Summary line for the tick transcript (current tick only). */
export function sandboxTickTranscriptSummary(tickRuns: Record<string, WorkflowRunResult | null>): string {
    const runs = Object.values(tickRuns).filter((run): run is WorkflowRunResult => run != null);
    if (runs.length > 0) {
        return `${runs.length} brain run${runs.length === 1 ? '' : 's'}`;
    }
    return 'no workflow runs';
}
