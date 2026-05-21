/**
 * Workflow bundle export/import: root workflow + transitive nested workflows
 * and referenced personas, structures, documents, palettes.
 */

import type {
    Document,
    DocumentCreate,
    GraphNode,
    Palette,
    Persona,
    PersonaCreate,
    Structure,
    StructureCreate,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowGraph,
} from '../api/types';
import { expandWorkflowPaletteColorsForExport } from './paletteDefaults';
import {
    WorkflowImportError,
    collectWorkflowRefIds,
    slugifyWorkflowExportBasename,
} from './workflowImportExport';

export const WORKFLOW_BUNDLE_EXPORT_KIND = 'mind_weave_workflow_bundle_export' as const;
export const WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION = 1 as const;

export { slugifyWorkflowExportBasename };

export class WorkflowBundleExportError extends Error {
    override readonly name = 'WorkflowBundleExportError';
    constructor(
        message: string,
        /** Nested workflow source ids that could not be loaded. */
        public readonly missingWorkflowIds: string[] = [],
    ) {
        super(message);
    }
}

export type BundleDefinitionPayload = {
    name: string;
    description: string | null;
    graph: WorkflowGraph;
    palette_id?: string | null;
    /** Set at export when palette_id refers to a built-in palette (resolved by slug on import). */
    palette_slug?: string | null;
};

export type BundleIncludedWorkflow = {
    source_definition_id: string;
    expose_as_custom_skill?: boolean;
    definition: BundleDefinitionPayload;
};

export type BundlePersonaExport = PersonaCreate & { source_id: string };

export type BundleStructureExport = StructureCreate & { source_id: string };

export type BundleDocumentExport = DocumentCreate & { source_id: string };

export type BundlePaletteExport = {
    source_id: string;
    name: string;
    colors: Record<string, string>;
    slug?: string | null;
};

export type WorkflowBundleExportDocument = {
    kind: typeof WORKFLOW_BUNDLE_EXPORT_KIND;
    schema_version: typeof WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION;
    exported_at: string;
    root_source_definition_id?: string;
    definition: BundleDefinitionPayload;
    included_workflows: BundleIncludedWorkflow[];
    personas?: BundlePersonaExport[];
    structures?: BundleStructureExport[];
    documents?: BundleDocumentExport[];
    palettes?: BundlePaletteExport[];
    export_warnings?: string[];
};

export type BundleResourceRefs = {
    workflowIds: string[];
    personaIds: string[];
    structureIds: string[];
    documentIds: string[];
    paletteIds: string[];
    binaryRefs: {
        artifactIds: string[];
        voiceSampleIds: string[];
        audioArtifactIds: string[];
    };
};

export type BundleIdMaps = {
    workflow: Map<string, string>;
    persona: Map<string, string>;
    structure: Map<string, string>;
    document: Map<string, string>;
    palette: Map<string, string>;
};

export type BundleImportPlan = {
    palettes: Array<{ source_id: string; create: { name: string; colors: Record<string, string> }; slug?: string | null }>;
    personas: Array<{ source_id: string; create: PersonaCreate; importName: string }>;
    structures: Array<{ source_id: string; create: StructureCreate; importName: string }>;
    documents: Array<{ source_id: string; create: DocumentCreate; importName: string }>;
    includedWorkflows: Array<{
        source_definition_id: string;
        expose_as_custom_skill?: boolean;
        importName: string;
        create: WorkflowDefinitionCreate;
    }>;
    root: {
        importName: string;
        create: WorkflowDefinitionCreate;
    };
    importWarnings: string[];
};

const UUID_RE =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const REMAP_ID_KEYS = [
    'workflow_id',
    'persona_id',
    'structure_id',
    'document_id',
    'existing_document_id',
    'palette_id',
] as const;

function isRecord(x: unknown): x is Record<string, unknown> {
    return typeof x === 'object' && x !== null && !Array.isArray(x);
}

function normalizeUuid(raw: unknown): string | null {
    if (typeof raw !== 'string') return null;
    const s = raw.trim();
    return UUID_RE.test(s) ? s : null;
}

function uniqueStrings(ids: string[]): string[] {
    return [...new Set(ids)];
}

