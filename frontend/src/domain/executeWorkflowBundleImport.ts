/**
 * Orchestrates API calls for workflow bundle import (create resources + remap pass).
 */

import type {
    Document,
    Palette,
    Persona,
    Structure,
    WorkflowDefinition,
    WorkflowProject,
} from '../api/types';
import {
    applyBundleIdMapsToDefinition,
    buildRemappedIncludedWorkflowUpdate,
    resolveBundlePaletteId,
    type BundleIdMaps,
    type BundleImportPlan,
    type WorkflowBundleExportDocument,
} from './workflowBundleImportExport';

export type WorkflowBundleImportApi = {
    createPalette: (data: { name: string; colors: Record<string, string> }) => Promise<Palette>;
    getPaletteBySlug: (slug: string) => Promise<Palette>;
    createPersona: (data: import('../api/types').PersonaCreate) => Promise<Persona>;
    createStructure: (data: import('../api/types').StructureCreate) => Promise<Structure>;
    createDocument: (data: import('../api/types').DocumentCreate) => Promise<Document>;
    createWorkflow: (data: import('../api/types').WorkflowDefinitionCreate) => Promise<WorkflowDefinition>;
    updateWorkflow: (id: string, data: import('../api/types').WorkflowDefinitionUpdate) => Promise<WorkflowDefinition>;
};

export type ExecuteWorkflowBundleImportOptions = {
    bundle: WorkflowBundleExportDocument;
    plan: BundleImportPlan;
    projectId: string;
    api: WorkflowBundleImportApi;
};

export type ExecuteWorkflowBundleImportResult = {
    root: WorkflowDefinition;
    importWarnings: string[];
};

export async function executeWorkflowBundleImport(
    options: ExecuteWorkflowBundleImportOptions,
): Promise<ExecuteWorkflowBundleImportResult> {
    const { bundle, plan, projectId, api } = options;

    const maps: BundleIdMaps = {
        workflow: new Map(),
        persona: new Map(),
        structure: new Map(),
        document: new Map(),
        palette: new Map(),
    };

    const resolvePaletteForDefinition = async (
        sourcePaletteId: string | null | undefined,
        paletteSlug: string | null | undefined,
    ) =>
        resolveBundlePaletteId(sourcePaletteId, paletteSlug, maps.palette, slug =>
            api.getPaletteBySlug(slug),
        );

    for (const row of plan.palettes) {
        if (row.slug) {
            try {
                const builtin = await api.getPaletteBySlug(row.slug);
                maps.palette.set(row.source_id, builtin.id);
                continue;
            } catch {
                /* create user palette below */
            }
        }
        const created = await api.createPalette(row.create);
        maps.palette.set(row.source_id, created.id);
    }

    for (const row of plan.personas) {
        const created = await api.createPersona(row.create);
        maps.persona.set(row.source_id, created.id);
    }

    for (const row of plan.structures) {
        const created = await api.createStructure(row.create);
        maps.structure.set(row.source_id, created.id);
    }

    for (const row of plan.documents) {
        const created = await api.createDocument(row.create);
        maps.document.set(row.source_id, created.id);
    }

    const createdIncluded: Array<{ sourceId: string; id: string; importName: string }> = [];

    for (const row of plan.includedWorkflows) {
        const bundleRow = bundle.included_workflows.find(w => w.source_definition_id === row.source_definition_id);
        const palette_id = await resolvePaletteForDefinition(
            row.create.palette_id,
            bundleRow?.definition.palette_slug,
        );
        const created = await api.createWorkflow({
            ...row.create,
            palette_id,
            project_id: projectId,
        });
        maps.workflow.set(row.source_definition_id, created.id);
        createdIncluded.push({
            sourceId: row.source_definition_id,
            id: created.id,
            importName: row.importName,
        });
    }

    for (const inc of createdIncluded) {
        const row = bundle.included_workflows.find(w => w.source_definition_id === inc.sourceId);
        if (!row) continue;
        const update = buildRemappedIncludedWorkflowUpdate(row, maps, inc.importName);
        update.palette_id = await resolvePaletteForDefinition(
            row.definition.palette_id,
            row.definition.palette_slug,
        );
        await api.updateWorkflow(inc.id, update);
    }

    const rootDef = applyBundleIdMapsToDefinition(bundle.definition, maps);
    const rootPaletteId = await resolvePaletteForDefinition(
        bundle.definition.palette_id,
        bundle.definition.palette_slug,
    );
    const root = await api.createWorkflow({
        name: plan.root.importName,
        description: plan.root.create.description ?? null,
        graph: rootDef.graph,
        palette_id: rootPaletteId,
        project_id: projectId,
    });

    return { root, importWarnings: plan.importWarnings };
}

/** Names from list endpoints for collision detection during planBundleImport. */
export function bundleImportExistingNames(input: {
    workflows: { name: string }[];
    personas: { name: string }[];
    structures: { name: string }[];
    documents: { name: string }[];
    palettes: { name: string }[];
}): {
    workflows: string[];
    personas: string[];
    structures: string[];
    documents: string[];
    palettes: string[];
} {
    return {
        workflows: input.workflows.map(w => w.name),
        personas: input.personas.map(p => p.name),
        structures: input.structures.map(s => s.name),
        documents: input.documents.map(d => d.name),
        palettes: input.palettes.map(p => p.name),
    };
}

export type { WorkflowProject };
