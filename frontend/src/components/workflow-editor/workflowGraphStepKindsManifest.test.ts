import { describe, expect, it } from 'vitest';

import type { GraphNode as AppGraphNode } from '../../api/types';

import { appNodeToFlow, flowNodeToApp, getSourceOutputType } from './graphConverters';
import manifest from '../../../../shared/workflow_graph_step_kinds.json';
import { manifestSteps, type ManifestStep } from './stepKindRegistry';
import { nodeTypes } from './nodeTypes';

const WF_ID = '00000000-0000-0000-0000-0000000000aa';
const STRUCTURE_ID = '00000000-0000-0000-0000-0000000000bb';
const DOCUMENT_ID = '00000000-0000-0000-0000-0000000000cc';

function minimalAppNodeFromManifestStep(step: ManifestStep): AppGraphNode {
    const nodeId = 'parity_node';
    const pos = { x: 0, y: 0 };
    const label = 'p';

    if (step.kind === 'primitive' && 'primitive_type' in step && step.primitive_type) {
        const pt = step.primitive_type;
        if (pt === 'string') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'string',
                label,
                data: { text: '' },
                position: pos,
            };
        }
        if (pt === 'list') {
            return { id: nodeId, kind: 'primitive', primitive_type: 'list', label, data: [], position: pos };
        }
        if (pt === 'dictionary') {
            return { id: nodeId, kind: 'primitive', primitive_type: 'dictionary', label, data: {}, position: pos };
        }
        if (pt === 'boolean') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'boolean',
                label,
                data: { value: false },
                position: pos,
            };
        }
        if (pt === 'int') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'int',
                label,
                data: { value: 0 },
                position: pos,
            };
        }
        if (pt === 'datetime') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'datetime',
                label,
                data: { iso: '2026-01-01T00:00:00Z' },
                position: pos,
            };
        }
        if (pt === 'structure') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'structure',
                label,
                data: { structure_id: STRUCTURE_ID },
                position: pos,
            };
        }
        if (pt === 'document') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'document',
                label,
                data: { document_id: DOCUMENT_ID },
                position: pos,
            };
        }
        if (pt === 'image') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'image',
                label,
                data: {
                    artifact_id: '00000000-0000-0000-0000-0000000000dd',
                    required_inputs: [{ key: 'image', type: 'dictionary', value: null }],
                },
                position: pos,
            };
        }
        if (pt === 'sandbox_tick') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'sandbox_tick',
                label,
                data: {},
                position: pos,
            };
        }
        if (pt === 'gmail') {
            return {
                id: nodeId,
                kind: 'primitive',
                primitive_type: 'gmail',
                label,
                data: { message: { id: 'manifest-gmail' }, required_inputs: [{ key: 'gmail', type: 'gmail', value: null }] },
                position: pos,
            };
        }
        throw new Error(`unhandled primitive_type in test helper: ${pt}`);
    }

    if (step.kind === 'skill' && 'skill_type' in step && step.skill_type) {
        const st = step.skill_type;
        if (st === 'simple_llm_call') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'simple_llm_call',
                label,
                data: {
                    required_inputs: [{ key: 'user_prompt', type: 'string', value: null }],
                    persona_id: null,
                },
                position: pos,
            };
        }
        if (st === 'multimodal_llm') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'multimodal_llm',
                label,
                data: {
                    required_inputs: [
                        { key: 'user_prompt', type: 'string', value: null },
                        { key: 'images', type: 'list', value: null },
                    ],
                    persona_id: null,
                },
                position: pos,
            };
        }
        if (st === 'text_to_speech') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'text_to_speech',
                label,
                data: {
                    tts_model_id: null,
                    voice_sample_id: null,
                    engine: null,
                    tts_options: {},
                    required_inputs: [{ key: 'text', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        if (st === 'transcribe_audio') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'transcribe_audio',
                label,
                data: { task: 'transcribe', language: null, model: null },
                position: pos,
            };
        }
        if (st === 'audio_file_input') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'audio_file_input',
                label,
                data: { audio_artifact_id: null, task: 'transcribe', language: null, model: null },
                position: pos,
            };
        }
        if (st === 'transcribe_file') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'transcribe_file',
                label,
                data: {
                    provider: 'local_whisper',
                    audio_artifact_id: null,
                    task: 'transcribe',
                    language: null,
                    prompt: null,
                    diarization_enabled: false,
                    include_word_timestamps: false,
                    provider_model_id: null,
                },
                position: pos,
            };
        }
        if (st === 'gmail_list_messages') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'gmail_list_messages',
                label,
                data: {
                    google_connection_id: null,
                    max_results: 10,
                    unread_only: false,
                    after: null,
                    before: null,
                    required_inputs: [
                        { key: 'after', type: 'string', value: null },
                        { key: 'before', type: 'string', value: null },
                        { key: 'unread_only', type: 'boolean', value: false },
                        { key: 'query', type: 'string', value: null },
                        { key: 'max_results', type: 'int', value: 10 },
                    ],
                },
                position: pos,
            };
        }
        if (st === 'calendar_list_events') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'calendar_list_events',
                label,
                data: {
                    google_connection_id: null,
                    calendar_id: 'primary',
                    required_inputs: [
                        { key: 'time_min', type: 'string', value: null },
                        { key: 'time_max', type: 'string', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (st === 'google_docs_get_document') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'google_docs_get_document',
                label,
                data: {
                    google_connection_id: null,
                    document_url_or_id: null,
                    include_tabs_content: true,
                    required_inputs: [{ key: 'document_url_or_id', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        if (st === 'fetch_url') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'fetch_url',
                label,
                data: {
                    url: '',
                    method: 'GET',
                    headers: {},
                    timeout_ms: null,
                    cache_policy: 'default',
                    required_inputs: [{ key: 'url', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        if (st === 'capture_url_snapshot') {
            return {
                id: nodeId,
                kind: 'skill',
                skill_type: 'capture_url_snapshot',
                label,
                data: {
                    url: '',
                    full_page: true,
                    viewport_width: null,
                    viewport_height: null,
                    wait_until: 'load',
                    timeout_ms: null,
                    cache_policy: 'default',
                    required_inputs: [{ key: 'url', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        throw new Error(`unhandled skill_type in test helper: ${st}`);
    }

    if (step.kind === 'utility' && 'utility_type' in step && step.utility_type) {
        const ut = step.utility_type;
        if (ut === 'list_item_by_index') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'list_item_by_index',
                label,
                data: {
                    required_inputs: [
                        { key: 'index', type: 'int', value: 0 },
                        { key: 'list', type: 'list', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'dictionary_value_by_key') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'dictionary_value_by_key',
                label,
                data: {
                    output_value_type: 'list',
                    required_inputs: [
                        { key: 'key', type: 'string', value: '' },
                        { key: 'dictionary', type: 'dictionary', value: null },
                        { key: 'fallback', type: 'any', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'dictionary_set_value_by_key') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'dictionary_set_value_by_key',
                label,
                data: {
                    required_inputs: [
                        { key: 'dictionary', type: 'dictionary', value: null },
                        { key: 'key', type: 'string', value: '' },
                        { key: 'value', type: 'any', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'read_document_property') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'read_document_property',
                label,
                data: {
                    output_value_type: 'string',
                    required_inputs: [
                        { key: 'target_property', type: 'string', value: '' },
                        { key: 'document', type: 'document', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'sandbox_move_forward' || ut === 'sandbox_idle') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: ut,
                label,
                data: {
                    required_inputs: [{ key: 'reason', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        if (ut === 'add_days') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'add_days',
                label,
                data: {
                    required_inputs: [
                        { key: 'input', type: 'datetime', value: '2026-01-01T00:00:00Z' },
                        { key: 'days', type: 'int', value: 0 },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'string_trunc') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'string_trunc',
                label,
                data: {
                    required_inputs: [
                        { key: 'target_string', type: 'string', value: null },
                        { key: 'start_index', type: 'int', value: 0 },
                        { key: 'end_index', type: 'int', value: -1 },
                    ],
                },
                position: pos,
            };
        }
        if (ut === 'html_parse_basic') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'html_parse_basic',
                label,
                data: {
                    required_inputs: [{ key: 'html', type: 'string', value: null }],
                },
                position: pos,
            };
        }
        if (ut === 'google_docs_parse_document') {
            return {
                id: nodeId,
                kind: 'utility',
                utility_type: 'google_docs_parse_document',
                label,
                data: {
                    chunk_strategy: 'structure',
                    required_inputs: [{ key: 'document', type: 'dictionary', value: null }],
                },
                position: pos,
            };
        }
        return { id: nodeId, kind: 'utility', utility_type: ut, label, data: {}, position: pos } as AppGraphNode;
    }

    if (step.kind === 'control' && 'control_type' in step && step.control_type) {
        const ct = step.control_type;
        if (ct === 'basic_conditional') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'basic_conditional',
                label,
                data: { required_inputs: [{ key: 'condition', type: 'boolean', value: null }] },
                position: pos,
            };
        }
        if (ct === 'and' || ct === 'or' || ct === 'xor') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: ct,
                label,
                data: {
                    required_inputs: [
                        { key: 'input_a', type: 'boolean', value: null },
                        { key: 'input_b', type: 'boolean', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ct === 'is') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'is',
                label,
                data: {
                    required_inputs: [
                        { key: 'input_a', type: 'string', value: null },
                        { key: 'input_b', type: 'string', value: null },
                    ],
                },
                position: pos,
            };
        }
        if (ct === 'is_empty') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'is_empty',
                label,
                data: { required_inputs: [{ key: 'value', type: 'any', value: null }] },
                position: pos,
            };
        }
        if (ct === 'try_catch') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'try_catch',
                label,
                data: { required_inputs: [{ key: 'value', type: 'any', value: null }] },
                position: pos,
            };
        }
        if (ct === 'for_loop') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'for_loop',
                label,
                data: { required_inputs: [{ key: 'input', type: 'list', value: null }] },
                position: pos,
            };
        }
        if (ct === 'for_loop_end') {
            return {
                id: nodeId,
                kind: 'control',
                control_type: 'for_loop_end',
                label,
                data: { for_loop_id: '', exports: ['odds', 'evens'] },
                position: pos,
            };
        }
        return {
            id: nodeId,
            kind: 'control',
            control_type: ct as 'gt' | 'lt' | 'gte' | 'lte',
            label,
            data: {
                required_inputs: [
                    { key: 'input_a', type: 'string', value: null },
                    { key: 'input_b', type: 'string', value: null },
                ],
            },
            position: pos,
        };
    }

    if (step.kind === 'start') {
        return { id: nodeId, kind: 'start', label, data: {}, position: pos };
    }

    if (step.kind === 'stop') {
        return {
            id: nodeId,
            kind: 'stop',
            label,
            data: { required_outputs: [{ key: 'output', type: 'string' }] },
            position: pos,
        };
    }

    return {
        id: nodeId,
        kind: 'workflow',
        label,
        data: { workflow_id: WF_ID },
        position: pos,
    };
}

describe('workflow_graph_step_kinds manifest', () => {
    const keys = new Set(Object.keys(nodeTypes));

    it('every step declares palette_handle and editor_label uniquely', () => {
        expect(manifest.manifest_version).toBeGreaterThanOrEqual(2);
        const paletteHandles = new Set<string>();
        for (const s of manifest.steps) {
            expect('palette_handle' in s && (s as { palette_handle?: string }).palette_handle).toBeTruthy();
            expect('editor_label' in s && (s as { editor_label?: string }).editor_label?.trim()).toBeTruthy();
            const ph = (s as { palette_handle: string }).palette_handle;
            expect(paletteHandles.has(ph)).toBe(false);
            paletteHandles.add(ph);
        }
        for (const e of manifest.palette_extras ?? []) {
            const row = e as { palette_handle: string; editor_label: string };
            expect(row.palette_handle).toBeTruthy();
            expect(row.editor_label.trim()).toBeTruthy();
            expect(paletteHandles.has(row.palette_handle)).toBe(false);
            paletteHandles.add(row.palette_handle);
        }
    });

    it('every manifest react_flow_type is registered in nodeTypes', () => {
        for (const s of manifestSteps()) {
            expect(keys.has(s.react_flow_type)).toBe(true);
        }
    });

    it('appNodeToFlow uses manifest types and round-trips discriminators', () => {
        for (const s of manifestSteps()) {
            const appNode = minimalAppNodeFromManifestStep(s);
            const flow = appNodeToFlow(appNode);
            expect(flow.type).toBe(s.react_flow_type);

            const back = flowNodeToApp({ ...flow, position: flow.position });
            expect(back.kind).toBe(appNode.kind);
            if (back.kind === 'primitive' && appNode.kind === 'primitive') {
                expect(back.primitive_type).toBe(appNode.primitive_type);
            }
            if (back.kind === 'utility' && appNode.kind === 'utility') {
                expect(back.utility_type).toBe(appNode.utility_type);
            }
            if (back.kind === 'skill' && appNode.kind === 'skill') {
                expect(back.skill_type).toBe(appNode.skill_type);
            }
            if (back.kind === 'control' && appNode.kind === 'control') {
                expect(back.control_type).toBe(appNode.control_type);
            }
        }
    });
});

describe('getSourceOutputType vs manifest react_flow_type', () => {
    /** Ports where `undefined` would fall through to the default `any`; match production handle ids. */
    const defaultSourceHandle: Partial<Record<string, string>> = {
        forLoopControl: 'item',
        forLoopEndControl: 'output',
        basicConditional: 'true',
        isControl: 'true',
        isEmptyControl: 'true',
        gtControl: 'true',
        ltControl: 'true',
        gteControl: 'true',
        lteControl: 'true',
        betweenControl: 'true',
        tryCatchControl: 'output',
        andControl: 'true',
        orControl: 'true',
        xorControl: 'true',
    };

    /** `getSourceOutputType` intentionally yields `any` for these `react_flow_type` keys (see graphConverters). */
    const allowAny = new Set([
        'randomItemFromList',
        'listItemByIndex',
        'validateAgainstStructure',
        'forLoopControl',
        'stop',
    ]);

    it.each(manifestSteps())('non-accidental output type for $react_flow_type ($kind)', (step) => {
        const rf = step.react_flow_type;
        const appNode = minimalAppNodeFromManifestStep(step);
        const flow = appNodeToFlow(appNode);
        const handle = defaultSourceHandle[rf];
        const ty = getSourceOutputType([flow], flow.id, handle, []);
        if (allowAny.has(rf)) {
            expect(ty).toBe('any');
            return;
        }
        expect(ty).not.toBe('any');
    });

    it('simpleLLMCall: string without structure, dictionary with structure_id', () => {
        const simple = minimalAppNodeFromManifestStep({
            kind: 'skill',
            skill_type: 'simple_llm_call',
            react_flow_type: 'simpleLLMCall',
            pydantic_model: 'SimpleLLMCallSkillNode',
        } as ManifestStep);
        const flowPlain = appNodeToFlow(simple);
        expect(getSourceOutputType([flowPlain], flowPlain.id, undefined, [])).toBe('string');

        const withStructure = {
            ...(simple as Extract<AppGraphNode, { kind: 'skill' }>),
            data: {
                ...(simple as Extract<AppGraphNode, { kind: 'skill' }>).data,
                structure_id: STRUCTURE_ID,
            },
        } as AppGraphNode;
        const flowStruct = appNodeToFlow(withStructure);
        expect(getSourceOutputType([flowStruct], flowStruct.id, undefined, [])).toBe('dictionary');

        const flowEdge = appNodeToFlow(simple);
        const edges = [
            {
                id: 'e1',
                source: 'other',
                target: flowEdge.id,
                targetHandle: 'structure',
                sourceHandle: undefined,
            },
        ];
        expect(getSourceOutputType([flowEdge], flowEdge.id, undefined, edges as any)).toBe('dictionary');
    });

    it('multimodalLLMCall: string vs dictionary with structure_id', () => {
        const mm = minimalAppNodeFromManifestStep({
            kind: 'skill',
            skill_type: 'multimodal_llm',
            react_flow_type: 'multimodalLLMCall',
            pydantic_model: 'MultimodalLLMCallSkillNode',
        } as ManifestStep);
        const flowPlain = appNodeToFlow(mm);
        expect(getSourceOutputType([flowPlain], flowPlain.id, undefined, [])).toBe('string');
        const withStructure = {
            ...(mm as Extract<AppGraphNode, { kind: 'skill' }>),
            data: {
                ...(mm as Extract<AppGraphNode, { kind: 'skill' }>).data,
                structure_id: STRUCTURE_ID,
            },
        } as AppGraphNode;
        const flowStruct = appNodeToFlow(withStructure);
        expect(getSourceOutputType([flowStruct], flowStruct.id, undefined, [])).toBe('dictionary');
    });
});
