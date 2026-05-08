import { describe, expect, it } from 'vitest';
import {
    WORKFLOW_GRAPH_UNDO_PAST_MAX,
    createWorkflowGraphHistory,
    normalizeGraphForHistorySnapshot,
} from './workflowGraphHistory';
import type { Edge, Node } from '@xyflow/react';

const sampleNode = (id: string, extra: Partial<Node> = {}): Node =>
    ({
        id,
        type: 'default',
        position: { x: 0, y: 0 },
        data: { label: id },
        ...extra,
    }) as Node;

const sampleEdge = (id: string, extra: Partial<Edge> = {}): Edge =>
    ({
        id,
        source: 'a',
        target: 'b',
        ...extra,
    }) as Edge;

describe('normalizeGraphForHistorySnapshot', () => {
    it('clears selection and run ephemera', () => {
        const nodes: Node[] = [
            sampleNode('a', { selected: true, data: { label: 'a', isRunning: true } }),
        ];
        const edges: Edge[] = [sampleEdge('e1', { animated: true, selected: true })];
        const snap = normalizeGraphForHistorySnapshot(nodes, edges);
        expect(snap.nodes[0]!.selected).toBe(false);
        expect((snap.nodes[0]!.data as Record<string, unknown>).isRunning).toBeUndefined();
        expect(snap.edges[0]!.animated).toBe(false);
        expect(snap.edges[0]!.selected).toBe(false);
    });

    it('does not mutate originals', () => {
        const nodes: Node[] = [sampleNode('a', { selected: true, data: { label: 'a', isRunning: true } })];
        const edges: Edge[] = [sampleEdge('e1', { animated: true })];
        normalizeGraphForHistorySnapshot(nodes, edges);
        expect(nodes[0]!.selected).toBe(true);
        expect((nodes[0]!.data as Record<string, unknown>).isRunning).toBe(true);
        expect(edges[0]!.animated).toBe(true);
    });
});

describe('createWorkflowGraphHistory', () => {
    it('push then undo restores prior graph', () => {
        const h = createWorkflowGraphHistory();
        const g0 = { nodes: [sampleNode('a')], edges: [] as Edge[] };
        const g1 = { nodes: [sampleNode('a'), sampleNode('b')], edges: [] as Edge[] };
        h.pushSnapshot(g0.nodes, g0.edges);
        const back = h.undo(g1.nodes, g1.edges);
        expect(back).not.toBeNull();
        expect(back!.nodes.map(n => n.id)).toEqual(['a']);
        expect(h.canUndo()).toBe(false);
        expect(h.canRedo()).toBe(true);
    });

    it('redo restores after undo', () => {
        const h = createWorkflowGraphHistory();
        const g0 = { nodes: [sampleNode('a')], edges: [] as Edge[] };
        const g1 = { nodes: [sampleNode('a'), sampleNode('b')], edges: [] as Edge[] };
        h.pushSnapshot(g0.nodes, g0.edges);
        h.undo(g1.nodes, g1.edges);
        const forward = h.redo(g0.nodes, g0.edges);
        expect(forward!.nodes.map(n => n.id)).toEqual(['a', 'b']);
        expect(h.canRedo()).toBe(false);
        expect(h.canUndo()).toBe(true);
    });

    it('new push clears redo stack', () => {
        const h = createWorkflowGraphHistory();
        h.pushSnapshot([sampleNode('a')], []);
        h.undo([sampleNode('a'), sampleNode('b')], []);
        expect(h.canRedo()).toBe(true);
        h.pushSnapshot([sampleNode('x')], []);
        expect(h.canRedo()).toBe(false);
    });

    it('trims past to WORKFLOW_GRAPH_UNDO_PAST_MAX', () => {
        const h = createWorkflowGraphHistory();
        for (let i = 0; i < WORKFLOW_GRAPH_UNDO_PAST_MAX + 3; i++) {
            h.pushSnapshot([sampleNode(`n${i}`)], []);
        }
        // Each push adds one to past then trim — after many pushes, oldest fall off
        let steps = 0;
        let nodes: Node[] = [sampleNode('latest')];
        let edges: Edge[] = [];
        while (h.canUndo()) {
            const prev = h.undo(nodes, edges);
            expect(prev).not.toBeNull();
            nodes = prev!.nodes;
            edges = prev!.edges;
            steps++;
        }
        expect(steps).toBe(WORKFLOW_GRAPH_UNDO_PAST_MAX);
    });

    it('clear resets stacks', () => {
        const h = createWorkflowGraphHistory();
        h.pushSnapshot([sampleNode('a')], []);
        h.clear();
        expect(h.canUndo()).toBe(false);
        expect(h.undo([sampleNode('b')], [])).toBeNull();
    });

    it('undo and redo return null when empty', () => {
        const h = createWorkflowGraphHistory();
        expect(h.undo([sampleNode('a')], [])).toBeNull();
        h.pushSnapshot([sampleNode('a')], []);
        h.undo([sampleNode('b')], []);
        h.redo([sampleNode('a')], []);
        expect(h.redo([sampleNode('a')], [])).toBeNull();
    });
});
