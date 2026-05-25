import { describe, expect, it } from 'vitest';

import type { WorkflowRunResult } from '../api/types';
import type { SandboxNestedWorkflowRunJson } from '../domain/sandbox/types';
import {
    filterNestedWorkflowRunsForCreature,
    mergeSandboxNestedWorkflowRuns,
    nestedWorkflowRunKey,
    sandboxTickTranscriptSummaryWithNested,
} from './sandboxNestedWorkflowRunMerge';

function nestedEntry(
    meta: Partial<SandboxNestedWorkflowRunJson['meta']> & Pick<SandboxNestedWorkflowRunJson['meta'], 'kind' | 'creature_id'>,
): SandboxNestedWorkflowRunJson {
    return {
        meta: {
            label: meta.label ?? 'Label',
            tick: meta.tick ?? 1,
            workflow_id: meta.workflow_id ?? 'wf-1',
            fixture_id: meta.fixture_id,
            region_id: meta.region_id,
            trigger_mode: meta.trigger_mode,
            node_labels: meta.node_labels ?? {},
            ...meta,
        },
        run: {
            workflow_id: 'wf-1',
            status: 'ok',
            node_results: [],
        } as WorkflowRunResult,
    };
}

describe('nestedWorkflowRunKey', () => {
    it('keys fixture runs by fixture and creature', () => {
        const key = nestedWorkflowRunKey(
            nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1' }).meta,
        );
        expect(key).toBe('fixture:fx1:c1');
    });

    it('keys region runs by region, creature, and mode', () => {
        const key = nestedWorkflowRunKey(
            nestedEntry({
                kind: 'region_trigger',
                creature_id: 'c1',
                region_id: 'r1',
                trigger_mode: 'enter',
            }).meta,
        );
        expect(key).toBe('region:r1:c1:enter');
    });
});

describe('mergeSandboxNestedWorkflowRuns', () => {
    it('replaces sticky entries for the same source key', () => {
        const first = nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1', tick: 1 });
        const second = nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1', tick: 2 });
        const merged = mergeSandboxNestedWorkflowRuns([first], [second]);
        expect(merged).toHaveLength(1);
        expect(merged[0].meta.tick).toBe(2);
    });
});

describe('filterNestedWorkflowRunsForCreature', () => {
    it('returns all runs when no creature is selected', () => {
        const runs = [
            nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1' }),
            nestedEntry({ kind: 'region_trigger', creature_id: 'c2', region_id: 'r1', trigger_mode: 'enter' }),
        ];
        expect(filterNestedWorkflowRunsForCreature(runs, null)).toHaveLength(2);
    });

    it('filters to the selected creature', () => {
        const runs = [
            nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1' }),
            nestedEntry({ kind: 'region_trigger', creature_id: 'c2', region_id: 'r1', trigger_mode: 'enter' }),
        ];
        expect(filterNestedWorkflowRunsForCreature(runs, 'c1')).toHaveLength(1);
    });
});

describe('sandboxTickTranscriptSummaryWithNested', () => {
    it('summarizes brain, fixture, and region counts', () => {
        const summary = sandboxTickTranscriptSummaryWithNested(
            { c1: { workflow_id: 'wf', status: 'ok', node_results: [] } as WorkflowRunResult },
            [
                nestedEntry({ kind: 'fixture', creature_id: 'c1', fixture_id: 'fx1' }),
                nestedEntry({
                    kind: 'region_trigger',
                    creature_id: 'c1',
                    region_id: 'r1',
                    trigger_mode: 'enter',
                }),
            ],
        );
        expect(summary).toBe('1 brain run, 1 fixture run, 1 region trigger run');
    });
});
