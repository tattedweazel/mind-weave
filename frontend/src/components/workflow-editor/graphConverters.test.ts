import { describe, expect, it } from 'vitest';
import type { Node } from '@xyflow/react';
import type { GraphNode as AppGraphNode, WorkflowDefinitionListItemHydrated } from '../../api/types';
import {
    ANNOTATION_NOTE_DEFAULT_HEIGHT,
    ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
    ANNOTATION_NOTE_DEFAULT_WIDTH,
    ANNOTATION_NOTE_DEFAULT_Z_INDEX,
    ANNOTATION_REGION_DEFAULT_Z_INDEX,
    appEdgeToFlow,
    appNodeToFlow,
    coerceDatetimePrimitiveUseNow,
    flowNodeToApp,
    hoistStepDiscriminatorsFromData,
    normalizeUpsertDocumentRequiredInputs,
    resolveWorkflowRefLabels,
} from './graphConverters';

describe('graphConverters', () => {
    it('flowNodeToApp preserves every Stop required_output (matches persisted graph for dirty checks)', () => {
        const app: AppGraphNode = {
            id: 'n_stop',
            kind: 'stop',
            label: 'Stop',
            data: {
                required_outputs: [
                    { key: 'first', type: 'string' },
                    { key: 'second', type: 'string' },
                ],
            },
            position: { x: 10, y: 20 },
        };
        const flow = appNodeToFlow(app);
        const back = flowNodeToApp(flow as Node);
        expect(back.kind).toBe('stop');
        expect((back as Extract<AppGraphNode, { kind: 'stop' }>).data?.required_outputs).toEqual(
            app.data?.required_outputs,
        );
    });

    it('coerceDatetimePrimitiveUseNow reads useNow on data or root', () => {
        expect(coerceDatetimePrimitiveUseNow({ useNow: true })).toBe(true);
        expect(coerceDatetimePrimitiveUseNow({ use_now: false })).toBe(false);
        expect(coerceDatetimePrimitiveUseNow({ iso: null }, { use_now: true })).toBe(true);
        expect(coerceDatetimePrimitiveUseNow({ iso: null }, { useNow: true })).toBe(true);
        expect(coerceDatetimePrimitiveUseNow({ use_now: 'true' })).toBe(true);
    });

    it('appNodeToFlow maps data.useNow to flow data.use_now', () => {
        const app: AppGraphNode = {
            id: 'n_dt',
            kind: 'primitive',
            primitive_type: 'datetime',
            label: 'DateTime',
            data: { iso: null, useNow: true } as any,
            position: { x: 0, y: 0 },
        } as AppGraphNode;
        const flow = appNodeToFlow(app);
        expect(flow.type).toBe('dateTimePrimitive');
        expect((flow.data as { use_now?: boolean }).use_now).toBe(true);
    });

    it('hoistStepDiscriminatorsFromData moves primitive_type from data to node root', () => {
        const raw = {
            id: 'n1',
            kind: 'primitive' as const,
            label: 'Dict',
            position: { x: 0, y: 0 },
            data: { primitive_type: 'dictionary', foo: 1 },
        } as unknown as AppGraphNode;
        const h = hoistStepDiscriminatorsFromData(raw);
        expect((h as { primitive_type?: string }).primitive_type).toBe('dictionary');
        expect((h as { data: { foo?: number } }).data).toEqual({ foo: 1 });
    });

    it('appNodeToFlow uses invalidStep (not stop) when control_type is missing', () => {
        const bad: AppGraphNode = {
            id: 'n_fl',
            kind: 'control',
            label: 'For Loop',
            data: { required_inputs: [{ key: 'input', type: 'list', value: null }] },
            position: { x: 0, y: 0 },
        } as AppGraphNode;
        const flow = appNodeToFlow(bad);
        expect(flow.type).toBe('invalidStep');
        const back = flowNodeToApp(flow as Node);
        expect(back).toEqual(bad);
    });

    it('appNodeToFlow uses dictionary primitive after hoisting primitive_type out of data', () => {
        const raw = {
            id: 'n_b',
            kind: 'primitive' as const,
            label: 'Bucket',
            position: { x: 0, y: 0 },
            data: { primitive_type: 'dictionary' },
        } as unknown as AppGraphNode;
        const flow = appNodeToFlow(raw);
        expect(flow.type).toBe('dictionaryPrimitive');
    });

    it('appEdgeToFlow maps Stop data edges to required_outputs[0].key (not legacy output)', () => {
        const paletteColors: Record<string, string> = {};
        const nodes: Node[] = [
            {
                id: 'n_list',
                type: 'listPrimitive',
                position: { x: 0, y: 0 },
                data: { label: 'L' },
            } as Node,
            {
                id: 'n_stop',
                type: 'stop',
                position: { x: 1, y: 0 },
                data: {
                    label: 'Stop',
                    required_outputs: [{ key: 'results', type: 'list' }],
                },
            } as Node,
        ];
        const edge = appEdgeToFlow(
            {
                source: 'n_list',
                target: 'n_stop',
                source_handle: 'output',
                target_handle: 'output',
            },
            0,
            nodes,
            paletteColors,
        );
        expect(edge.targetHandle).toBe('results');
    });

    it('appEdgeToFlow maps mistaken addToList target_handle output to value', () => {
        const paletteColors: Record<string, string> = {};
        const nodes: Node[] = [
            {
                id: 'n_llm',
                type: 'simpleLLMCall',
                position: { x: 0, y: 0 },
                data: { label: 'LLM' },
            } as Node,
            {
                id: 'n_atl',
                type: 'addToList',
                position: { x: 1, y: 0 },
                data: { label: 'Add' },
            } as Node,
        ];
        const edge = appEdgeToFlow(
            {
                source: 'n_llm',
                target: 'n_atl',
                source_handle: 'output',
                target_handle: 'output',
            },
            0,
            nodes,
            paletteColors,
        );
               expect(edge.targetHandle).toBe('value');
    });

    it('appEdgeToFlow maps null upsertDocument target_handle to content when title is inline and body empty', () => {
        const paletteColors: Record<string, string> = {};
        const nodes: Node[] = [
            {
                id: 'n_txt',
                type: 'stringPrimitive',
                position: { x: 0, y: 0 },
                data: { label: 'S', value: 'body' },
            } as Node,
            {
                id: 'n_up',
                type: 'upsertDocument',
                position: { x: 1, y: 0 },
                data: {
                    label: 'Save',
                    required_inputs: [
                        { key: 'name', type: 'string', value: 'My Title' },
                        { key: 'content', type: 'string', value: '' },
                    ],
                },
            } as Node,
        ];
        const edge = appEdgeToFlow(
            { source: 'n_txt', target: 'n_up', source_handle: null, target_handle: null },
            0,
            nodes,
            paletteColors,
        );
        expect(edge.targetHandle).toBe('content');
    });

    it('appEdgeToFlow maps upsertDocument content-alias target_handles to content', () => {
        const paletteColors: Record<string, string> = {};
        const nodes: Node[] = [
            {
                id: 'n_llm',
                type: 'simpleLLMCall',
                position: { x: 0, y: 0 },
                data: { label: 'LLM' },
            } as Node,
            {
                id: 'n_up',
                type: 'upsertDocument',
                position: { x: 1, y: 0 },
                data: {
                    label: 'Save',
                    required_inputs: [
                        { key: 'name', type: 'string', value: 'T' },
                        { key: 'content', type: 'string', value: '' },
                    ],
                },
            } as Node,
        ];
        for (const th of ['output', 'markdown', 'body', 'text'] as const) {
            const edge = appEdgeToFlow(
                { source: 'n_llm', target: 'n_up', source_handle: 'output', target_handle: th },
                0,
                nodes,
                paletteColors,
            );
            expect(edge.targetHandle).toBe('content');
        }
    });

    it('annotation note round-trips app → flow → app', () => {
        const app: AppGraphNode = {
            id: 'n_ann',
            kind: 'annotation',
            annotation_type: 'note',
            label: 'My note',
            data: {
                text: 'Hello',
                color: '#ff0000',
                label_font_size_px: 14,
                content_font_size_px: 18,
                width: 300,
                height: 140,
            },
            position: { x: 5, y: 6 },
        };
        const flow = appNodeToFlow(app);
        expect(flow.type).toBe('annotationNote');
        expect(flow.zIndex).toBe(ANNOTATION_NOTE_DEFAULT_Z_INDEX);
        expect((flow.data as { z_index?: number }).z_index).toBe(ANNOTATION_NOTE_DEFAULT_Z_INDEX);
        expect(flow.connectable).toBe(false);
        expect((flow.style as { width?: number }).width).toBe(300);
        expect((flow.style as { height?: number }).height).toBe(140);
        expect((flow.data as { text?: string }).text).toBe('Hello');
        expect((flow.data as { width?: number; height?: number }).width).toBe(300);
        expect((flow.data as { width?: number; height?: number }).height).toBe(140);
        expect((flow.data as { content_font_size_px?: number }).content_font_size_px).toBe(18);
        expect((flow.data as { label_font_size_px?: number }).label_font_size_px).toBe(14);
        expect((flow.data as { label_align?: string }).label_align).toBe('left');
        expect((flow.data as { content_align?: string }).content_align).toBe('left');
        const back = flowNodeToApp(flow as Node);
        expect(back.kind).toBe('annotation');
        expect((back as { annotation_type?: string }).annotation_type).toBe('note');
        expect((back as { label?: string }).label).toBe('My note');
        expect((back as { data?: { text?: string; color?: string } }).data?.text).toBe('Hello');
        expect((back as { data?: { color?: string } }).data?.color).toBe('#ff0000');
        expect((back as { data?: { content_font_size_px?: number } }).data?.content_font_size_px).toBe(18);
        expect((back as { data?: { label_font_size_px?: number } }).data?.label_font_size_px).toBe(14);
        expect((back as { data?: { width?: number; height?: number } }).data?.width).toBe(300);
        expect((back as { data?: { width?: number; height?: number } }).data?.height).toBe(140);
        expect((back as { data?: { label_align?: string } }).data?.label_align).toBe('left');
        expect((back as { data?: { content_align?: string } }).data?.content_align).toBe('left');
        expect((back as { data?: { z_index?: number } }).data?.z_index).toBe(ANNOTATION_NOTE_DEFAULT_Z_INDEX);
    });

    it('annotation note preserves label and content alignment on round-trip', () => {
        const app: AppGraphNode = {
            id: 'n_ann_align',
            kind: 'annotation',
            annotation_type: 'note',
            label: 'Aligned',
            data: {
                text: 'x',
                label_align: 'center',
                content_align: 'right',
                width: 200,
                height: 120,
            },
            position: { x: 0, y: 0 },
        };
        const flow = appNodeToFlow(app);
        expect((flow.data as { label_align?: string }).label_align).toBe('center');
        expect((flow.data as { content_align?: string }).content_align).toBe('right');
        const back = flowNodeToApp(flow as Node);
        expect((back as { data?: { label_align?: string; content_align?: string } }).data).toMatchObject({
            label_align: 'center',
            content_align: 'right',
        });
    });

    it('annotation note coerces invalid alignment to left on flow → app', () => {
        const flow: Node = {
            id: 'n_bad_align',
            type: 'annotationNote',
            position: { x: 0, y: 0 },
            style: { width: 200, height: 120 },
            data: {
                label: 'N',
                text: '',
                color: null,
                label_font_size_px: 10,
                content_font_size_px: 12,
                label_align: 'justify',
                content_align: 'CENTER',
                width: 200,
                height: 120,
            },
        };
        const back = flowNodeToApp(flow);
        const d = (back as { data?: { label_align?: string; content_align?: string } }).data;
        expect(d?.label_align).toBe('left');
        expect(d?.content_align).toBe('left');
    });

    it('annotation note without width/height gets default dimensions on app → flow', () => {
        const app: AppGraphNode = {
            id: 'n_ann2',
            kind: 'annotation',
            annotation_type: 'note',
            label: 'Note',
            data: { text: '' },
            position: { x: 0, y: 0 },
        };
        const flow = appNodeToFlow(app);
        expect((flow.style as { width?: number }).width).toBe(ANNOTATION_NOTE_DEFAULT_WIDTH);
        expect((flow.style as { height?: number }).height).toBe(ANNOTATION_NOTE_DEFAULT_HEIGHT);
        expect((flow.data as { label_font_size_px?: number }).label_font_size_px).toBe(
            ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
        );
        expect((flow.data as { label_align?: string }).label_align).toBe('left');
        expect((flow.data as { content_align?: string }).content_align).toBe('left');
        expect(flow.zIndex).toBe(ANNOTATION_NOTE_DEFAULT_Z_INDEX);
        expect((flow.data as { z_index?: number }).z_index).toBe(ANNOTATION_NOTE_DEFAULT_Z_INDEX);
    });

    it('annotation note round-trips with zIndex', () => {
        const app: AppGraphNode = {
            id: 'n_note_z',
            kind: 'annotation',
            annotation_type: 'note',
            label: 'Stacked',
            data: {
                text: '',
                width: 100,
                height: 100,
                z_index: 42,
            },
            position: { x: 0, y: 0 },
        };
        const flow = appNodeToFlow(app);
        expect(flow.zIndex).toBe(42);
        expect((flow.data as { z_index?: number }).z_index).toBe(42);
        const back = flowNodeToApp(flow as Node);
        expect((back as { data?: { z_index?: number } }).data?.z_index).toBe(42);
    });

    it('annotation note clamps out-of-range z_index on app → flow', () => {
        const app: AppGraphNode = {
            id: 'n_note_clamp',
            kind: 'annotation',
            annotation_type: 'note',
            label: 'N',
            data: { text: '', width: 50, height: 50, z_index: 5000 },
            position: { x: 0, y: 0 },
        };
        const flow = appNodeToFlow(app);
        expect(flow.zIndex).toBe(999);
        expect((flow.data as { z_index?: number }).z_index).toBe(999);
    });

    it('annotation region round-trips with zIndex, dimensions, color, and label font size', () => {
        const app: AppGraphNode = {
            id: 'n_reg',
            kind: 'annotation',
            annotation_type: 'region',
            label: 'Group',
            data: {
                width: 300,
                height: 200,
                color: '#00aa00',
                label_font_size_px: 16,
                label_align: 'right',
                z_index: -7,
            },
            position: { x: 1, y: 2 },
        };
        const flow = appNodeToFlow(app);
        expect(flow.type).toBe('annotationRegion');
        expect(flow.zIndex).toBe(-7);
        expect(flow.style).toEqual({ width: 300, height: 200 });
        expect((flow.data as { color?: string; label_font_size_px?: number; z_index?: number }).color).toBe('#00aa00');
        expect((flow.data as { label_font_size_px?: number }).label_font_size_px).toBe(16);
        expect((flow.data as { label_align?: string }).label_align).toBe('right');
        expect((flow.data as { z_index?: number }).z_index).toBe(-7);
        const back = flowNodeToApp(flow as Node);
        expect(back.kind).toBe('annotation');
        expect((back as { annotation_type?: string }).annotation_type).toBe('region');
        expect(
            (back as {
                data?: {
                    width?: number;
                    height?: number;
                    color?: string;
                    label_font_size_px?: number;
                    label_align?: string;
                    z_index?: number;
                };
            }).data,
        ).toEqual({
            width: 300,
            height: 200,
            color: '#00aa00',
            label_font_size_px: 16,
            label_align: 'right',
            z_index: -7,
        });
    });

    it('annotation region without z_index gets default stack order on app → flow', () => {
        const app: AppGraphNode = {
            id: 'n_reg2',
            kind: 'annotation',
            annotation_type: 'region',
            label: 'R',
            data: { width: 100, height: 100 },
            position: { x: 0, y: 0 },
        };
        const flow = appNodeToFlow(app);
        expect(flow.zIndex).toBe(ANNOTATION_REGION_DEFAULT_Z_INDEX);
        expect((flow.data as { z_index?: number }).z_index).toBe(ANNOTATION_REGION_DEFAULT_Z_INDEX);
    });

    it('hoistStepDiscriminatorsFromData hoists annotation_type from data', () => {
        const raw = {
            id: 'x',
            kind: 'annotation' as const,
            label: 'N',
            data: { annotation_type: 'note' as const, text: 't' },
            position: { x: 0, y: 0 },
        } as unknown as AppGraphNode;
        const h = hoistStepDiscriminatorsFromData(raw);
        expect((h as { annotation_type?: string }).annotation_type).toBe('note');
        expect((h.data as { text?: string }).text).toBe('t');
    });
});