function emptyRefs(): BundleResourceRefs {
    return {
        workflowIds: [],
        personaIds: [],
        structureIds: [],
        documentIds: [],
        paletteIds: [],
        binaryRefs: {
            artifactIds: [],
            voiceSampleIds: [],
            audioArtifactIds: [],
        },
    };
}

function definitionPayloadFromWorkflow(wf: WorkflowDefinition): BundleDefinitionPayload {
    return {
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
    };
}

function scanNodeDataForRefs(data: unknown, refs: BundleResourceRefs): void {
    if (!isRecord(data)) return;
    const w = normalizeUuid(data.workflow_id);
    if (w) refs.workflowIds.push(w);
    const p = normalizeUuid(data.persona_id);
    if (p) refs.personaIds.push(p);
    const st = normalizeUuid(data.structure_id);
    if (st) refs.structureIds.push(st);
    const d = normalizeUuid(data.document_id);
    if (d) refs.documentIds.push(d);
    const ed = normalizeUuid(data.existing_document_id);
    if (ed) refs.documentIds.push(ed);
    const a = normalizeUuid(data.artifact_id);
    if (a) refs.binaryRefs.artifactIds.push(a);
    const v = normalizeUuid(data.voice_sample_id);
    if (v) refs.binaryRefs.voiceSampleIds.push(v);
    const au = normalizeUuid(data.audio_artifact_id);
    if (au) refs.binaryRefs.audioArtifactIds.push(au);
}

/**
 * Collect resource UUIDs referenced from workflow graphs (not palette_id on definitions).
 */
export function collectBundleResourceRefs(graphs: WorkflowGraph[]): BundleResourceRefs {
    const refs = emptyRefs();
    for (const graph of graphs) {
        for (const wid of collectWorkflowRefIds(graph)) {
            refs.workflowIds.push(wid);
        }
        for (const n of graph.nodes) {
            scanNodeDataForRefs((n as GraphNode).data, refs);
        }
    }
    return {
        workflowIds: uniqueStrings(refs.workflowIds),
        personaIds: uniqueStrings(refs.personaIds),
        structureIds: uniqueStrings(refs.structureIds),
        documentIds: uniqueStrings(refs.documentIds),
        paletteIds: uniqueStrings(refs.paletteIds),
        binaryRefs: {
            artifactIds: uniqueStrings(refs.binaryRefs.artifactIds),
            voiceSampleIds: uniqueStrings(refs.binaryRefs.voiceSampleIds),
            audioArtifactIds: uniqueStrings(refs.binaryRefs.audioArtifactIds),
        },
    };
}

export function collectBundlePaletteIds(definitions: BundleDefinitionPayload[]): string[] {
    const ids: string[] = [];
    for (const d of definitions) {
        const pid = normalizeUuid(d.palette_id);
        if (pid) ids.push(pid);
    }
    return uniqueStrings(ids);
}

function buildBinaryExportWarnings(refs: BundleResourceRefs): string[] {
    const warnings: string[] = [];
    const { artifactIds, voiceSampleIds, audioArtifactIds } = refs.binaryRefs;
    if (artifactIds.length > 0) {
        warnings.push(
            `Image/url snapshot artifact_id(s) not embedded (${artifactIds.length} ref(s)); re-upload or re-wire after import.`,
        );
    }
    if (voiceSampleIds.length > 0) {
        warnings.push(
            `voice_sample_id(s) not embedded (${voiceSampleIds.length} ref(s)); re-select voice samples after import.`,
        );
    }
    if (audioArtifactIds.length > 0) {
        warnings.push(
            `audio_artifact_id(s) not embedded (${audioArtifactIds.length} ref(s)); re-upload audio files after import.`,
        );
    }
    return warnings;
}

export type WorkflowBundleClosure = {
    root: WorkflowDefinition;
    nestedById: Map<string, WorkflowDefinition>;
};

/**
 * BFS transitive nested workflow closure. Throws if any nested workflow cannot be fetched.
 */
