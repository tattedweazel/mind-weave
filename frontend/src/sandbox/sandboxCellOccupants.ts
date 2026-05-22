import type {
    SandboxCreatureJson,
    SandboxEnvelopeJson,
    SandboxGridCellJson,
    SandboxItemJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';

export const BLOCKING_ITEM_TYPES = new Set(['food', 'wall']);
export const REGION_ITEM_TYPE = 'region';

export interface CellOccupants {
    items: SandboxItemJson[];
    creatures: SandboxCreatureJson[];
}

export function isBlockingItem(item: SandboxItemJson): boolean {
    return BLOCKING_ITEM_TYPES.has(item.type);
}

export function isRegionItem(item: SandboxItemJson): boolean {
    return item.type === REGION_ITEM_TYPE;
}

export function getBlockingItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isBlockingItem);
}

export function getRegionItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isRegionItem);
}

export function getCellOccupantsFromSandboxState(
    state: SandboxSandboxStateJson,
    cell: SandboxGridCellJson,
): CellOccupants {
    const { x, y } = cell;
    const items = (state.world.items ?? []).filter(it => it.position.x === x && it.position.y === y);
    const creatures = (state.creatures ?? []).filter(c => c.position.x === x && c.position.y === y);
    return { items, creatures };
}

export function getCellOccupants(envelope: SandboxEnvelopeJson, cell: SandboxGridCellJson): CellOccupants {
    return getCellOccupantsFromSandboxState(envelope.sandbox, cell);
}

export function cellHasInspectableContent(occupants: CellOccupants): boolean {
    return occupants.items.length > 0 || occupants.creatures.length > 0;
}

export type CellRootActionId =
    | 'place_item'
    | 'remove_item'
    | 'place_region'
    | 'remove_region'
    | 'place_creature'
    | 'remove_creature';

export interface CellRootAction {
    id: CellRootActionId;
    label: string;
    description: string;
}

const CELL_ROOT_ACTIONS: Record<CellRootActionId, CellRootAction> = {
    place_item: {
        id: 'place_item',
        label: 'Place item',
        description: 'Put food or wall on this cell',
    },
    remove_item: {
        id: 'remove_item',
        label: 'Remove item',
        description: 'Clear food or wall from this cell',
    },
    place_region: {
        id: 'place_region',
        label: 'Place region',
        description: 'Colored visual marker — coexists with other occupants',
    },
    remove_region: {
        id: 'remove_region',
        label: 'Remove region',
        description: 'Clear the region marker from this cell',
    },
    place_creature: {
        id: 'place_creature',
        label: 'Place creature',
        description: 'Spawn a creature with a workflow brain',
    },
    remove_creature: {
        id: 'remove_creature',
        label: 'Remove creature',
        description: 'Remove creature from this cell',
    },
};

export function deriveCellRootActions(
    occupants: CellOccupants,
    options?: { allowCreatureActions?: boolean },
): CellRootAction[] {
    const allowCreatureActions = options?.allowCreatureActions ?? false;
    const hasBlockingItems = getBlockingItems(occupants.items).length > 0;
    const hasRegion = getRegionItems(occupants.items).length > 0;
    const hasCreatures = occupants.creatures.length > 0;

    const ids: CellRootActionId[] = ['place_region'];

    if (hasBlockingItems) {
        ids.push('remove_item');
    } else if (!hasCreatures) {
        ids.push('place_item');
    }

    if (allowCreatureActions) {
        if (hasCreatures) {
            ids.push('remove_creature');
        } else if (!hasBlockingItems) {
            ids.push('place_creature');
        }
    }

    if (hasRegion) {
        ids.push('remove_region');
    }

    return ids.map(id => CELL_ROOT_ACTIONS[id]);
}
