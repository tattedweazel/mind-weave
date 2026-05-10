/**
 * Workflow definition JSON import/export (Build tab).
 * Shape is versioned; mirrors persisted API graph + metadata.
 */

import type {
    GraphNode,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowExecutionLimitsOverrides,
    WorkflowGraph,
} from '../api/types';

export const WORKFLOW_EXPORT_KIND = 'mind_weave_workflow_export' as const;
export const WORKFLOW_EXPORT_SCHEMA_VERSION = 1 as const;

export class WorkflowImportError extends Error {
    override readonly name = 'WorkflowImportError';
    constructor(message: string) {
        super(message);
    }
}

export type WorkflowExportDocument = {
    kind: typeof WORKFLOW_EXPORT_KIND;
    schema_version: typeof WORKFLOW_EXPORT_SCHEMA_VERSION;
    exported_at: string;
    /** Optional: original row id for human reference only; import ignores it. */
    source_definition_id?: string;
    definition: {
        name: string;
        description: string | null;
        graph: WorkflowGraph;
        /** Omitted on import when creating a new workflow unless caller validates palette. */
        palette_id?: string | null;
    };
};

function isRecord(x: unknown): x is Record<string, unknown> {
    return typeof x === 'object' && x !== null && !Array.isArray(x);
}

function ensureGraph(raw: unknown): WorkflowGraph {
    if (!isRecord(raw)) {
        throw new WorkflowImportError('Invalid graph: expected an object.');
    }
    const nodes = raw.nodes;
    const edges = raw.edges;
    if (!Array.isArray(nodes)) {
        throw new WorkflowImportError('Invalid graph: nodes must be an array.');
    }
    if (!Array.isArray(edges)) {
        throw new WorkflowImportError('Invalid graph: edges must be an array.');
    }
    const sv = raw.schema_version;
    const graph: WorkflowGraph = {
        nodes: nodes as GraphNode[],
        edges: edges as WorkflowGraph['edges'],
    };
    if (sv !== undefined && sv !== null) {
        if (typeof sv !== 'number' || !Number.isFinite(sv)) {
            throw new WorkflowImportError('Invalid graph: schema_version must be a number when present.');
        }
        graph.schema_version = sv;
    }
    const limitsRaw = raw.execution_limits;
    if (limitsRaw !== undefined && limitsRaw !== null) {
        if (!isRecord(limitsRaw)) {
            throw new WorkflowImportError('Invalid graph: execution_limits must be a JSON object when present.');
        }
        graph.execution_limits = limitsRaw as WorkflowExecutionLimitsOverrides;
    }
    return graph;
}

/**
 * Build a versioned export document from the current workflow (API shape).
 */
export function buildWorkflowExportDocument(wf: WorkflowDefinition): WorkflowExportDocument {
    return {
        kind: WORKFLOW_EXPORT_KIND,
        schema_version: WORKFLOW_EXPORT_SCHEMA_VERSION,
        exported_at: new Date().toISOString(),
        source_definition_id: wf.id,
        definition: {
            name: wf.name,
            description: wf.description ?? null,
            graph: {
                nodes: wf.graph.nodes,
                edges: wf.graph.edges,
                schema_version: wf.graph.schema_version ?? undefined,
                ...(wf.graph.execution_limits != null &&
                typeof wf.graph.execution_limits === 'object' &&
                Object.keys(wf.graph.execution_limits).length > 0
                    ? { execution_limits: wf.graph.execution_limits }
                    : {}),
            },
            palette_id: wf.palette_id ?? null,
        },
    };
}

export function serializeWorkflowExport(wf: WorkflowDefinition): string {
    return JSON.stringify(buildWorkflowExportDocument(wf), null, 2);
}

/** Safe filename segment for downloads (no path separators). */
export function slugifyWorkflowExportBasename(name: string): string {
    const s = name
        .trim()
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    return s || 'workflow';
}

/**
 * Collect nested workflow reference UUIDs from graph nodes (`kind: workflow`).
 */
export function collectWorkflowRefIds(graph: WorkflowGraph): string[] {
    const ids: string[] = [];
    for (const n of graph.nodes) {
        const node = n as { kind?: string; data?: { workflow_id?: string } };
        if (node.kind === 'workflow') {
            const wid = node.data?.workflow_id;
            if (typeof wid === 'string' && wid.trim() !== '') {
                ids.push(wid.trim());
            }
        }
    }
    return [...new Set(ids)];
}

/**
 * Parse JSON into a create payload. Always returns a new-definition payload (no id).
 * - Supports wrapped `mind_weave_workflow_export` v1.
 * - Supports legacy `{ name, graph }` or `{ name, description?, graph }`.
 * - Supports API GET shape `{ id, name, graph, ... }` (id ignored).
 */
export function parseWorkflowImport(raw: unknown): WorkflowDefinitionCreate {
    if (typeof raw === 'string') {
        let parsed: unknown;
        try {
            parsed = JSON.parse(raw) as unknown;
        } catch {
            throw new WorkflowImportError('Invalid JSON: could not parse.');
        }
        return parseWorkflowImport(parsed);
    }

    if (!isRecord(raw)) {
        throw new WorkflowImportError('Invalid JSON: expected an object.');
    }

    let name: string | undefined;
    let description: string | null | undefined;
    let graph: WorkflowGraph | undefined;
    let palette_id: string | null | undefined;

    if (raw.kind === WORKFLOW_EXPORT_KIND) {
        const ver = raw.schema_version;
        if (ver !== undefined && ver !== WORKFLOW_EXPORT_SCHEMA_VERSION) {
            throw new WorkflowImportError(
                `Unsupported workflow export schema_version: ${String(ver)} (expected ${WORKFLOW_EXPORT_SCHEMA_VERSION}).`,
            );
        }
        const def = raw.definition;
        if (!isRecord(def)) {
            throw new WorkflowImportError('Invalid export: definition is missing or not an object.');
        }
        const n = def.name;
        if (typeof n !== 'string' || !n.trim()) {
            throw new WorkflowImportError('Invalid export: definition.name is required.');
        }
        name = n.trim();
        if (def.description !== undefined && def.description !== null) {
            description = typeof def.description === 'string' ? def.description : null;
        } else {
            description = null;
        }
        graph = ensureGraph(def.graph);
        if (def.palette_id !== undefined) {
            palette_id = def.palette_id === null || def.palette_id === '' ? null : String(def.palette_id);
        }
    } else {
        // Legacy: same fields as API row
        const n = raw.name;
        if (typeof n !== 'string' || !n.trim()) {
            throw new WorkflowImportError('Invalid workflow JSON: name is required.');
        }
        name = n.trim();
        if (raw.description !== undefined && raw.description !== null) {
            description = typeof raw.description === 'string' ? raw.description : null;
        } else {
            description = null;
        }
        if (raw.graph === undefined) {
            throw new WorkflowImportError('Invalid workflow JSON: graph is required.');
        }
        graph = ensureGraph(raw.graph);
        if (raw.palette_id !== undefined) {
            palette_id = raw.palette_id === null || raw.palette_id === '' ? null : String(raw.palette_id);
        }
    }

    const create: WorkflowDefinitionCreate = {
        name: name!,
        description: description ?? null,
        graph: graph!,
    };
    if (palette_id !== undefined) {
        create.palette_id = palette_id;
    }
    return create;
}

export function readWorkflowImportFile(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            resolve(typeof reader.result === 'string' ? reader.result : '');
        };
        reader.onerror = () => reject(new Error('Failed to read file.'));
        reader.readAsText(file);
    });
}