export async function buildWorkflowBundleClosure(
    root: WorkflowDefinition,
    fetchWorkflow: (id: string) => Promise<WorkflowDefinition>,
): Promise<WorkflowBundleClosure> {
    const nestedById = new Map<string, WorkflowDefinition>();
    const queue = collectWorkflowRefIds(root.graph).filter(id => id !== root.id);
    const missing: string[] = [];

    while (queue.length > 0) {
        const id = queue.shift()!;
        if (id === root.id || nestedById.has(id)) continue;
        let wf: WorkflowDefinition;
        try {
            wf = await fetchWorkflow(id);
        } catch {
            missing.push(id);
            continue;
        }
        nestedById.set(id, wf);
        for (const childId of collectWorkflowRefIds(wf.graph)) {
            if (childId !== root.id && !nestedById.has(childId) && !queue.includes(childId)) {
                queue.push(childId);
            }
        }
    }

    if (missing.length > 0) {
        throw new WorkflowBundleExportError(
            `Cannot export bundle: missing nested workflow(s): ${missing.join(', ')}`,
            uniqueStrings(missing),
        );
    }

    return { root, nestedById };
}

export type WorkflowBundleExportDeps = {
    personas: Map<string, BundlePersonaExport>;
    structures: Map<string, BundleStructureExport>;
    documents: Map<string, BundleDocumentExport>;
    palettes: Map<string, BundlePaletteExport>;
};

export function buildWorkflowBundleExportDocument(
    closure: WorkflowBundleClosure,
    deps: WorkflowBundleExportDeps,
): WorkflowBundleExportDocument {
    const { root, nestedById } = closure;
    const allGraphs = [root.graph, ...[...nestedById.values()].map(w => w.graph)];
    const refs = collectBundleResourceRefs(allGraphs);
    const paletteIds = collectBundlePaletteIds([
        definitionPayloadFromWorkflow(root),
        ...[...nestedById.values()].map(definitionPayloadFromWorkflow),
    ]);
    refs.paletteIds = paletteIds;

    const export_warnings = buildBinaryExportWarnings(refs);

    const included_workflows: BundleIncludedWorkflow[] = [...nestedById.entries()].map(([source_definition_id, wf]) => ({
        source_definition_id,
        ...(wf.expose_as_custom_skill ? { expose_as_custom_skill: true } : {}),
        definition: definitionPayloadFromWorkflow(wf),
    }));

    const doc: WorkflowBundleExportDocument = {
        kind: WORKFLOW_BUNDLE_EXPORT_KIND,
        schema_version: WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION,
        exported_at: new Date().toISOString(),
        root_source_definition_id: root.id,
        definition: definitionPayloadFromWorkflow(root),
        included_workflows,
    };

    if (deps.personas.size > 0) {
        doc.personas = [...deps.personas.values()];
    }
    if (deps.structures.size > 0) {
        doc.structures = [...deps.structures.values()];
    }
    if (deps.documents.size > 0) {
        doc.documents = [...deps.documents.values()];
    }
    if (deps.palettes.size > 0) {
        doc.palettes = [...deps.palettes.values()];
    }
    if (export_warnings.length > 0) {
        doc.export_warnings = export_warnings;
    }

    return doc;
}

export function serializeWorkflowBundleExport(doc: WorkflowBundleExportDocument): string {
    return JSON.stringify(doc, null, 2);
}

export function slugifyWorkflowBundleExportBasename(name: string): string {
    return `${slugifyWorkflowExportBasename(name)}-bundle`;
}

export function isWorkflowBundleExport(raw: unknown): boolean {
    return isRecord(raw) && raw.kind === WORKFLOW_BUNDLE_EXPORT_KIND;
}

function ensureGraphFromBundle(raw: unknown): WorkflowGraph {
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
    const graph: WorkflowGraph = {
        nodes: nodes as GraphNode[],
        edges: edges as WorkflowGraph['edges'],
    };
    if (raw.schema_version !== undefined && raw.schema_version !== null) {
        if (typeof raw.schema_version !== 'number' || !Number.isFinite(raw.schema_version)) {
            throw new WorkflowImportError('Invalid graph: schema_version must be a number when present.');
        }
        graph.schema_version = raw.schema_version;
    }
    if (raw.execution_limits !== undefined && raw.execution_limits !== null) {
        if (!isRecord(raw.execution_limits)) {
            throw new WorkflowImportError('Invalid graph: execution_limits must be a JSON object when present.');
        }
        graph.execution_limits = raw.execution_limits as WorkflowGraph['execution_limits'];
    }
    return graph;
}

