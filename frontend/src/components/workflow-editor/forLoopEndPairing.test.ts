import { describe, expect, it } from 'vitest';
import type { Edge, Node } from '@xyflow/react';
import { applyForLoopEndClearOnEdgeRemoved, pairForLoopEndOnConnect } from './forLoopEndPairing';

describe('pairForLoopEndOnConnect', () => {
    const forLoop = { type: 'forLoopControl' } as Node;
    const forLoopEnd = { type: 'forLoopEndControl' } as Node;

    it('returns pairing when signal_out connects to trigger', () => {
        expect(
            pairForLoopEndOnConnect(
                { source: 'fl1', target: 'end1', sourceHandle: 'signal_out', targetHandle: 'trigger' },
                forLoop,
                forLoopEnd,
            ),
        ).toEqual({ targetId: 'end1', forLoopId: 'fl1' });
    });

    it('returns null when handles are wrong', () => {
        expect(
            pairForLoopEndOnConnect(
                { source: 'fl1', target: 'end1', sourceHandle: 'item', targetHandle: 'trigger' },
                forLoop,
                forLoopEnd,
            ),
        ).toBeNull();
    });

    it('returns null when node types are wrong', () => {
        expect(
            pairForLoopEndOnConnect(
                { source: 'fl1', target: 'end1', sourceHandle: 'signal_out', targetHandle: 'trigger' },
                { type: 'isControl' } as Node,
                forLoopEnd,
            ),
        ).toBeNull();
    });
});

describe('applyForLoopEndClearOnEdgeRemoved', () => {
    const mk = (id: string, for_loop_id: string): Node =>
        ({
            id,
            type: 'forLoopEndControl',
            position: { x: 0, y: 0 },
            data: { label: 'End', for_loop_id, exports: ['a'] },
        }) as Node;

    it('clears for_loop_id when pairing edge removed and id matched', () => {
        const nodes: Node[] = [mk('end1', 'fl1')];
        const edge: Edge = {
            id: 'e1',
            source: 'fl1',
            target: 'end1',
            sourceHandle: 'signal_out',
            targetHandle: 'trigger',
        };
        const next = applyForLoopEndClearOnEdgeRemoved(nodes, [edge]);
        expect((next[0].data as { for_loop_id?: string }).for_loop_id).toBe('');
    });

    it('does not clear when for_loop_id was changed to another loop', () => {
        const nodes: Node[] = [mk('end1', 'fl2')];
        const edge: Edge = {
            id: 'e1',
            source: 'fl1',
            target: 'end1',
            sourceHandle: 'signal_out',
            targetHandle: 'trigger',
        };
        const next = applyForLoopEndClearOnEdgeRemoved(nodes, [edge]);
        expect((next[0].data as { for_loop_id?: string }).for_loop_id).toBe('fl2');
    });

    it('ignores non-pairing edges', () => {
        const nodes: Node[] = [mk('end1', 'fl1')];
        const edge: Edge = {
            id: 'e1',
            source: 'x',
            target: 'end1',
            sourceHandle: 'output',
            targetHandle: 'a',
        };
        const next = applyForLoopEndClearOnEdgeRemoved(nodes, [edge]);
        expect((next[0].data as { for_loop_id?: string }).for_loop_id).toBe('fl1');
    });
});
