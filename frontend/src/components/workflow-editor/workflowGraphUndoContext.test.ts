import { describe, expect, it } from 'vitest';
import {
    reactFlowEdgeChangesSkipUndoRecord,
    reactFlowNodeChangesSkipUndoRecord,
} from './workflowGraphUndoContext';
import type { EdgeChange, NodeChange } from '@xyflow/react';

describe('reactFlowNodeChangesSkipUndoRecord', () => {
    it('skips empty', () => {
        expect(reactFlowNodeChangesSkipUndoRecord([], { nodeDrag: false, nodeResize: false })).toBe(true);
    });

    it('skips selection-only', () => {
        const changes: NodeChange[] = [
            { id: 'a', type: 'select', selected: true },
        ];
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: false, nodeResize: false })).toBe(true);
    });

    it('skips position while drag', () => {
        const changes: NodeChange[] = [{ id: 'a', type: 'position', position: { x: 1, y: 2 } }];
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: true, nodeResize: false })).toBe(true);
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: false, nodeResize: false })).toBe(false);
    });

    it('skips dimensions while resize', () => {
        const changes: NodeChange[] = [
            { id: 'a', type: 'dimensions', dimensions: { width: 10, height: 20 } },
        ];
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: false, nodeResize: true })).toBe(true);
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: false, nodeResize: false })).toBe(false);
    });

    it('skips replace-only (embedded node useReactFlow setNodes)', () => {
        const changes: NodeChange[] = [
            {
                id: 'a',
                type: 'replace',
                item: { id: 'a', position: { x: 0, y: 0 }, data: {} },
            },
        ];
        expect(reactFlowNodeChangesSkipUndoRecord(changes, { nodeDrag: false, nodeResize: false })).toBe(true);
    });
});

describe('reactFlowEdgeChangesSkipUndoRecord', () => {
    it('skips empty', () => {
        expect(reactFlowEdgeChangesSkipUndoRecord([])).toBe(true);
    });

    it('skips selection-only', () => {
        const changes: EdgeChange[] = [{ id: 'e', type: 'select', selected: true }];
        expect(reactFlowEdgeChangesSkipUndoRecord(changes)).toBe(true);
    });

    it('does not skip remove', () => {
        const changes: EdgeChange[] = [{ id: 'e', type: 'remove' }];
        expect(reactFlowEdgeChangesSkipUndoRecord(changes)).toBe(false);
    });
});
