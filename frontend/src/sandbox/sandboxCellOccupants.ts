import type {
    SandboxCreatureJson,
    SandboxEnvelopeJson,
    SandboxGridCellJson,
    SandboxItemJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';

export interface CellOccupants {
    items: SandboxItemJson[];
    creatures: SandboxCreatureJson[];
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

export type CellRootActionId = 'place_item' | 'remove_item' | 'place_creature' | 'remove_creature';

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
        description: 'Clear items from this cell',
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
    const hasItems = occupants.items.length > 0;
    const hasCreatures = occupants.creatures.length > 0;
    const isEmpty = !hasItems && !hasCreatures;

    const ids: CellRootActionId[] = [];

    if (isEmpty) {
        ids.push('place_item');
        if (allowCreatureActions) {
            ids.push('place_creature');
        }
    } else {
        if (hasItems) {
            ids.push('remove_item');
        }
        if (hasCreatures && allowCreatureActions) {
            ids.push('remove_creature');
        }
    }

    return ids.map(id => CELL_ROOT_ACTIONS[id]);
}
