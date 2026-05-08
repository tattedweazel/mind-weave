import { describe, it, expect } from 'vitest';
import type { WorkflowDefinition } from '../api/types';
import {
    WORKFLOW_EXPORT_KIND,
    buildWorkflowExportDocument,
    collectWorkflowRefIds,
    parseWorkflowImport,
    serializeWorkflowExport,
    slugifyWorkflowExportBasename,
    WorkflowImportError,
} from './workflowImportExport';

describe('workflowImportExport', () => {
    const minimalWf: WorkflowDefinition = {
        id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        user_id: '11111111-2222-3333-4444-555555555555',
        name: 'Test Flow',
        description: 'Desc',
        palette_id: null,
        graph: {
            schema_version: 1,
            nodes: [
                {
                    id: 'a',
                    kind: 'start',
                    label: 'Start',
                    data: { required_inputs: [] },
                    position: { x: 0, y: 0 },
                },
                {
                    id: 'b',
                    kind: 'stop',
                    label: 'Stop',
                    data: { required_outputs: [{ key: 'output', type: 'string' }] },
                    position: { x: 100, y: 0 },
                },
            ],
            edges: [{ source: 'a', target: 'b' }],
        },
    };

    it('buildWorkflowExportDocument wraps definition and kind', () => {
        const doc = buildWorkflowExportDocument(minimalWf);
        expect(doc.kind).toBe(WORKFLOW_EXPORT_KIND);
        expect(doc.schema_version).toBe(1);
        expect(doc.source_definition_id).toBe(minimalWf.id);
        expect(doc.definition.name).toBe('Test Flow');
        expect(doc.definition.graph.nodes).toHaveLength(2);
    });

    it('serialize + parse round-trip yields create payload', () => {
        const json = serializeWorkflowExport(minimalWf);
        const create = parseWorkflowImport(json);
        expect(create.name).toBe('Test Flow');
        expect(create.description).toBe('Desc');
        expect(create.graph).toBeDefined();
        expect(create.graph!.nodes).toHaveLength(2);
        expect(create.graph!.edges).toHaveLength(1);
        expect((create as unknown as Record<string, unknown>).id).toBeUndefined();
    });

    it('parseWorkflowImport accepts legacy name + graph', () => {
        const create = parseWorkflowImport({
            name: ' Legacy ',
            graph: { nodes: [], edges: [] },
        });
        expect(create.name).toBe('Legacy');
        expect(create.graph).toBeDefined();
        expect(create.graph!.nodes).toEqual([]);
        expect(create.graph!.edges).toEqual([]);
    });

    it('parseWorkflowImport accepts API GET-shaped object and ignores id conceptually', () => {
        const create = parseWorkflowImport({
            id: 'old-id',
            name: 'API',
            description: null,
            graph: { nodes: [], edges: [], schema_version: 1 },
        });
        expect(create.name).toBe('API');
        expect((create as { id?: string }).id).toBeUndefined();
    });

    it('collectWorkflowRefIds finds workflow nodes', () => {
        const ids = collectWorkflowRefIds({
            nodes: [
                { id: 'w', kind: 'workflow', label: 'Sub', data: { workflow_id: 'uuid-one' }, position: { x: 0, y: 0 } },
                { id: 'w2', kind: 'workflow', label: 'Sub2', data: { workflow_id: 'uuid-one' }, position: { x: 0, y: 0 } },
            ],
            edges: [],
        });
        expect(ids).toEqual(['uuid-one']);
    });

    it('slugifyWorkflowExportBasename sanitizes name', () => {
        expect(slugifyWorkflowExportBasename('Hello World!')).toBe('hello-world');
        expect(slugifyWorkflowExportBasename('!!!')).toBe('workflow');
    });

    it('parseWorkflowImport throws on invalid graph', () => {
        expect(() => parseWorkflowImport({ name: 'x', graph: { nodes: 'bad', edges: [] } })).toThrow(WorkflowImportError);
        expect(() => parseWorkflowImport({ name: 'x', graph: { nodes: [], edges: {} } })).toThrow(WorkflowImportError);
    });

    it('parseWorkflowImport throws on bad JSON string', () => {
        expect(() => parseWorkflowImport('not json')).toThrow(WorkflowImportError);
    });
});
