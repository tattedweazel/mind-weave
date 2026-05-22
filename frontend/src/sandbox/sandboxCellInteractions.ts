/** Build payloads for `POST .../tick` `interactions`. */

import type { SandboxGridCellJson } from '../domain/sandbox/types';

export type SandboxPlaceItemInteraction = {
    type: 'place_item';
    cell: SandboxGridCellJson;
    item_type: 'food' | 'wall';
};

export type SandboxRemoveItemInteraction = {
    type: 'remove_item';
    cell: SandboxGridCellJson;
};

export type SandboxPlaceCreatureInteraction = {
    type: 'place_creature';
    cell: SandboxGridCellJson;
    workflow_id: string;
    name?: string;
};

export type SandboxRemoveCreatureInteraction = {
    type: 'remove_creature';
    cell: SandboxGridCellJson;
};

export type SandboxCellInteraction =
    | SandboxPlaceItemInteraction
    | SandboxRemoveItemInteraction
    | SandboxPlaceCreatureInteraction
    | SandboxRemoveCreatureInteraction;

export function placeFoodInteraction(cell: SandboxGridCellJson): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'food' };
}

export function placeWallInteraction(cell: SandboxGridCellJson): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'wall' };
}

export function removeItemAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveItemInteraction {
    return { type: 'remove_item', cell };
}

export function placeCreatureInteraction(cell: SandboxGridCellJson, workflowId: string, name?: string): SandboxPlaceCreatureInteraction {
    return { type: 'place_creature', cell, workflow_id: workflowId, name };
}

export function removeCreatureAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveCreatureInteraction {
    return { type: 'remove_creature', cell };
}
