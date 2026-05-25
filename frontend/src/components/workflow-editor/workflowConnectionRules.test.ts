import type { Connection, Node } from '@xyflow/react';
import { describe, expect, it } from 'vitest';

import { getTargetHandleType, isValidWorkflowConnection, stopDataHandleKeyForConnection } from './workflowConnectionRules';

function node(partial: Pick<Node, 'id' | 'type'> & { data?: Record<string, unknown> }): Node {
    return {
        position: { x: 0, y: 0 },
        ...partial,
        data: partial.data ?? { label: partial.id },
    } as Node;
}

describe('getTargetHandleType', () => {
    it('returns required_inputs type for matching key', () => {
        const n = node({
            id: 'x',
            type: 'simpleLLMCall',
            data: {
                required_inputs: [
                    { key: 'user_prompt', type: 'string', value: null },
                    { key: 'additional_context', type: 'string', value: null },
                ],
            },
        });
        expect(getTargetHandleType(n, 'user_prompt')).toBe('string');
        expect(getTargetHandleType(n, 'missing')).toBeUndefined();
    });

    it('returns undefined for empty handle', () => {
        const n = node({ id: 'x', type: 'prependText', data: {} });
        expect(getTargetHandleType(n, '')).toBeUndefined();
        expect(getTargetHandleType(n, null)).toBeUndefined();
    });
});

describe('stopDataHandleKeyForConnection', () => {
    it('returns primary required_outputs key', () => {
        const stop = node({
            id: 's1',
            type: 'stop',
            data: { required_outputs: [{ key: 'trimmed_email', type: 'dictionary' }] },
        });
        expect(stopDataHandleKeyForConnection(stop)).toBe('trimmed_email');
    });

    it('defaults to output when missing', () => {
        const stop = node({ id: 's1', type: 'stop', data: {} });
        expect(stopDataHandleKeyForConnection(stop)).toBe('output');
    });
});

