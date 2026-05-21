import { describe, it, expect } from 'vitest';
import type { WorkflowDefinition } from '../api/types';
import {
    WORKFLOW_BUNDLE_EXPORT_KIND,
    WorkflowBundleExportError,
    applyBundleIdMapsToDefinition,
    buildWorkflowBundleClosure,
    buildWorkflowBundleExportDocument,
    clearWorkflowRefsInGraph,
    collectBundleResourceRefs,
    isWorkflowBundleExport,
    parseWorkflowBundleImport,
    planBundleImport,
    remapGraphIds,
    resolveImportedName,
    serializeWorkflowBundleExport,
    slugifyWorkflowBundleExportBasename,
} from './workflowBundleImportExport';

const PERSONA_A = '11111111-1111-4111-8111-111111111111';
const STRUCT_B = '22222222-2222-4222-8222-222222222222';
const DOC_C = '33333333-3333-4333-8333-333333333333';
const CHILD_WF = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const ROOT_WF = 'ffffffff-ffff-4fff-8fff-ffffffffffff';

function minimalWf(id: string, name: string, graph: WorkflowDefinition['graph']): WorkflowDefinition {
    return {
        id,
        user_id: '00000000-0000-4000-8000-000000000001',
        name,
        description: null,
        palette_id: null,
        graph,
    };
}

