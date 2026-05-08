/** Build payloads for `POST .../tick` `interactions` (mirrors backend / shared schema). */

import type { SandboxGridCellJson } from '../domain/sandbox/types';

export type SandboxPlaceItemInteraction = {
    type: 'place_item';
    cell: SandboxGridCellJson;
    item_type: 'food';
};

export type SandboxRemoveItemInteraction = {
    type: 'remove_item';
    cell: SandboxGridCellJson;
};

export type SandboxCellInteraction = SandboxPlaceItemInteraction | SandboxRemoveItemInteraction;

export function placeFoodInteraction(cell: SandboxGridCellJson): SandboxPlaceItemInteraction {
    return { type: 'place_item', cell, item_type: 'food' };
}

export function removeItemAtCellInteraction(cell: SandboxGridCellJson): SandboxRemoveItemInteraction {
    return { type: 'remove_item', cell };
}