describe('isValidWorkflowConnection', () => {
    const dictSet = node({
        id: 'd1',
        type: 'dictionarySetValueByKey',
        data: { label: 'Set key' },
    });
    const stopDictionary = node({
        id: 's1',
        type: 'stop',
        data: { required_outputs: [{ key: 'output', type: 'dictionary' }] },
    });
    const stopCustomKey = node({
        id: 's2',
        type: 'stop',
        data: { required_outputs: [{ key: 'trimmed_email', type: 'dictionary' }] },
    });

    it('returns false when source or target node is missing', () => {
        const c: Connection = { source: 'x', target: 's1', sourceHandle: 'output', targetHandle: 'output' };
        expect(isValidWorkflowConnection([stopDictionary], [], c)).toBe(false);
        expect(isValidWorkflowConnection([dictSet], [], c)).toBe(false);
    });

    it('blocks annotation node endpoints', () => {
        const note = node({ id: 'n1', type: 'annotationNote', data: {} });
        const c: Connection = { source: 'd1', target: 'n1', sourceHandle: 'output', targetHandle: 'output' };
        expect(isValidWorkflowConnection([dictSet, note], [], c)).toBe(false);
        const c2: Connection = { source: 'n1', target: 's1', sourceHandle: 'output', targetHandle: 'output' };
        expect(isValidWorkflowConnection([dictSet, stopDictionary, note], [], c2)).toBe(false);
    });

    it('allows dictionarySetValueByKey output to Stop dictionary data handle', () => {
        const c: Connection = { source: 'd1', target: 's1', sourceHandle: 'output', targetHandle: 'output' };
        expect(isValidWorkflowConnection([dictSet, stopDictionary], [], c)).toBe(true);
    });

    it('allows custom Stop key when handles match', () => {
        const c: Connection = { source: 'd1', target: 's2', sourceHandle: 'output', targetHandle: 'trimmed_email' };
        expect(isValidWorkflowConnection([dictSet, stopCustomKey], [], c)).toBe(true);
    });

    it('rejects data wire when Stop key does not match', () => {
        const c: Connection = { source: 'd1', target: 's2', sourceHandle: 'output', targetHandle: 'output' };
        expect(isValidWorkflowConnection([dictSet, stopCustomKey], [], c)).toBe(false);
    });

    it('normalizes empty Stop targetHandle to data key (loose connection)', () => {
        const c = { source: 'd1', target: 's1', sourceHandle: 'output', targetHandle: '' } as Connection;
        expect(isValidWorkflowConnection([dictSet, stopDictionary], [], c)).toBe(true);
        const c2 = { source: 'd1', target: 's2', sourceHandle: 'output', targetHandle: null } as unknown as Connection;
        expect(isValidWorkflowConnection([dictSet, stopCustomKey], [], c2)).toBe(true);
    });

    it('does not normalize explicit trigger target', () => {
        const c: Connection = { source: 'd1', target: 's1', sourceHandle: 'signal_out', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([dictSet, stopDictionary], [], c)).toBe(true);
    });

    it('rejects signal_out to Stop data handle', () => {
        const c: Connection = { source: 'd1', target: 's1', sourceHandle: 'signal_out', targetHandle: 'output' };
        expect(isValidWorkflowConnection([dictSet, stopDictionary], [], c)).toBe(false);
    });

    it('rejects dictionary output wired to Stop trigger', () => {
        const c: Connection = { source: 'd1', target: 's1', sourceHandle: 'output', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([dictSet, stopDictionary], [], c)).toBe(false);
    });

    it('requires document source when Stop expects document', () => {
        const stopDoc = node({
            id: 'sd',
            type: 'stop',
            data: { required_outputs: [{ key: 'out', type: 'document' }] },
        });
        const docPrim = node({ id: 'dp', type: 'documentPrimitive', data: {} });
        const listPrim = node({ id: 'lp', type: 'listPrimitive', data: {} });
        const ok: Connection = { source: 'dp', target: 'sd', sourceHandle: 'output', targetHandle: 'out' };
        expect(isValidWorkflowConnection([docPrim, stopDoc], [], ok)).toBe(true);
        const bad: Connection = { source: 'lp', target: 'sd', sourceHandle: 'output', targetHandle: 'out' };
        expect(isValidWorkflowConnection([listPrim, stopDoc], [], bad)).toBe(false);
    });

    it('requires structure source when Stop expects structure', () => {
        const stopSt = node({
            id: 'ss',
            type: 'stop',
            data: { required_outputs: [{ key: 'schema', type: 'structure' }] },
        });
        const structPrim = node({ id: 'st', type: 'structurePrimitive', data: {} });
        const ok: Connection = { source: 'st', target: 'ss', sourceHandle: 'output', targetHandle: 'schema' };
        expect(isValidWorkflowConnection([structPrim, stopSt], [], ok)).toBe(true);
    });

    it('allows structurePrimitive only to simpleLLM structure or matching Stop', () => {
        const structPrim = node({ id: 'st', type: 'structurePrimitive', data: {} });
        const llm = node({ id: 'llm', type: 'simpleLLMCall', data: {} });
        const stopStr = node({
            id: 'sst',
            type: 'stop',
            data: { required_outputs: [{ key: 'out', type: 'structure' }] },
        });
        expect(
            isValidWorkflowConnection(
                [structPrim, llm],
                [],
                { source: 'st', target: 'llm', sourceHandle: 'output', targetHandle: 'structure' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [structPrim, stopStr],
                [],
                { source: 'st', target: 'sst', sourceHandle: 'output', targetHandle: 'out' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [dictSet, structPrim],
                [],
                { source: 'st', target: 'd1', sourceHandle: 'output', targetHandle: 'dictionary' },
            ),
        ).toBe(false);
    });

    it('allows branch true handle to feed non-trigger data targets', () => {
        const cond = node({ id: 'bc', type: 'basicConditional', data: {} });
        const c: Connection = { source: 'bc', target: 's1', sourceHandle: 'true', targetHandle: 'output' };
        expect(isValidWorkflowConnection([cond, stopDictionary], [], c)).toBe(true);
    });

    it('allows isEmptyControl false handle to feed lenFromList list input', () => {
        const ie = node({ id: 'ie', type: 'isEmptyControl', data: {} });
        const len = node({ id: 'len', type: 'lenFromList', data: {} });
        const c: Connection = { source: 'ie', target: 'len', sourceHandle: 'false', targetHandle: 'list' };
        expect(isValidWorkflowConnection([ie, len], [], c)).toBe(true);
    });

    it('allows documentPrimitive and loadDocument into readDocumentProperty document handle only', () => {
        const rdp = node({ id: 'rdp', type: 'readDocumentProperty', data: {} });
        const docPrim = node({ id: 'dp', type: 'documentPrimitive', data: {} });
        const load = node({ id: 'ld', type: 'loadDocument', data: {} });
        const listPrim = node({ id: 'lp', type: 'listPrimitive', data: {} });
        const ok1: Connection = { source: 'dp', target: 'rdp', sourceHandle: 'output', targetHandle: 'document' };
        const ok2: Connection = { source: 'ld', target: 'rdp', sourceHandle: 'output', targetHandle: 'document' };
        expect(isValidWorkflowConnection([docPrim, load, rdp], [], ok1)).toBe(true);
        expect(isValidWorkflowConnection([docPrim, load, rdp], [], ok2)).toBe(true);
        const bad: Connection = { source: 'lp', target: 'rdp', sourceHandle: 'output', targetHandle: 'document' };
        expect(isValidWorkflowConnection([listPrim, rdp], [], bad)).toBe(false);
    });

    it('rejects simpleLLM structure handle from non-structure sources', () => {
        const llm = node({ id: 'llm', type: 'simpleLLMCall', data: {} });
        const str = node({ id: 'st', type: 'structurePrimitive', data: {} });
        const dict = node({ id: 'd0', type: 'dictionaryPrimitive', data: {} });
        expect(
            isValidWorkflowConnection(
                [dict, llm],
                [],
                { source: 'd0', target: 'llm', sourceHandle: 'output', targetHandle: 'structure' },
            ),
        ).toBe(false);
        expect(
            isValidWorkflowConnection(
                [str, llm],
                [],
                { source: 'st', target: 'llm', sourceHandle: 'output', targetHandle: 'structure' },
            ),
        ).toBe(true);
    });

    it('allows ordering wire from Start to transcribeAudio trigger', () => {
        const start = node({
            id: 'st0',
            type: 'start',
            data: { required_inputs: [{ key: 'output', type: 'string' }] },
        });
        const tr = node({ id: 'tr0', type: 'transcribeAudio', data: { label: 'Voice' } });
        const c: Connection = { source: 'st0', target: 'tr0', sourceHandle: 'output', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([start, tr], [], c)).toBe(true);
    });

    it('allows ordering wire from Start to audioFileInput trigger', () => {
        const start = node({
            id: 'st0',
            type: 'start',
            data: { required_inputs: [{ key: 'output', type: 'string' }] },
        });
        const af = node({ id: 'af0', type: 'audioFileInput', data: { label: 'Audio File Input' } });
        const c: Connection = { source: 'st0', target: 'af0', sourceHandle: 'output', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([start, af], [], c)).toBe(true);
    });

    it('allows ordering wire from Start to transcribeFile trigger', () => {
        const start = node({
            id: 'st0',
            type: 'start',
            data: { required_inputs: [{ key: 'output', type: 'string' }] },
        });
        const tf = node({ id: 'tf0', type: 'transcribeFile', data: { label: 'Transcribe File' } });
        const c: Connection = { source: 'st0', target: 'tf0', sourceHandle: 'output', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([start, tf], [], c)).toBe(true);
    });

    it('allows branch true output to transcribeFile trigger', () => {
        const cond = node({ id: 'bc', type: 'basicConditional', data: {} });
        const tf = node({ id: 'tf1', type: 'transcribeFile', data: { label: 'Transcribe File' } });
        const c: Connection = { source: 'bc', target: 'tf1', sourceHandle: 'true', targetHandle: 'trigger' };
        expect(isValidWorkflowConnection([cond, tf], [], c)).toBe(true);
    });

    it('allows document sources to string or any target handles (LLM, utilities, Stop)', () => {
        const docPrim = node({ id: 'dp', type: 'documentPrimitive', data: {} });
        const load = node({ id: 'ld', type: 'loadDocument', data: {} });
        const upsert = node({ id: 'ud', type: 'upsertDocument', data: {} });

        const llmSimple = node({
            id: 'llm',
            type: 'simpleLLMCall',
            data: {
                required_inputs: [
                    { key: 'user_prompt', type: 'string', value: null },
                    { key: 'additional_context', type: 'string', value: null },
                ],
            },
        });
        const llmMm = node({
            id: 'llmM',
            type: 'multimodalLLMCall',
            data: {
                required_inputs: [
                    { key: 'user_prompt', type: 'string', value: null },
                    { key: 'images', type: 'list', value: null },
                ],
            },
        });
        const prepend = node({
            id: 'pt',
            type: 'prependText',
            data: {
                required_inputs: [
                    { key: 'target_string', type: 'string', value: null },
                    { key: 'text_to_prepend', type: 'string', value: null },
                ],
            },
        });
        const writeBody = node({
            id: 'wob',
            type: 'writeObjectToDocumentBody',
            data: { required_inputs: [{ key: 'value', type: 'any', value: null }] },
        });
        const stopStr = node({
            id: 'ss',
            type: 'stop',
            data: { required_outputs: [{ key: 'output', type: 'string' }] },
        });
        const stopDoc = node({
            id: 'sd',
            type: 'stop',
            data: { required_outputs: [{ key: 'out', type: 'document' }] },
        });

        expect(
            isValidWorkflowConnection(
                [docPrim, llmSimple],
                [],
                { source: 'dp', target: 'llm', sourceHandle: 'output', targetHandle: 'user_prompt' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [load, llmSimple],
                [],
                { source: 'ld', target: 'llm', sourceHandle: 'output', targetHandle: 'additional_context' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [upsert, llmMm],
                [],
                { source: 'ud', target: 'llmM', sourceHandle: 'output', targetHandle: 'user_prompt' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [docPrim, prepend],
                [],
                { source: 'dp', target: 'pt', sourceHandle: 'output', targetHandle: 'target_string' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [docPrim, writeBody],
                [],
                { source: 'dp', target: 'wob', sourceHandle: 'output', targetHandle: 'value' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [docPrim, stopStr],
                [],
                { source: 'dp', target: 'ss', sourceHandle: 'output', targetHandle: 'output' },
            ),
        ).toBe(true);
        expect(
            isValidWorkflowConnection(
                [docPrim, stopDoc],
                [],
                { source: 'dp', target: 'sd', sourceHandle: 'output', targetHandle: 'out' },
            ),
        ).toBe(true);
    });

    it('rejects document sources into non-string non-any inputs', () => {
        const docPrim = node({ id: 'dp', type: 'documentPrimitive', data: {} });
        const dictSet = node({
            id: 'ds',
            type: 'dictionarySetValueByKey',
            data: {
                required_inputs: [
                    { key: 'dictionary', type: 'dictionary', value: null },
                    { key: 'key', type: 'string', value: '' },
                    { key: 'value', type: 'any', value: null },
                ],
            },
        });
        const llm = node({
            id: 'llm',
            type: 'simpleLLMCall',
            data: {
                required_inputs: [{ key: 'user_prompt', type: 'string', value: null }],
            },
        });
        expect(
            isValidWorkflowConnection(
                [docPrim, dictSet],
                [],
                { source: 'dp', target: 'ds', sourceHandle: 'output', targetHandle: 'dictionary' },
            ),
        ).toBe(false);
        expect(
            isValidWorkflowConnection(
                [docPrim, llm],
                [],
                { source: 'dp', target: 'llm', sourceHandle: 'output', targetHandle: 'structure' },
            ),
        ).toBe(false);
    });
});
