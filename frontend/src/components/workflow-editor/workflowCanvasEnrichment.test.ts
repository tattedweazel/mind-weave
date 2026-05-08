import type { Node } from '@xyflow/react';
import { describe, expect, it } from 'vitest';
import type { WorkflowDefinitionListItemHydrated } from '../../api/types';
import { enrichNodesForCanvasFlow } from './workflowCanvasEnrichment';

describe('enrichNodesForCanvasFlow', () => {
    it('sets subWorkflowRequiredInputs from referenced Start required_inputs (multiple slots)', () => {
        const childId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
        const workflows = [
            {
                id: childId,
                user_id: 'u1',
                name: 'Child WF',
                description: null,
                graph: {
                    nodes: [
                        {
                            id: 'start-1',
                            kind: 'start',
                            label: 'Start',
                            data: {
                                required_inputs: [
                                    { key: 'sandbox_tick', type: 'dictionary' as const, value: null },
                                    { key: 'user_prompt', type: 'string' as const, value: null },
                                    { key: 'extra', type: 'int' as const, value: null },
                                ],
                            },
                            position: { x: 0, y: 0 },
                        },
                        {
                            id: 'stop-1',
                            kind: 'stop',
                            label: 'Stop',
                            data: {
                                required_outputs: [{ key: 'output', type: 'string' as const }],
                            },
                            position: { x: 200, y: 0 },
                        },
                    ],
                    edges: [],
                },
            },
        ] as WorkflowDefinitionListItemHydrated[];

        const nodes: Node[] = [
            {
                id: 'ref-node',
                type: 'workflowRef',
                position: { x: 100, y: 100 },
                data: { label: 'Child WF', workflow_id: childId },
            },
        ];

        const enriched = enrichNodesForCanvasFlow(nodes, [], {}, workflows, [], []);
        const ref = enriched.find(n => n.id === 'ref-node');
        expect(ref).toBeDefined();
        const d = ref?.data as {
            subWorkflowRequiredInputs?: { key: string; type: string }[];
            subWorkflowRequiredOutputs?: { key: string; type: string }[];
        };
        expect(d?.subWorkflowRequiredInputs?.map(x => x.key)).toEqual(['sandbox_tick', 'user_prompt', 'extra']);
        expect(d?.subWorkflowRequiredOutputs?.map(x => x.key)).toEqual(['output']);
    });

    it('uses synthetic output handle when child Start has required_inputs [] (matches Start node)', () => {
        const childId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
        const workflows = [
            {
                id: childId,
                user_id: 'u1',
                name: 'Child',
                description: null,
                graph: {
                    nodes: [
                        {
                            id: 'start-1',
                            kind: 'start',
                            label: 'Start',
                            data: { required_inputs: [] },
                            position: { x: 0, y: 0 },
                        },
                        {
                            id: 'stop-1',
                            kind: 'stop',
                            label: 'Stop',
                            data: { required_outputs: [{ key: 'output', type: 'string' as const }] },
                            position: { x: 200, y: 0 },
                        },
                    ],
                    edges: [],
                },
            },
        ] as WorkflowDefinitionListItemHydrated[];
        const nodes: Node[] = [
            {
                id: 'ref-node',
                type: 'workflowRef',
                position: { x: 0, y: 0 },
                data: { label: 'Child', workflow_id: childId },
            },
        ];
        const enriched = enrichNodesForCanvasFlow(nodes, [], {}, workflows, [], []);
        const d = enriched.find(n => n.id === 'ref-node')?.data as {
            subWorkflowRequiredInputs?: { key: string }[];
        };
        expect(d?.subWorkflowRequiredInputs?.map(x => x.key)).toEqual(['output']);
    });

    it('falls back to user_input when referenced workflow has no graph in list state', () => {
        const childId = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
        const workflows: WorkflowDefinitionListItemHydrated[] = [
            {
                id: childId,
                user_id: 'u1',
                name: 'No graph row',
                description: null,
            },
        ];
        const nodes: Node[] = [
            {
                id: 'ref-node',
                type: 'workflowRef',
                position: { x: 0, y: 0 },
                data: { workflow_id: childId },
            },
        ];
        const enriched = enrichNodesForCanvasFlow(nodes, [], {}, workflows, [], []);
        const d = enriched.find(n => n.id === 'ref-node')?.data as {
            subWorkflowRequiredInputs?: { key: string }[];
        };
        expect(d?.subWorkflowRequiredInputs?.map(x => x.key)).toEqual(['user_input']);
    });

    it('keeps Explorer Label as canvas subtitle when it differs from the referenced workflow name', () => {
        const childId = 'dddddddd-dddd-dddd-dddd-dddddddddddd';
        const workflows = [
            {
                id: childId,
                user_id: 'u1',
                name: 'Renamed Child Workflow',
                description: null,
                graph: {
                    nodes: [
                        {
                            id: 'start-1',
                            kind: 'start',
                            label: 'Start',
                            data: { required_inputs: [{ key: 'user_input', type: 'string' as const, value: null }] },
                            position: { x: 0, y: 0 },
                        },
                        {
                            id: 'stop-1',
                            kind: 'stop',
                            label: 'Stop',
                            data: { required_outputs: [{ key: 'output', type: 'string' as const }] },
                            position: { x: 200, y: 0 },
                        },
                    ],
                    edges: [],
                },
            },
        ] as WorkflowDefinitionListItemHydrated[];
        const nodes: Node[] = [
            {
                id: 'ref-node',
                type: 'workflowRef',
                position: { x: 0, y: 0 },
                data: { label: 'My custom label', workflow_id: childId },
            },
        ];
        const enriched = enrichNodesForCanvasFlow(nodes, [], {}, workflows, [], []);
        const d = enriched.find(n => n.id === 'ref-node')?.data as { label?: string };
        expect(d?.label).toBe('My custom label');
    });

    it('sets upsertInputHasValue for each upsert handle from edges and inline values', () => {
        const nodes: Node[] = [
            {
                id: 'n_str',
                type: 'stringPrimitive',
                position: { x: 0, y: 0 },
                data: { label: 'S', text: 'body' },
            },
            {
                id: 'n_up',
                type: 'upsertDocument',
                position: { x: 100, y: 0 },
                data: {
                    label: 'Save',
                    required_inputs: [
                        { key: 'name', type: 'string', value: 'Doc A' },
                        { key: 'content', type: 'string', value: null },
                    ],
                },
            },
        ];
        const edges = [
            {
                id: 'e1',
                source: 'n_str',
                target: 'n_up',
                sourceHandle: 'output',
                targetHandle: 'content',
                type: 'default',
            },
        ];
        const enriched = enrichNodesForCanvasFlow(nodes, edges, {}, [], [], []);
        const d = enriched.find(n => n.id === 'n_up')?.data as { upsertInputHasValue?: Record<string, boolean> };
        expect(d?.upsertInputHasValue?.name).toBe(true);
        expect(d?.upsertInputHasValue?.content).toBe(true);
    });

    it('sets isCanvasSelected from node.selected', () => {
        const nodes: Node[] = [
            { id: 'sel', type: 'stringPrimitive', position: { x: 0, y: 0 }, data: { label: 'A', text: '' }, selected: true },
            { id: 'other', type: 'stringPrimitive', position: { x: 0, y: 0 }, data: { label: 'B', text: '' }, selected: false },
        ];
        const enriched = enrichNodesForCanvasFlow(nodes, [], {}, [], [], []);
        expect((enriched.find(n => n.id === 'sel')?.data as { isCanvasSelected?: boolean }).isCanvasSelected).toBe(true);
        expect((enriched.find(n => n.id === 'other')?.data as { isCanvasSelected?: boolean }).isCanvasSelected).toBe(false);
    });
});