describe('normalizeUpsertDocumentRequiredInputs', () => {
    it('returns legacy four-slot defaults when absent, null, empty, or noise-only after filter', () => {
        const quadKeys = ['name', 'content', 'existing_document_id', 'write_mode'];
        expect(normalizeUpsertDocumentRequiredInputs(null).map(r => r.key)).toEqual(quadKeys);
        expect(normalizeUpsertDocumentRequiredInputs(undefined).map(r => r.key)).toEqual(quadKeys);
        expect(normalizeUpsertDocumentRequiredInputs([]).map(r => r.key)).toEqual(quadKeys);
        expect(
            normalizeUpsertDocumentRequiredInputs([{ key: 'bogus', type: 'string', value: '' }] as any).map(r => r.key),
        ).toEqual(quadKeys);
    });

    it('keeps name + content only when that is what the graph stores', () => {
        const ri = [
            { key: 'name', type: 'string' as const, value: 'Episode 1' },
            { key: 'content', type: 'string' as const, value: '' },
        ];
        expect(normalizeUpsertDocumentRequiredInputs(ri)).toEqual([
            { key: 'name', type: 'string', value: 'Episode 1' },
            { key: 'content', type: 'string', value: '' },
        ]);
    });

    it('preserves optional inputs only when authored', () => {
        const ri = [
            { key: 'name', type: 'string' as const, value: '' },
            { key: 'content', type: 'string' as const, value: 'x' },
            { key: 'write_mode', type: 'string' as const, value: 'append' },
        ];
        expect(normalizeUpsertDocumentRequiredInputs(ri).map(r => r.key)).toEqual(['name', 'content', 'write_mode']);
    });
});

