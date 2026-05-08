import { describe, expect, it } from 'vitest';
import type { WorkflowDefinition } from '../../api/types';
import { canonicalStopFromGraph } from './workflowStopCanonical';

describe('canonicalStopFromGraph', () => {
    it('returns undefined when graph is missing or has no Stop nodes', () => {
        expect(canonicalStopFromGraph(undefined)).toBeUndefined();
        expect(canonicalStopFromGraph(null)).toBeUndefined();
        expect(canonicalStopFromGraph({ nodes: [], edges: [], schema_version: 1 } as unknown as WorkflowDefinition['graph'])).toBeUndefined();
    });

    it('returns the only Stop node', () => {
        const stop = { id: 's1', kind: 'stop', data: { stop_priority: 0, required_outputs: [{ key: 'output', type: 'string' }] } };
        const graph = { nodes: [{ id: 'a', kind: 'start' }, stop], edges: [], schema_version: 1 } as unknown as WorkflowDefinition['graph'];
        expect(canonicalStopFromGraph(graph)).toEqual(stop);
    });

    it('prefers higher stop_priority', () => {
        const low = { id: 's-low', kind: 'stop', data: { stop_priority: 0 } };
        const high = { id: 's-high', kind: 'stop', data: { stop_priority: 5 } };
        const graph = { nodes: [low, high], edges: [], schema_version: 1 } as unknown as WorkflowDefinition['graph'];
        expect(canonicalStopFromGraph(graph)).toEqual(high);
    });

    it('on equal priority picks lexicographically smallest id', () => {
        const b = { id: 's-b', kind: 'stop', data: { stop_priority: 1 } };
        const a = { id: 's-a', kind: 'stop', data: { stop_priority: 1 } };
        const graph = { nodes: [b, a], edges: [], schema_version: 1 } as unknown as WorkflowDefinition['graph'];
        expect(canonicalStopFromGraph(graph)).toEqual(a);
    });
});
