import type {
    SandboxCreatureJson,
    SandboxEnvelopeJson,
    SandboxGridCellJson,
    SandboxItemJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';
import {
    isFixtureItem,
    isPickableItem,
    isRegionItemResolved,
    isSolidItem,
    resolvedItemType,
} from './sandboxItemResolve';

export { resolvedItemType, isSolidItem, isPickableItem, isFixtureItem };

export const BLOCKING_ITEM_TYPES = new Set(['food', 'wall', 'ball', 'fixture']);
export const REGION_ITEM_TYPE = 'region';

export interface CellOccupants {
    items: SandboxItemJson[];
    creatures: SandboxCreatureJson[];
}

export function isBlockingItem(item: SandboxItemJson): boolean {
    return BLOCKING_ITEM_TYPES.has(resolvedItemType(item));
}

export function isRegionItem(item: SandboxItemJson): boolean {
    return isRegionItemResolved(item);
}

export function getBlockingItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isBlockingItem);
}

export function getSolidItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isSolidItem);
}

export function getPickableItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isPickableItem);
}

export function isRemovableCellItem(item: SandboxItemJson): boolean {
    if (isRegionItem(item) || isFixtureItem(item)) return false;
    return isPickableItem(item) || isSolidItem(item);
}

export function getRemovableCellItems(items: SandboxItemJson[]): SandboxItemJson[] {
    return items.filter(isRemovableCellItem);
}

export interface RemovableItemLabelContext {
    itemDefinitions?: ReadonlyArray<{ id: string; name: string; label: string }>;
    terrainDefinitions?: ReadonlyArray<{ id: string; name: string; label: string }>;
}

export function describeRemovableCellItem(
    item: SandboxItemJson,
    context?: RemovableItemLabelContext,
): string {
    if (item.label?.trim()) return item.label.trim();

    const defId = item.definition_id;
    if (defId && context?.itemDefinitions) {
        const def = context.itemDefinitions.find(d => d.id === defId);
        if (def) return def.label || def.name;
    }
    if (defId && context?.terrainDefinitions) {
        const def = context.terrainDefinitions.find(d => d.id === defId);
        if (def) return def.label || def.name;
    }

    const type = resolvedItemType(item);
    if (type === 'food') return item.energy != null ? `Food (${item.energy})` : 'Food';
    if (type === 'ball') return item.color ? `Ball (${item.color})` : 'Ball';
    if (type === 'wall') return 'Wall';
    return type;
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
    | 'place_fixture'
    | 'remove_fixture'
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
        description: 'Item, terrain, or built-in template',
    },
    remove_item: {
        id: 'remove_item',
        label: 'Remove item',
        description: 'Clear pickables or solid terrain from this cell',
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
    place_fixture: {
        id: 'place_fixture',
        label: 'Place fixture',
        description: 'Solid, workflow-powered interactable',
    },
    remove_fixture: {
        id: 'remove_fixture',
        label: 'Remove fixture',
        description: 'Clear fixture from this cell',
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

function cellHasNonRegionItems(items: SandboxItemJson[]): boolean {
    return items.some(it => !isRegionItem(it));
}

export function canPlacePickableItem(items: SandboxItemJson[], hasCreatures: boolean): boolean {
    if (hasCreatures) return false;
    const solid = getSolidItems(items);
    if (solid.length === 0) return true;
    return solid.length === 1 && isFixtureItem(solid[0]!);
}

export function deriveCellRootActions(
    occupants: CellOccupants,
    options?: { allowCreatureActions?: boolean },
): CellRootAction[] {
    const allowCreatureActions = options?.allowCreatureActions ?? false;
    const solidItems = getSolidItems(occupants.items);
    const pickables = getPickableItems(occupants.items);
    const hasFixture = solidItems.some(isFixtureItem);
    const hasNonFixtureSolid = solidItems.some(it => !isFixtureItem(it));
    const hasRegion = getRegionItems(occupants.items).length > 0;
    const hasCreatures = occupants.creatures.length > 0;
    const nonFixtureSolids = solidItems.filter(it => !isFixtureItem(it));
    const hasRemovableNonFixtureItems = nonFixtureSolids.length > 0 || pickables.length > 0;

    const ids: CellRootActionId[] = ['place_region'];

    if (hasRemovableNonFixtureItems) {
        ids.push('remove_item');
    }
    if (canPlacePickableItem(occupants.items, hasCreatures)) {
        ids.push('place_item');
    }

    if (hasFixture) {
        ids.push('remove_fixture');
    } else if (!hasCreatures && !hasNonFixtureSolid) {
        ids.push('place_fixture');
    }

    if (allowCreatureActions) {
        if (hasCreatures) {
            ids.push('remove_creature');
        } else if (!cellHasNonRegionItems(occupants.items)) {
            ids.push('place_creature');
        }
    }

    if (hasRegion) {
        ids.push('remove_region');
    }

    return ids.map(id => CELL_ROOT_ACTIONS[id]);
}