describe('workflowBundleImportExport', () => {
    it('collectBundleResourceRefs finds skill and primitive refs', () => {
        const refs = collectBundleResourceRefs([
            {
                nodes: [
                    {
                        id: 'llm',
                        kind: 'skill',
                        skill_type: 'simple_llm_call',
                        label: 'LLM',
                        data: { persona_id: PERSONA_A, structure_id: STRUCT_B, required_inputs: [] },
                        position: { x: 0, y: 0 },
                    },
                    {
                        id: 'doc',
                        kind: 'primitive',
                        primitive_type: 'document',
                        label: 'Doc',
                        data: { document_id: DOC_C },
                        position: { x: 0, y: 0 },
                    },
                    {
                        id: 'img',
                        kind: 'primitive',
                        primitive_type: 'image',
                        label: 'Img',
                        data: { artifact_id: '44444444-4444-4444-8444-444444444444' },
                        position: { x: 0, y: 0 },
                    },
                ],
                edges: [],
            },
        ]);
        expect(refs.personaIds).toEqual([PERSONA_A]);
        expect(refs.structureIds).toEqual([STRUCT_B]);
        expect(refs.documentIds).toEqual([DOC_C]);
        expect(refs.binaryRefs.artifactIds).toHaveLength(1);
    });

    it('buildWorkflowBundleClosure dedupes shared nested workflow', async () => {
        const child = minimalWf(CHILD_WF, 'Child', {
            nodes: [
                { id: 'a', kind: 'start', label: 'Start', data: { required_inputs: [] }, position: { x: 0, y: 0 } },
                { id: 'b', kind: 'stop', label: 'Stop', data: { required_outputs: [{ key: 'output', type: 'string' }] }, position: { x: 0, y: 0 } },
            ],
            edges: [{ source: 'a', target: 'b' }],
        });
        const root = minimalWf(ROOT_WF, 'Root', {
            nodes: [
                { id: 'a', kind: 'start', label: 'Start', data: { required_inputs: [] }, position: { x: 0, y: 0 } },
                { id: 'w1', kind: 'workflow', label: 'W1', data: { workflow_id: CHILD_WF }, position: { x: 0, y: 0 } },
                { id: 'w2', kind: 'workflow', label: 'W2', data: { workflow_id: CHILD_WF }, position: { x: 0, y: 0 } },
                { id: 'b', kind: 'stop', label: 'Stop', data: { required_outputs: [{ key: 'output', type: 'string' }] }, position: { x: 0, y: 0 } },
            ],
            edges: [],
        });
        const fetches: string[] = [];
        const closure = await buildWorkflowBundleClosure(root, async id => {
            fetches.push(id);
            if (id === CHILD_WF) return child;
            throw new Error('missing');
        });
        expect(fetches).toEqual([CHILD_WF]);
        expect(closure.nestedById.size).toBe(1);
    });

    it('buildWorkflowBundleClosure throws on missing nested workflow', async () => {
        const root = minimalWf(ROOT_WF, 'Root', {
            nodes: [
                { id: 'w', kind: 'workflow', label: 'W', data: { workflow_id: CHILD_WF }, position: { x: 0, y: 0 } },
            ],
            edges: [],
        });
        await expect(
            buildWorkflowBundleClosure(root, async () => {
                throw new Error('404');
            }),
        ).rejects.toThrow(WorkflowBundleExportError);
    });

    it('buildWorkflowBundleExportDocument includes warnings for binary refs', () => {
        const root = minimalWf(ROOT_WF, 'Root', {
            nodes: [
                {
                    id: 't',
                    kind: 'skill',
                    skill_type: 'text_to_speech',
                    label: 'TTS',
                    data: {
                        tts_model_id: null,
                        voice_sample_id: '55555555-5555-4555-8555-555555555555',
                        required_inputs: [],
                    },
                    position: { x: 0, y: 0 },
                },
            ],
            edges: [],
        });
        const doc = buildWorkflowBundleExportDocument(
            { root, nestedById: new Map() },
            { personas: new Map(), structures: new Map(), documents: new Map(), palettes: new Map() },
        );
        expect(doc.export_warnings?.length).toBeGreaterThan(0);
    });

    it('remapGraphIds replaces known ids', () => {
        const graph = {
            nodes: [
                {
                    id: 'w',
                    kind: 'workflow',
                    label: 'W',
                    data: { workflow_id: CHILD_WF, persona_id: PERSONA_A },
                    position: { x: 0, y: 0 },
                },
            ],
            edges: [],
        };
        const remapped = remapGraphIds(graph as import('../api/types').WorkflowGraph, {
            workflow: new Map([[CHILD_WF, '99999999-9999-4999-8999-999999999999']]),
            persona: new Map([[PERSONA_A, '88888888-8888-4888-8888-888888888888']]),
            structure: new Map(),
            document: new Map(),
            palette: new Map(),
        });
        const data = (remapped.nodes[0] as { data: Record<string, string> }).data;
        expect(data.workflow_id).toBe('99999999-9999-4999-8999-999999999999');
        expect(data.persona_id).toBe('88888888-8888-4888-8888-888888888888');
    });

    it('parseWorkflowBundleImport and serialize round-trip', () => {
        const bundle = {
            kind: WORKFLOW_BUNDLE_EXPORT_KIND,
            schema_version: 1,
            exported_at: '2026-01-01T00:00:00.000Z',
            definition: {
                name: 'Root',
                description: null,
                graph: {
                    nodes: [
                        { id: 'a', kind: 'start', label: 'Start', data: { required_inputs: [] }, position: { x: 0, y: 0 } },
                        { id: 'b', kind: 'stop', label: 'Stop', data: { required_outputs: [{ key: 'output', type: 'string' }] }, position: { x: 0, y: 0 } },
                    ],
                    edges: [{ source: 'a', target: 'b' }],
                },
            },
            included_workflows: [],
        };
        const json = serializeWorkflowBundleExport(bundle as ReturnType<typeof parseWorkflowBundleImport>);
        const parsed = parseWorkflowBundleImport(json);
        expect(parsed.definition.name).toBe('Root');
        expect(isWorkflowBundleExport(parsed)).toBe(true);
    });

    it('planBundleImport suffixes root name and clears workflow refs on nested create', () => {
        const bundle = parseWorkflowBundleImport({
            kind: WORKFLOW_BUNDLE_EXPORT_KIND,
            schema_version: 1,
            exported_at: '2026-01-01T00:00:00.000Z',
            definition: {
                name: 'My Flow',
                description: null,
                graph: {
                    nodes: [
                        { id: 'w', kind: 'workflow', label: 'W', data: { workflow_id: CHILD_WF }, position: { x: 0, y: 0 } },
                    ],
                    edges: [],
                },
            },
            included_workflows: [
                {
                    source_definition_id: CHILD_WF,
                    definition: {
                        name: 'Child',
                        description: null,
                        graph: { nodes: [], edges: [] },
                    },
                },
            ],
        });
        const plan = planBundleImport(bundle, { workflows: ['My Flow (imported)'] });
        expect(plan.root.importName).toBe('My Flow (imported) (2)');
        expect(plan.root.create.graph?.nodes[0]).toMatchObject({
            data: { workflow_id: '' },
        });
    });

    it('resolveImportedName handles collisions', () => {
        const existing = new Set(['alpha (imported)']);
        expect(resolveImportedName('Alpha', existing)).toBe('Alpha (imported) (2)');
    });

    it('clearWorkflowRefsInGraph clears workflow nodes only', () => {
        const g = clearWorkflowRefsInGraph({
            nodes: [
                { id: 'w', kind: 'workflow', label: 'W', data: { workflow_id: CHILD_WF }, position: { x: 0, y: 0 } },
                { id: 's', kind: 'start', label: 'Start', data: {}, position: { x: 0, y: 0 } },
            ],
            edges: [],
        });
        expect((g.nodes[0] as { data: { workflow_id: string } }).data.workflow_id).toBe('');
    });

    it('applyBundleIdMapsToDefinition remaps palette_id', () => {
        const PAL_OLD = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
        const PAL_NEW = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
        const out = applyBundleIdMapsToDefinition(
            {
                name: 'X',
                description: null,
                graph: { nodes: [], edges: [] },
                palette_id: PAL_OLD,
            },
            {
                workflow: new Map(),
                persona: new Map(),
                structure: new Map(),
                document: new Map(),
                palette: new Map([[PAL_OLD, PAL_NEW]]),
            },
        );
        expect(out.palette_id).toBe(PAL_NEW);
    });

    it('slugifyWorkflowBundleExportBasename adds bundle suffix', () => {
        expect(slugifyWorkflowBundleExportBasename('Hello World')).toBe('hello-world-bundle');
    });
});
