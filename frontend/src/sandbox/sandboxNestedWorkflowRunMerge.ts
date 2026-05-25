import type { WorkflowRunResult } from '../api/types';
import type { SandboxNestedWorkflowRunJson } from '../domain/sandbox/types';

/** Stable key for sticky latest-only nested run storage. */
export function nestedWorkflowRunKey(meta: SandboxNestedWorkflowRunJson['meta']): string {
    if (meta.kind === 'fixture') {
        return `fixture:${meta.fixture_id ?? meta.label}:${meta.creature_id}`;
    }
    return `region:${meta.region_id ?? meta.label}:${meta.creature_id}:${meta.trigger_mode ?? ''}`;
}

/** Merge per-tick nested runs into sticky client state (latest per source key). */
export function mergeSandboxNestedWorkflowRuns(
    prev: SandboxNestedWorkflowRunJson[],
    tickRuns: SandboxNestedWorkflowRunJson[],
): SandboxNestedWorkflowRunJson[] {
    const byKey = new Map<string, SandboxNestedWorkflowRunJson>();
    for (const entry of prev) {
        byKey.set(nestedWorkflowRunKey(entry.meta), entry);
    }
    for (const entry of tickRuns) {
        byKey.set(nestedWorkflowRunKey(entry.meta), entry);
    }
    return Array.from(byKey.values());
}

/** Nested runs for a selected creature, or all when none selected. */
export function filterNestedWorkflowRunsForCreature(
    runs: readonly SandboxNestedWorkflowRunJson[],
    selectedCreatureId: string | null,
): SandboxNestedWorkflowRunJson[] {
    if (!selectedCreatureId) {
        return [...runs];
    }
    return runs.filter(run => run.meta.creature_id === selectedCreatureId);
}

export function sandboxTickTranscriptSummaryWithNested(
    brainRuns: Record<string, WorkflowRunResult | null>,
    nestedRuns: readonly SandboxNestedWorkflowRunJson[],
): string {
    const brainCount = Object.values(brainRuns).filter((run): run is WorkflowRunResult => run != null).length;
    const fixtureCount = nestedRuns.filter(run => run.meta.kind === 'fixture').length;
    const regionCount = nestedRuns.filter(run => run.meta.kind === 'region_trigger').length;
    const parts: string[] = [];
    parts.push(`${brainCount} brain run${brainCount === 1 ? '' : 's'}`);
    if (fixtureCount > 0) {
        parts.push(`${fixtureCount} fixture run${fixtureCount === 1 ? '' : 's'}`);
    }
    if (regionCount > 0) {
        parts.push(`${regionCount} region trigger run${regionCount === 1 ? '' : 's'}`);
    }
    if (brainCount === 0 && fixtureCount === 0 && regionCount === 0) {
        return 'no workflow runs';
    }
    return parts.join(', ');
}