function parseDefinitionPayload(raw: unknown, label: string): BundleDefinitionPayload {
    if (!isRecord(raw)) {
        throw new WorkflowImportError(`Invalid bundle: ${label} is missing or not an object.`);
    }
    const n = raw.name;
    if (typeof n !== 'string' || !n.trim()) {
        throw new WorkflowImportError(`Invalid bundle: ${label}.name is required.`);
    }
    let description: string | null = null;
    if (raw.description !== undefined && raw.description !== null) {
        description = typeof raw.description === 'string' ? raw.description : null;
    }
    const graph = ensureGraphFromBundle(raw.graph);
    let palette_id: string | null | undefined;
    if (raw.palette_id !== undefined) {
        palette_id = raw.palette_id === null || raw.palette_id === '' ? null : String(raw.palette_id);
    }
    let palette_slug: string | null | undefined;
    if (raw.palette_slug !== undefined && raw.palette_slug !== null && raw.palette_slug !== '') {
        palette_slug = String(raw.palette_slug);
    }
    return {
        name: n.trim(),
        description,
        graph,
        ...(palette_id !== undefined ? { palette_id } : {}),
        ...(palette_slug !== undefined ? { palette_slug } : {}),
    };
}

export function parseWorkflowBundleImport(raw: unknown): WorkflowBundleExportDocument {
    if (typeof raw === 'string') {
        let parsed: unknown;
        try {
            parsed = JSON.parse(raw) as unknown;
        } catch {
            throw new WorkflowImportError('Invalid JSON: could not parse.');
        }
        return parseWorkflowBundleImport(parsed);
    }

    if (!isRecord(raw)) {
        throw new WorkflowImportError('Invalid JSON: expected an object.');
    }
    if (raw.kind !== WORKFLOW_BUNDLE_EXPORT_KIND) {
        throw new WorkflowImportError(
            `Invalid bundle: expected kind "${WORKFLOW_BUNDLE_EXPORT_KIND}", got ${String(raw.kind)}.`,
        );
    }
    const ver = raw.schema_version;
    if (ver !== undefined && ver !== WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION) {
        throw new WorkflowImportError(
            `Unsupported bundle schema_version: ${String(ver)} (expected ${WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION}).`,
        );
    }

    const definition = parseDefinitionPayload(raw.definition, 'definition');
    const includedRaw = raw.included_workflows;
    const included_workflows: BundleIncludedWorkflow[] = [];
    if (includedRaw !== undefined) {
        if (!Array.isArray(includedRaw)) {
            throw new WorkflowImportError('Invalid bundle: included_workflows must be an array.');
        }
        for (let i = 0; i < includedRaw.length; i++) {
            const row = includedRaw[i];
            if (!isRecord(row)) {
                throw new WorkflowImportError(`Invalid bundle: included_workflows[${i}] must be an object.`);
            }
            const sid = row.source_definition_id;
            if (typeof sid !== 'string' || !normalizeUuid(sid)) {
                throw new WorkflowImportError(`Invalid bundle: included_workflows[${i}].source_definition_id must be a UUID.`);
            }
            const item: BundleIncludedWorkflow = {
                source_definition_id: sid.trim(),
                definition: parseDefinitionPayload(row.definition, `included_workflows[${i}].definition`),
            };
            if (row.expose_as_custom_skill === true) {
                item.expose_as_custom_skill = true;
            }
            included_workflows.push(item);
        }
    }

    const doc: WorkflowBundleExportDocument = {
        kind: WORKFLOW_BUNDLE_EXPORT_KIND,
        schema_version: WORKFLOW_BUNDLE_EXPORT_SCHEMA_VERSION,
        exported_at: typeof raw.exported_at === 'string' ? raw.exported_at : new Date().toISOString(),
        definition,
        included_workflows,
    };
    if (typeof raw.root_source_definition_id === 'string') {
        doc.root_source_definition_id = raw.root_source_definition_id;
    }

    const parsePersonas = (): void => {
        const arr = raw.personas;
        if (arr === undefined) return;
        if (!Array.isArray(arr)) throw new WorkflowImportError('Invalid bundle: personas must be an array.');
        doc.personas = arr.map((row, i) => {
            if (!isRecord(row)) throw new WorkflowImportError(`Invalid bundle: personas[${i}] must be an object.`);
            const source_id = normalizeUuid(row.source_id);
            if (!source_id) throw new WorkflowImportError(`Invalid bundle: personas[${i}].source_id must be a UUID.`);
            const name = row.name;
            if (typeof name !== 'string' || !name.trim()) {
                throw new WorkflowImportError(`Invalid bundle: personas[${i}].name is required.`);
            }
            const description = typeof row.description === 'string' ? row.description : '';
            const system_prompt = typeof row.system_prompt === 'string' ? row.system_prompt : '';
            const create: BundlePersonaExport = {
                source_id,
                name: name.trim(),
                description,
                system_prompt,
                type: row.type === 'system' ? 'system' : 'custom',
            };
            if (row.default_model !== undefined && row.default_model !== null) {
                create.default_model = String(row.default_model);
            }
            if (row.is_default === true) create.is_default = true;
            if (typeof row.creativity === 'number') create.creativity = row.creativity;
            if (row.suppress_lm_thinking === true) create.suppress_lm_thinking = true;
            return create;
        });
    };

    const parseStructures = (): void => {
        const arr = raw.structures;
        if (arr === undefined) return;
        if (!Array.isArray(arr)) throw new WorkflowImportError('Invalid bundle: structures must be an array.');
        doc.structures = arr.map((row, i) => {
            if (!isRecord(row)) throw new WorkflowImportError(`Invalid bundle: structures[${i}] must be an object.`);
            const source_id = normalizeUuid(row.source_id);
            if (!source_id) throw new WorkflowImportError(`Invalid bundle: structures[${i}].source_id must be a UUID.`);
            const name = row.name;
            if (typeof name !== 'string' || !name.trim()) {
                throw new WorkflowImportError(`Invalid bundle: structures[${i}].name is required.`);
            }
            const json_schema = row.json_schema;
            if (typeof json_schema !== 'string' || !json_schema.trim()) {
                throw new WorkflowImportError(`Invalid bundle: structures[${i}].json_schema is required.`);
            }
            return {
                source_id,
                name: name.trim(),
                description: typeof row.description === 'string' ? row.description : '',
                json_schema: json_schema.trim(),
            };
        });
    };

    const parseDocuments = (): void => {
        const arr = raw.documents;
        if (arr === undefined) return;
        if (!Array.isArray(arr)) throw new WorkflowImportError('Invalid bundle: documents must be an array.');
        doc.documents = arr.map((row, i) => {
            if (!isRecord(row)) throw new WorkflowImportError(`Invalid bundle: documents[${i}] must be an object.`);
            const source_id = normalizeUuid(row.source_id);
            if (!source_id) throw new WorkflowImportError(`Invalid bundle: documents[${i}].source_id must be a UUID.`);
            const name = row.name;
            if (typeof name !== 'string' || !name.trim()) {
                throw new WorkflowImportError(`Invalid bundle: documents[${i}].name is required.`);
            }
            return {
                source_id,
                name: name.trim(),
                description: typeof row.description === 'string' ? row.description : '',
                body: typeof row.body === 'string' ? row.body : '',
            };
        });
    };

    const parsePalettes = (): void => {
        const arr = raw.palettes;
        if (arr === undefined) return;
        if (!Array.isArray(arr)) throw new WorkflowImportError('Invalid bundle: palettes must be an array.');
        doc.palettes = arr.map((row, i) => {
            if (!isRecord(row)) throw new WorkflowImportError(`Invalid bundle: palettes[${i}] must be an object.`);
            const source_id = normalizeUuid(row.source_id);
            if (!source_id) throw new WorkflowImportError(`Invalid bundle: palettes[${i}].source_id must be a UUID.`);
            const name = row.name;
            if (typeof name !== 'string' || !name.trim()) {
                throw new WorkflowImportError(`Invalid bundle: palettes[${i}].name is required.`);
            }
            const colorsRaw = row.colors;
            if (!isRecord(colorsRaw)) {
                throw new WorkflowImportError(`Invalid bundle: palettes[${i}].colors must be an object.`);
            }
            const colors: Record<string, string> = {};
            for (const [k, v] of Object.entries(colorsRaw)) {
                if (typeof v === 'string') colors[k] = v;
            }
            const item: BundlePaletteExport = {
                source_id,
                name: name.trim(),
                colors: expandWorkflowPaletteColorsForExport(colors),
            };
            if (row.slug !== undefined && row.slug !== null && row.slug !== '') {
                item.slug = String(row.slug);
            }
            return item;
        });
    };

    parsePersonas();
    parseStructures();
    parseDocuments();
    parsePalettes();

    if (raw.export_warnings !== undefined) {
        if (!Array.isArray(raw.export_warnings)) {
            throw new WorkflowImportError('Invalid bundle: export_warnings must be an array.');
        }
        doc.export_warnings = raw.export_warnings.filter((w): w is string => typeof w === 'string');
    }

    return doc;
}

