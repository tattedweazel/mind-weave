/**
 * Helpers for sandbox_prompt_user_action workflow brains and tick orchestration.
 */

import type { WorkflowDefinition } from '../api/types';
import type { SandboxCreatureJson } from '../domain/sandbox/types';

export type SandboxUserDecisionAction =
    | 'move_forward'
    | 'turn_left'
    | 'turn_right'
    | 'idle'
    | 'pick_up_item'
    | 'place_item';

export type SandboxPlaceItemType = 'ball' | 'food';

export interface SandboxCreatureUserAction {
    action: SandboxUserDecisionAction;
    item_type?: SandboxPlaceItemType;
    inventory_index?: number;
}

export type CreatureUserActionsMap = Record<string, SandboxCreatureUserAction>;

export function promptUserActionNodeIdFromGraph(
    graph: WorkflowDefinition['graph'] | null | undefined,
): string | null {
    const nodes = (graph?.nodes ?? []) as {
        id?: string;
        kind?: string;
        utility_type?: string;
    }[];
    for (const node of nodes) {
        if (
            node.kind === 'utility' &&
            node.utility_type === 'sandbox_prompt_user_action' &&
            typeof node.id === 'string' &&
            node.id.trim()
        ) {
            return node.id.trim();
        }
    }
    return null;
}

export function graphRequiresSimulationUserAction(
    graph: WorkflowDefinition['graph'] | null | undefined,
): boolean {
    return promptUserActionNodeIdFromGraph(graph) != null;
}

export function autoReasonForUserAction(action: SandboxCreatureUserAction): string {
    if (action.action === 'place_item' && action.item_type) {
        if (action.inventory_index != null) {
            return `user: place_item:${action.item_type}@${action.inventory_index}`;
        }
        return `user: place_item:${action.item_type}`;
    }
    return `user: ${action.action}`;
}

export function buildCreatureUserActionsPayload(
    actions: CreatureUserActionsMap,
): Record<string, { action: string; item_type?: string; inventory_index?: number }> {
    const out: Record<string, { action: string; item_type?: string; inventory_index?: number }> = {};
    for (const [creatureId, act] of Object.entries(actions)) {
        const row: { action: string; item_type?: string; inventory_index?: number } = { action: act.action };
        if (act.action === 'place_item') {
            if (act.item_type) {
                row.item_type = act.item_type;
            }
            if (act.inventory_index != null) {
                row.inventory_index = act.inventory_index;
            }
        }
        out[creatureId] = row;
    }
    return out;
}

export function creaturesRequiringUserAction(
    creatures: SandboxCreatureJson[],
    workflowById: Map<string, WorkflowDefinition | null>,
): SandboxCreatureJson[] {
    return creatures.filter(c => {
        const wf = workflowById.get(c.workflow_id);
        return wf != null && graphRequiresSimulationUserAction(wf.graph);
    });
}
