import type { GraphNode as AppGraphNode } from '../../api/types';

import manifest from '../../../../shared/workflow_graph_step_kinds.json';

export type ManifestStep = (typeof manifest)['steps'][number];

/** Maps persisted graph discriminant → React Flow `Node.type` (see shared/workflow_graph_step_kinds.json). */
const flowTypeByKey = new Map<string, string>();

for (const s of manifest.steps) {
    if (s.kind === 'primitive' && 'primitive_type' in s && s.primitive_type) {
        flowTypeByKey.set(`primitive:${s.primitive_type}`, s.react_flow_type);
    } else if (s.kind === 'utility' && 'utility_type' in s && s.utility_type) {
        flowTypeByKey.set(`utility:${s.utility_type}`, s.react_flow_type);
    } else if (s.kind === 'skill' && 'skill_type' in s && s.skill_type) {
        flowTypeByKey.set(`skill:${s.skill_type}`, s.react_flow_type);
    } else if (s.kind === 'control' && 'control_type' in s && s.control_type) {
        flowTypeByKey.set(`control:${s.control_type}`, s.react_flow_type);
    } else {
        flowTypeByKey.set(s.kind, s.react_flow_type);
    }
}

/** Editor-only annotations (not in shared manifest; excluded from executor). */
const annotationFlowTypeByKey = new Map<string, string>([
    ['annotation:note', 'annotationNote'],
    ['annotation:region', 'annotationRegion'],
]);

export function manifestSteps(): ManifestStep[] {
    return manifest.steps;
}

export function expectedReactFlowTypeForAppNode(n: AppGraphNode): string | null {
    if (n.kind === 'primitive') return flowTypeByKey.get(`primitive:${n.primitive_type}`) ?? null;
    if (n.kind === 'utility' && 'utility_type' in n && (n as { utility_type: string }).utility_type === 'simple_llm_call') {
        return flowTypeByKey.get('skill:simple_llm_call') ?? null;
    }
    if (n.kind === 'utility') return flowTypeByKey.get(`utility:${n.utility_type}`) ?? null;
    if (n.kind === 'skill') return flowTypeByKey.get(`skill:${n.skill_type}`) ?? null;
    if (n.kind === 'control') return flowTypeByKey.get(`control:${n.control_type}`) ?? null;
    if (n.kind === 'start' || n.kind === 'stop' || n.kind === 'workflow') {
        return flowTypeByKey.get(n.kind) ?? null;
    }
    if (n.kind === 'annotation') {
        const at = (n as { annotation_type?: string }).annotation_type;
        if (!at) return null;
        return annotationFlowTypeByKey.get(`annotation:${at}`) ?? null;
    }
    return null;
}

/** React Flow type string from manifest for the current app node; throws if the manifest is missing a row. */
export function reactFlowTypeForAppNode(n: AppGraphNode): string {
    const t = expectedReactFlowTypeForAppNode(n);
    if (t == null) {
        throw new Error(
            `No react_flow_type for app node kind=${(n as AppGraphNode).kind} (check manifest and annotation registry)`,
        );
    }
    return t;
}