function remapValueForKey(key: string, value: unknown, maps: BundleIdMaps): unknown {
    if (typeof value !== 'string') return value;
    const id = normalizeUuid(value);
    if (!id) return value;
    if (key === 'workflow_id') {
        return maps.workflow.get(id) ?? value;
    }
    if (key === 'persona_id') {
        return maps.persona.get(id) ?? value;
    }
    if (key === 'structure_id') {
        return maps.structure.get(id) ?? value;
    }
    if (key === 'document_id' || key === 'existing_document_id') {
        return maps.document.get(id) ?? value;
    }
    if (key === 'palette_id') {
        return maps.palette.get(id) ?? value;
    }
    return value;
}

function remapRecordDeep(obj: Record<string, unknown>, maps: BundleIdMaps): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
        if ((REMAP_ID_KEYS as readonly string[]).includes(k)) {
            out[k] = remapValueForKey(k, v, maps);
        } else if (Array.isArray(v)) {
            out[k] = v.map(item =>
                isRecord(item) ? remapRecordDeep(item, maps) : item,
            );
        } else if (isRecord(v)) {
            out[k] = remapRecordDeep(v, maps);
        } else {
            out[k] = v;
        }
    }
    return out;
}

/** Deep-remap workflow_id, persona_id, structure_id, document ids, palette_id in a graph. */
export function remapGraphIds(graph: WorkflowGraph, maps: BundleIdMaps): WorkflowGraph {
    const nodes = graph.nodes.map(n => {
        const node = n as GraphNode;
        if (!isRecord(node.data)) {
            return node;
        }
        return {
            ...node,
            data: remapRecordDeep(node.data as Record<string, unknown>, maps),
        } as GraphNode;
    });
    return { ...graph, nodes };
}

