/**
 * Build payloads for sandbox session interaction APIs.
 */

import type { SandboxFacing, SandboxGridCellJson } from '../domain/sandbox/types';

export type SandboxPlaceItemInteraction = {
    type: 'place_item';
    cell: SandboxGridCellJson;
    item_type?: 'food' | 'wall' | 'ball';
    definition_id?: string;
    color?: string;
    energy?: number;
};

export type SandboxRemoveItemInteraction = {
    type: 'remove_item';
    cell: SandboxGridCellJson;
    item_id?: string;
};

export type SandboxPlaceFixtureInteraction = {
    type: 'place_fixture';
    cell: SandboxGridCellJson;
    definition_id: string;
};

export type SandboxRemoveFixtureInteraction = {
    type: 'remove_fixture';
    cell: SandboxGridCellJson;
};

export type SandboxPlaceRegionInteraction = {
    type: 'place_region';
    cell: SandboxGridCellJson;
    color: string;
    label?: string;
    definition_id?: string;
};

export type SandboxRemoveRegionInteraction = {
    type: 'remove_region';
    cell: SandboxGridCellJson;
};

export type SandboxPlaceCreatureInteraction = {
    type: 'place_creature';
    cell: SandboxGridCellJson;
    workflow_id: string;
    color: string;
    name?: string;
    facing?: SandboxFacing;
    creature_definition_id?: string;
};

export type SandboxRemoveCreatureInteraction = {
    type: 'remove_creature';
    cell: SandboxGridCellJson;
};

export type SandboxCellInteraction =
    | SandboxPlaceItemInteraction
    | SandboxRemoveItemInteraction
    | SandboxPlaceFixtureInteraction
    | SandboxRemoveFixtureInteraction
    | SandboxPlaceRegionInteraction
    | SandboxRemoveRegionInteraction
    | SandboxPlaceCreatureInteraction
    | SandboxRemoveCreatureInteraction;

export function placeFoodInteraction(cell: SandboxGridCellJson): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'food' };
}

export function placeWallInteraction(cell: SandboxGridCellJson): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'wall' };
}

export function placeBallInteraction(cell: SandboxGridCellJson, color: string): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'ball', color };
}

export function placeItemDefinitionInteraction(
    cell: SandboxGridCellJson,
    definitionId: string,
    options?: { color?: string; energy?: number },
): SandboxPlaceItemInteraction {
    return {
        type: 'place_item',
        cell,
        definition_id: definitionId,
        ...(options?.color ? { color: options.color } : {}),
        ...(options?.energy != null ? { energy: options.energy } : {}),
    };
}

export function placeFixtureInteraction(
    cell: SandboxGridCellJson,
    definitionId: string,
): SandboxPlaceFixtureInteraction {
    return { type: 'place_fixture', cell, definition_id: definitionId };
}

export function removeFixtureAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveFixtureInteraction {
    return { type: 'remove_fixture', cell };
}

export function placeRegionInteraction(
    cell: SandboxGridCellJson,
    color: string,
    label = '',
    definitionId?: string,
): SandboxPlaceRegionInteraction {
    return {
        type: 'place_region',
        cell,
        color,
        label,
        ...(definitionId ? { definition_id: definitionId } : {}),
    };
}

export function removeItemAtCellInteraction(
    cell: SandboxGridCellJson,
    itemId?: string,
): SandboxRemoveItemInteraction {
    return {
        type: 'remove_item',
        cell,
        ...(itemId ? { item_id: itemId } : {}),
    };
}

export function removeRegionAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveRegionInteraction {
    return { type: 'remove_region', cell };
}

export function placeCreatureInteraction(
    cell: SandboxGridCellJson,
    workflowId: string,
    options: { name?: string; facing?: SandboxFacing; color: string; creature_definition_id?: string },
): SandboxPlaceCreatureInteraction {
    return {
        type: 'place_creature',
        cell,
        workflow_id: workflowId,
        color: options.color,
        ...(options.name !== undefined ? { name: options.name } : {}),
        ...(options.facing !== undefined ? { facing: options.facing } : {}),
        ...(options.creature_definition_id ? { creature_definition_id: options.creature_definition_id } : {}),
    };
}

export function removeCreatureAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveCreatureInteraction {
    return { type: 'remove_creature', cell };
}
