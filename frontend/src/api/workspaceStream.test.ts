import { describe, it, expect, vi } from 'vitest';
import { consumeWorkspaceTurnStream } from './workspaceStream';

function streamResponse(chunks: string[]): Response {
    const enc = new TextEncoder();
    return new Response(
        new ReadableStream({
            start(controller) {
                for (const c of chunks) {
                    controller.enqueue(enc.encode(c));
                }
                controller.close();
            },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    );
}

describe('consumeWorkspaceTurnStream', () => {
    it('parses token and done events', async () => {
        const tokens: string[] = [];
        const done = vi.fn();
        const body =
            'data: {"event":"token","text":"Hi"}\n\n' +
            'data: {"event":"token","text":" there"}\n\n' +
            'data: {"event":"done","phase":"completed","turn_id":"t1","memory_proposed":0}\n\n';
        await consumeWorkspaceTurnStream(streamResponse([body]), t => tokens.push(t), done);
        expect(tokens.join('')).toBe('Hi there');
        expect(done).toHaveBeenCalledWith({
            phase: 'completed',
            proposal_id: undefined,
            turn_id: 't1',
            replay_id: undefined,
            memory_proposed: 0,
        });
    });

    it('parses capability_proposal and proposal-phase done', async () => {
        const proposal = vi.fn();
        const done = vi.fn();
        const body =
            'data: {"event":"token","text":"Ready"}\n\n' +
            'data: {"event":"capability_proposal","proposal_id":"p1","capabilities":[{"capability_key":"wf:x","name":"W","input_bindings":{"a":1}}]}\n\n' +
            'data: {"event":"done","phase":"proposal","proposal_id":"p1","memory_proposed":0}\n\n';
        await consumeWorkspaceTurnStream(
            streamResponse([body]),
            () => {},
            done,
            proposal,
        );
        expect(proposal).toHaveBeenCalledWith({
            proposal_id: 'p1',
            capabilities: [{ capability_key: 'wf:x', name: 'W', input_bindings: { a: 1 } }],
        });
        expect(done).toHaveBeenCalledWith({
            phase: 'proposal',
            proposal_id: 'p1',
            turn_id: undefined,
            replay_id: undefined,
            memory_proposed: 0,
        });
    });

    it('parses stage events', async () => {
        const stages: { stage: string; status: string; ms?: number }[] = [];
        const body =
            'data: {"event":"stage","stage":"interpret","status":"started"}\n\n' +
            'data: {"event":"stage","stage":"interpret","status":"completed","ms":12.3}\n\n' +
            'data: {"event":"done","phase":"completed","memory_proposed":0}\n\n';
        await consumeWorkspaceTurnStream(
            streamResponse([body]),
            () => {},
            () => {},
            undefined,
            e => stages.push(e),
        );
        expect(stages).toEqual([
            { stage: 'interpret', status: 'started', detail: undefined },
            { stage: 'interpret', status: 'completed', ms: 12.3, detail: undefined },
        ]);
    });
});