export function clearWorkflowRefsInGraph(graph: WorkflowGraph): WorkflowGraph {
    const nodes = graph.nodes.map(n => {
        const node = n as { kind?: string; data?: Record<string, unknown> };
        if (node.kind !== 'workflow' || !isRecord(node.data)) {
            return n;
        }
        return {
            ...n,
            data: { ...node.data, workflow_id: '' },
        } as GraphNode;
    });
    return { ...graph, nodes };
}

export function resolveImportedName(
    baseName: string,
    existingNames: Set<string>,
    options?: { suffixImported?: boolean },
): string {
    const trimmed = baseName.trim();
    const withSuffix =
        options?.suffixImported !== false && !trimmed.toLowerCase().endsWith(' (imported)')
            ? `${trimmed} (imported)`
            : trimmed;
    if (!existingNames.has(withSuffix.toLowerCase())) {
        return withSuffix;
    }
    let n = 2;
    while (existingNames.has(`${withSuffix} (${n})`.toLowerCase())) {
        n += 1;
    }
    return `${withSuffix} (${n})`;
}

export function planBundleImport(
    bundle: WorkflowBundleExportDocument,
    existingNames: {
        workflows?: string[];
        personas?: string[];
        structures?: string[];
        documents?: string[];
        palettes?: string[];
    },
): BundleImportPlan {
    const wfNames = new Set((existingNames.workflows ?? []).map(s => s.trim().toLowerCase()));
    const personaNames = new Set((existingNames.personas ?? []).map(s => s.trim().toLowerCase()));
    const structureNames = new Set((existingNames.structures ?? []).map(s => s.trim().toLowerCase()));
    const documentNames = new Set((existingNames.documents ?? []).map(s => s.trim().toLowerCase()));
    const paletteNames = new Set((existingNames.palettes ?? []).map(s => s.trim().toLowerCase()));

    const importWarnings: string[] = [...(bundle.export_warnings ?? [])];
    importWarnings.push(
        'Workflows that use Google (Gmail, Calendar, Docs) skills require connecting Google for workflows under My Settings before running.',
    );

    const palettes = (bundle.palettes ?? []).map(p => {
        const importName = resolveImportedName(p.name, paletteNames, { suffixImported: false });
        paletteNames.add(importName.toLowerCase());
        return {
            source_id: p.source_id,
            create: { name: importName, colors: p.colors },
            slug: p.slug ?? null,
        };
    });

    const personas = (bundle.personas ?? []).map(p => {
        const { source_id, ...create } = p;
        const importName = resolveImportedName(create.name, personaNames, { suffixImported: false });
        personaNames.add(importName.toLowerCase());
        return {
            source_id,
            create: { ...create, name: importName },
            importName,
        };
    });

    const structures = (bundle.structures ?? []).map(s => {
        const { source_id, ...create } = s;
        const importName = resolveImportedName(create.name, structureNames, { suffixImported: false });
        structureNames.add(importName.toLowerCase());
        return {
            source_id,
            create: { ...create, name: importName },
            importName,
        };
    });

    const documents = (bundle.documents ?? []).map(d => {
        const { source_id, ...create } = d;
        const importName = resolveImportedName(create.name, documentNames, { suffixImported: false });
        documentNames.add(importName.toLowerCase());
        return {
            source_id,
            create: { ...create, name: importName },
            importName,
        };
    });

    const includedWorkflows = bundle.included_workflows.map(row => {
        const importName = resolveImportedName(row.definition.name, wfNames, { suffixImported: false });
        wfNames.add(importName.toLowerCase());
        const graph = clearWorkflowRefsInGraph(row.definition.graph);
        const create: WorkflowDefinitionCreate = {
            name: importName,
            description: row.definition.description ?? null,
            graph,
            ...(row.expose_as_custom_skill ? { expose_as_custom_skill: true } : {}),
        };
        if (row.definition.palette_id !== undefined) {
            create.palette_id = row.definition.palette_id;
        }
        return {
            source_definition_id: row.source_definition_id,
            expose_as_custom_skill: row.expose_as_custom_skill,
            importName,
            create,
        };
    });

    const rootImportName = resolveImportedName(bundle.definition.name, wfNames);
    wfNames.add(rootImportName.toLowerCase());
    const rootGraph = clearWorkflowRefsInGraph(bundle.definition.graph);
    const rootCreate: WorkflowDefinitionCreate = {
        name: rootImportName,
        description: bundle.definition.description ?? null,
        graph: rootGraph,
    };
    if (bundle.definition.palette_id !== undefined) {
        rootCreate.palette_id = bundle.definition.palette_id;
    }

    return {
        palettes,
        personas,
        structures,
        documents,
        includedWorkflows,
        root: { importName: rootImportName, create: rootCreate },
        importWarnings,
    };
}

