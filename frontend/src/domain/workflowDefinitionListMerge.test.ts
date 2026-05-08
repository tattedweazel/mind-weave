import { describe, expect, it } from 'vitest';
import {
    mergeWorkflowDefinitionIntoList,
    workflowListEntryHasGraph,
} from './workflowDefinitionListMerge';
import type { WorkflowDefinition } from '../api/types';

describe('workflowListEntryHasGraph', () => {
    it('is false when graph is missing', () => {
        expect(workflowListEntryHasGraph(undefined)).toBe(false);
        expect(
            workflowListEntryHasGraph({
                id: 'a',
                user_id: null,
                name: 'x',
                description: null,
            }),
        ).toBe(false);
    });

    it('is true when graph has nodes array', () => {
        expect(
            workflowListEntryHasGraph({
                id: 'a',
                user_id: null,
                name: 'x',
                description: null,
                graph: { nodes: [], edges: [] },
            }),
        ).toBe(true);
    });
});

describe('mergeWorkflowDefinitionIntoList', () => {
    const full: WorkflowDefinition = {
        id: 'wf-1',
        user_id: null,
        name: 'Full',
        description: null,
        graph: { nodes: [{ id: 's', kind: 'start', label: 'S', data: {}, position: { x: 0, y: 0 } }], edges: [] },
        created_at: '2020-01-01T00:00:00Z',
        updated_at: '2020-01-01T00:00:00Z',
    };

    it('appends when id is new', () => {
        const list = [
            { id: 'other', user_id: null, name: 'O', description: null },
        ];
        const next = mergeWorkflowDefinitionIntoList(list, full);
        expect(next).toHaveLength(2);
        expect(next.find(w => w.id === 'wf-1')).toMatchObject({ name: 'Full', graph: full.graph });
    });

    it('replaces row in place when id matches', () => {
        const list = [
            { id: 'wf-1', user_id: null, name: 'Old', description: null },
        ];
        const next = mergeWorkflowDefinitionIntoList(list, full);
        expect(next).toHaveLength(1);
        expect(next[0].name).toBe('Full');
        expect(next[0].graph).toEqual(full.graph);
    });
});
