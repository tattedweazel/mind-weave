import { describe, expect, it } from 'vitest';

import type { WorkflowRunResult } from '../api/types';
import { mergeSandboxWorkflowRuns, sandboxTickTranscriptSummary } from './sandboxWorkflowRunMerge';

function run(id: string): WorkflowRunResult {
    return {
        workflow_id: `wf-${id}`,
        status: 'ok',
        node_results: [],
    };
}

describe('mergeSandboxWorkflowRuns', () => {
    it('populates from first non-null tick run', () => {
        const result = mergeSandboxWorkflowRuns({}, { c1: run('a') }, ['c1']);
        expect(result).toEqual({ c1: run('a') });
    });

    it('ignores null tick entries without clearing prior run', () => {
        const prev = { c1: run('a') };
        const result = mergeSandboxWorkflowRuns(prev, { c1: null }, ['c1']);
        expect(result).toEqual(prev);
    });

    it('overwrites with newer non-null run for same creature', () => {
        const prev = { c1: run('old') };
        const newer = run('new');
        const result = mergeSandboxWorkflowRuns(prev, { c1: newer }, ['c1']);
        expect(result.c1).toBe(newer);
    });

    it('prunes removed creature ids', () => {
        const prev = { c1: run('a'), c2: run('b') };
        const result = mergeSandboxWorkflowRuns(prev, { c1: null }, ['c1']);
        expect(result).toEqual({ c1: run('a') });
    });

    it('adds runs for new creatures while keeping existing sticky runs', () => {
        const prev = { c1: run('a') };
        const result = mergeSandboxWorkflowRuns(prev, { c2: run('b') }, ['c1', 'c2']);
        expect(result.c1).toEqual(run('a'));
        expect(result.c2).toEqual(run('b'));
    });
});

describe('sandboxTickTranscriptSummary', () => {
    it('reports brain runs when present this tick', () => {
        expect(sandboxTickTranscriptSummary({ c1: run('a') })).toBe('1 brain run');
        expect(sandboxTickTranscriptSummary({ c1: run('a'), c2: run('b') })).toBe('2 brain runs');
    });

    it('reports no workflow runs when tick has none', () => {
        expect(sandboxTickTranscriptSummary({ c1: null })).toBe('no workflow runs');
        expect(sandboxTickTranscriptSummary({})).toBe('no workflow runs');
    });
});
