import type { Node } from '@xyflow/react';
import { describe, expect, it } from 'vitest';
import {
    FLOW_EDGE_SELECTED_CLASS,
    canvasSelectedNodes,
    explorerTargetNodeFromCanvasSelection,
    flowEdgeSelectionClassName,
    mergeCanvasSelectionIntoNodeData,
    multiCanvasSelectionActive,
    partitionCanvasSelection,
} from './workflowCanvasSelection';

describe('canvas multi-select helpers', () => {
    const n = (id: string, selected?: boolean): Node =>
        ({ id, type: 'stringPrimitive', position: { x: 0, y: 0 }, data: { label: id, text: '' }, selected }) as Node;

    it('canvasSelectedNodes filters on selected', () => {
        expect(canvasSelectedNodes([n('a', true), n('b')])).toHaveLength(1);
        expect(canvasSelectedNodes([n('a'), n('b')])).toHaveLength(0);
    });

    it('explorerTargetNodeFromCanvasSelection returns one node or null', () => {
        expect(explorerTargetNodeFromCanvasSelection([n('a', true)])?.id).toBe('a');
        expect(explorerTargetNodeFromCanvasSelection([n('a', true), n('b', true)])).toBeNull();
        expect(explorerTargetNodeFromCanvasSelection([n('a')])).toBeNull();
    });

    it('multiCanvasSelectionActive is true only when 2+ selected', () => {
        expect(multiCanvasSelectionActive([n('a', true), n('b', true)])).toBe(true);
        expect(multiCanvasSelectionActive([n('a', true)])).toBe(false);
    });

    it('partitionCanvasSelection aggregates counts', () => {
        const p0 = partitionCanvasSelection([n('a'), n('b')]);
        expect(p0.multiCanvasSelectActive).toBe(false);
        expect(p0.explorerTargetNode).toBeNull();
        expect(p0.selectedCanvasNodes).toHaveLength(0);
        const p1 = partitionCanvasSelection([n('a', true)]);
        expect(p1.explorerTargetNode?.id).toBe('a');
        expect(p1.multiCanvasSelectActive).toBe(false);
        const p2 = partitionCanvasSelection([n('a', true), n('b', true)]);
        expect(p2.explorerTargetNode).toBeNull();
        expect(p2.multiCanvasSelectActive).toBe(true);
    });
});

describe('mergeCanvasSelectionIntoNodeData', () => {
    it('sets isCanvasSelected from the flag', () => {
        expect(mergeCanvasSelectionIntoNodeData({ label: 'x' }, true)).toEqual({ label: 'x', isCanvasSelected: true });
        expect(mergeCanvasSelectionIntoNodeData({ label: 'x' }, false)).toEqual({ label: 'x', isCanvasSelected: false });
    });

    it('supports empty data', () => {
        expect(mergeCanvasSelectionIntoNodeData({}, false)).toEqual({ isCanvasSelected: false });
    });
});

describe('flowEdgeSelectionClassName', () => {
    it('preserves existing class when not selected', () => {
        expect(flowEdgeSelectionClassName('foo', 'e1', null)).toBe('foo');
        expect(flowEdgeSelectionClassName('foo', 'e1', 'e2')).toBe('foo');
    });

    it('appends selection class when selected', () => {
        expect(flowEdgeSelectionClassName(undefined, 'e1', 'e1')).toBe(FLOW_EDGE_SELECTED_CLASS);
        expect(flowEdgeSelectionClassName('foo', 'e1', 'e1')).toBe(
            `${FLOW_EDGE_SELECTED_CLASS} foo`,
        );
    });
});
