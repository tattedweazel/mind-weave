import { describe, expect, it } from 'vitest';
import {
    extractPayloadFromSourceOutput,
    resolveEdgeDeliveredPayload,
    resolveLatestNodeRun,
    workflowEdgeDataTypeLabel,
    workflowNodeFlowTypeLabel,
} from './edgeInspectorUtils';

describe('workflowNodeFlowTypeLabel', () => {
    it('maps known react flow types', () => {
        expect(workflowNodeFlowTypeLabel('gmailListMessages')).toBe('Gmail List');
        expect(workflowNodeFlowTypeLabel('fetchUrl')).toBe('Fetch URL');
        expect(workflowNodeFlowTypeLabel('unknownX')).toBe('unknownX');
    });
});

describe('workflowEdgeDataTypeLabel', () => {
    it('formats palette keys', () => {
        expect(workflowEdgeDataTypeLabel('string')).toBe('String');
        expect(workflowEdgeDataTypeLabel('foo_bar')).toBe('foo bar');
    });
});

describe('extractPayloadFromSourceOutput', () => {
    it('picks start slot by handle', () => {
        expect(
            extractPayloadFromSourceOutput(
                { kind: 'start', outputs: { a: 'hi', b: 2 }, text: '', node_id: 's' },
                'a',
            ),
        ).toBe('hi');
    });

    it('unwraps response and list', () => {
        expect(extractPayloadFromSourceOutput({ kind: 'response', text: 'x', node_id: 'n' }, undefined)).toBe('x');
        expect(extractPayloadFromSourceOutput({ kind: 'list', data: [1], node_id: 'n' }, undefined)).toEqual([1]);
    });
});

describe('resolveEdgeDeliveredPayload', () => {
    it('returns control_flow for trigger target', () => {
        const r = resolveEdgeDeliveredPayload(
            { source: 'a', target: 'b', sourceHandle: 'true', targetHandle: 'trigger' },
            'simpleLLMCall',
            undefined,
            undefined,
        );
        expect(r.kind).toBe('control_flow');
    });

    it('prefers resolved_inputs', () => {
        const r = resolveEdgeDeliveredPayload(
            { source: 'a', target: 'b', sourceHandle: 'output', targetHandle: 'user_prompt' },
            'simpleLLMCall',
            { node_id: 'a', status: 'ok', output: { kind: 'string', text: 'ignored', node_id: 'a' } },
            {
                node_id: 'b',
                status: 'ok',
                details: { resolved_inputs: { user_prompt: 'from resolved' } },
            },
        );
        expect(r.kind).toBe('payload');
        if (r.kind === 'payload') {
            expect(r.via).toBe('resolved_inputs');
            expect(r.value).toBe('from resolved');
        }
    });

    it('falls back to source output', () => {
        const r = resolveEdgeDeliveredPayload(
            { source: 'a', target: 'b', sourceHandle: undefined, targetHandle: 'user_prompt' },
            'simpleLLMCall',
            { node_id: 'a', status: 'ok', output: { kind: 'string', text: 'upstream', node_id: 'a' } },
            { node_id: 'b', status: 'ok', details: {} },
        );
        expect(r.kind).toBe('payload');
        if (r.kind === 'payload') {
            expect(r.via).toBe('source_output');
            expect(r.value).toBe('upstream');
        }
    });
});

describe('resolveLatestNodeRun', () => {
    it('prefers lastRun map over runResult list', () => {
        expect(
            resolveLatestNodeRun(
                'n1',
                { n1: { node_id: 'n1', status: 'ok', step_number: 2 } },
                { node_results: [{ node_id: 'n1', status: 'ok', step_number: 1 }] },
            )?.step_number,
        ).toBe(2);
    });

    it('picks max step_number from runResult', () => {
        expect(
            resolveLatestNodeRun('n1', {}, {
                node_results: [
                    { node_id: 'n1', status: 'ok', step_number: 1 },
                    { node_id: 'n1', status: 'ok', step_number: 3 },
                    { node_id: 'n1', status: 'ok', step_number: 2 },
                ],
            })?.step_number,
        ).toBe(3);
    });
});
