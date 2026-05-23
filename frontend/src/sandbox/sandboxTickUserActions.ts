import type { WorkflowDefinition } from '../api/types';
import { ApiClient } from '../api/client';
import type { SandboxCreatureJson } from '../domain/sandbox/types';
import {
    buildCreatureUserActionsPayload,
    creaturesRequiringUserAction,
    type CreatureUserActionsMap,
} from './sandboxPromptUserAction';

/** Load full workflow definitions for unique creature brain ids. */
export async function loadWorkflowsForCreatures(
    creatures: SandboxCreatureJson[],
): Promise<Map<string, WorkflowDefinition | null>> {
    const ids = [...new Set(creatures.map(c => c.workflow_id).filter(Boolean))];
    const map = new Map<string, WorkflowDefinition | null>();
    await Promise.all(
        ids.map(async id => {
            try {
                const wf = await ApiClient.getWorkflow(id);
                map.set(id, wf);
            } catch {
                map.set(id, null);
            }
        }),
    );
    return map;
}

export async function planCreatureUserActionPrompts(
    creatures: SandboxCreatureJson[],
): Promise<{
    needing: SandboxCreatureJson[];
    workflowById: Map<string, WorkflowDefinition | null>;
}> {
    const workflowById = await loadWorkflowsForCreatures(creatures);
    const needing = creaturesRequiringUserAction(creatures, workflowById);
    return { needing, workflowById };
}

export function mergeCollectedUserActions(
    collected: CreatureUserActionsMap,
): Record<string, { action: string; item_type?: string }> {
    return buildCreatureUserActionsPayload(collected);
}