export function applyBundleIdMapsToDefinition(
    def: BundleDefinitionPayload,
    maps: BundleIdMaps,
): BundleDefinitionPayload {
    const graph = remapGraphIds(def.graph, maps);
    let palette_id = def.palette_id;
    if (palette_id) {
        const mapped = maps.palette.get(palette_id);
        if (mapped) palette_id = mapped;
    }
    return { ...def, graph, palette_id };
}

export function buildRemappedIncludedWorkflowUpdate(
    row: BundleIncludedWorkflow,
    maps: BundleIdMaps,
    importName: string,
): WorkflowDefinitionUpdate {
    const def = applyBundleIdMapsToDefinition(row.definition, maps);
    return {
        name: importName,
        description: def.description ?? null,
        graph: def.graph,
        palette_id: def.palette_id ?? null,
        ...(row.expose_as_custom_skill ? { expose_as_custom_skill: true } : {}),
    };
}

export type WorkflowBundleFetchers = {
    fetchWorkflow: (id: string) => Promise<WorkflowDefinition>;
    fetchPersona: (id: string) => Promise<Persona>;
    fetchStructure: (id: string) => Promise<Structure>;
    fetchDocument: (id: string) => Promise<Document>;
    fetchPalette: (id: string) => Promise<Palette>;
};

function personaToExport(p: Persona): BundlePersonaExport {
    return {
        source_id: p.id,
        name: p.name,
        description: p.description,
        system_prompt: p.system_prompt,
        type: p.type === 'system' ? 'system' : 'custom',
        default_model: p.default_model,
        is_default: p.is_default,
        creativity: p.creativity,
        suppress_lm_thinking: p.suppress_lm_thinking,
    };
}

