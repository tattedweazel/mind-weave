/** Build payloads for sandbox session interaction APIs. */

import type { SandboxFacing, SandboxGridCellJson } from '../domain/sandbox/types';

export type SandboxPlaceItemInteraction = {
    type: 'place_item';
    cell: SandboxGridCellJson;
    item_type: 'food' | 'wall';
};

export type SandboxRemoveItemInteraction = {
    type: 'remove_item';
    cell: SandboxGridCellJson;
};

export type SandboxPlaceRegionInteraction = {
    type: 'place_region';
    cell: SandboxGridCellJson;
    color: string;
};

export type SandboxRemoveRegionInteraction = {
    type: 'remove_region';
    cell: SandboxGridCellJson;
};

export type SandboxPlaceCreatureInteraction = {
    type: 'place_creature';
    cell: SandboxGridCellJson;
    workflow_id: string;
    name?: string;
    facing?: SandboxFacing;
};

export type SandboxRemoveCreatureInteraction = {
    type: 'remove_creature';
    cell: SandboxGridCellJson;
};

export type SandboxCellInteraction =
    | SandboxPlaceItemInteraction
    | SandboxRemoveItemInteraction
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

export function placeRegionInteraction(cell: SandboxGridCellJson, color: string): SandboxPlaceRegionInteraction {
    return { type: 'place_region', cell, color };
}

export function removeItemAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveItemInteraction {
    return { type: 'remove_item', cell };
}

export function removeRegionAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveRegionInteraction {
    return { type: 'remove_region', cell };
}

export function placeCreatureInteraction(
    cell: SandboxGridCellJson,
    workflowId: string,
    options?: { name?: string; facing?: SandboxFacing },
): SandboxPlaceCreatureInteraction {
    return {
        type: 'place_creature',
        cell,
        workflow_id: workflowId,
        ...(options?.name !== undefined ? { name: options.name } : {}),
        ...(options?.facing !== undefined ? { facing: options.facing } : {}),
    };
}

export function removeCreatureAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveCreatureInteraction {
    return { type: 'remove_creature', cell };
}