describe('upsert_document graph round-trip', () => {
    it('legacy empty required_inputs expands to four slots on canvas', () => {
        const app = {
            id: 'n_ud',
            kind: 'utility',
            utility_type: 'upsert_document',
            label: 'Upsert Document',
            data: {},
            position: { x: 0, y: 0 },
        } as AppGraphNode;
        const flow = appNodeToFlow(app);
        expect(flow.type).toBe('upsertDocument');
        const inputs = ((flow.data as { required_inputs?: { key: string }[] }).required_inputs ?? []).map(r => r.key);
        expect(inputs).toEqual(['name', 'content', 'existing_document_id', 'write_mode']);
    });

    it('trimmed required_inputs survives flow → app → flow', () => {
        const flow = {
            id: 'n_save',
            type: 'upsertDocument',
            position: { x: 10, y: 20 },
            data: {
                label: 'Save text as Document',
                required_inputs: [
                    { key: 'name', type: 'string', value: '' },
                    { key: 'content', type: 'string', value: '' },
                ],
            },
        } as Node;
        const app = flowNodeToApp(flow);
        expect(app.kind).toBe('utility');
        expect((app as Extract<AppGraphNode, { kind: 'utility' }>).utility_type).toBe('upsert_document');
        const reqs =
            (((app as { data?: { required_inputs?: { key: string }[] } }).data ?? {}).required_inputs ?? []).map(
                r => r.key,
            );
        expect(reqs).toEqual(['name', 'content']);
        const back = appNodeToFlow(app as AppGraphNode);
        expect(
            ((back.data as { required_inputs?: { key: string }[] }).required_inputs ?? []).map(r => r.key),
        ).toEqual(['name', 'content']);
    });
});

describe('resolveWorkflowRefLabels', () => {
    const childId = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

    it('preserves a custom data.label over the referenced workflow name', () => {
        const workflows = [
            { id: childId, user_id: 'u1', name: 'Backend Name', description: null },
        ] as WorkflowDefinitionListItemHydrated[];
        const nodes: Node[] = [
            {
                id: 'n1',
                type: 'workflowRef',
                position: { x: 0, y: 0 },
                data: { label: 'User label', workflow_id: childId },
            },
        ];
        const out = resolveWorkflowRefLabels(nodes, workflows);
        expect((out[0].data as { label?: string }).label).toBe('User label');
    });

    it('falls back to referenced workflow name when data.label is missing', () => {
        const workflows = [
            { id: childId, user_id: 'u1', name: 'Default From List', description: null },
        ] as WorkflowDefinitionListItemHydrated[];
        const nodes: Node[] = [
            {
                id: 'n1',
                type: 'workflowRef',
                position: { x: 0, y: 0 },
                data: { workflow_id: childId },
            },
        ];
        const out = resolveWorkflowRefLabels(nodes, workflows);
        expect((out[0].data as { label?: string }).label).toBe('Default From List');
    });
});