/**
 * Resolve closure + referenced resources, then build the bundle document.
 * Throws WorkflowBundleExportError when nested workflows or referenced resources are missing.
 */
function attachPaletteSlugs(
    payload: BundleDefinitionPayload,
    paletteSlugBySourceId: Map<string, string>,
): BundleDefinitionPayload {
    const pid = normalizeUuid(payload.palette_id);
    if (!pid) return payload;
    const slug = paletteSlugBySourceId.get(pid);
    if (!slug) return payload;
    return { ...payload, palette_slug: slug };
}

export async function assembleWorkflowBundleExport(
    root: WorkflowDefinition,
    fetchers: WorkflowBundleFetchers,
): Promise<WorkflowBundleExportDocument> {
    const closure = await buildWorkflowBundleClosure(root, fetchers.fetchWorkflow);
    const paletteSlugBySourceId = new Map<string, string>();
    const allGraphs = [root.graph, ...[...closure.nestedById.values()].map(w => w.graph)];
    const refs = collectBundleResourceRefs(allGraphs);
    const paletteIds = collectBundlePaletteIds([
        definitionPayloadFromWorkflow(root),
        ...[...closure.nestedById.values()].map(definitionPayloadFromWorkflow),
    ]);

    const personas = new Map<string, BundlePersonaExport>();
    const structures = new Map<string, BundleStructureExport>();
    const documents = new Map<string, BundleDocumentExport>();
    const palettes = new Map<string, BundlePaletteExport>();
    const missingResources: string[] = [];

    for (const id of refs.personaIds) {
        try {
            personas.set(id, personaToExport(await fetchers.fetchPersona(id)));
        } catch {
            missingResources.push(`persona ${id}`);
        }
    }
    for (const id of refs.structureIds) {
        try {
            const s = await fetchers.fetchStructure(id);
            structures.set(id, {
                source_id: s.id,
                name: s.name,
                description: s.description,
                json_schema: s.json_schema,
            });
        } catch {
            missingResources.push(`structure ${id}`);
        }
    }
    for (const id of refs.documentIds) {
        try {
            const d = await fetchers.fetchDocument(id);
            documents.set(id, {
                source_id: d.id,
                name: d.name,
                description: d.description,
                body: d.body,
            });
        } catch {
            missingResources.push(`document ${id}`);
        }
    }
    for (const id of paletteIds) {
        try {
            const pal = await fetchers.fetchPalette(id);
            if (pal.slug) {
                paletteSlugBySourceId.set(id, pal.slug);
            }
            if (pal.user_id == null || pal.user_id === '') {
                continue;
            }
            palettes.set(id, {
                source_id: pal.id,
                name: pal.name,
                colors: expandWorkflowPaletteColorsForExport(pal.colors ?? {}),
                slug: pal.slug ?? null,
            });
        } catch {
            missingResources.push(`palette ${id}`);
        }
    }

    if (missingResources.length > 0) {
        throw new WorkflowBundleExportError(
            `Cannot export bundle: missing referenced resource(s): ${missingResources.join(', ')}`,
        );
    }

    const doc = buildWorkflowBundleExportDocument(closure, { personas, structures, documents, palettes });
    doc.definition = attachPaletteSlugs(doc.definition, paletteSlugBySourceId);
    doc.included_workflows = doc.included_workflows.map(row => ({
        ...row,
        definition: attachPaletteSlugs(row.definition, paletteSlugBySourceId),
    }));
    return doc;
}

/** Resolve exported palette_id to a palette id in the importer's account. */
export async function resolveBundlePaletteId(
    sourcePaletteId: string | null | undefined,
    paletteSlug: string | null | undefined,
    paletteMap: Map<string, string>,
    getPaletteBySlug: (slug: string) => Promise<{ id: string }>,
): Promise<string | null> {
    if (!sourcePaletteId) return null;
    const mapped = paletteMap.get(sourcePaletteId);
    if (mapped) return mapped;
    if (paletteSlug) {
        try {
            const builtin = await getPaletteBySlug(paletteSlug);
            return builtin.id;
        } catch {
            return null;
        }
    }
    return null;
}
