import type {
    BoardDefinitionJson,
    SandboxInventoryItemJson,
    SandboxInventoryItemType,
} from '../domain/sandbox/types';
import { normalizeHexColor } from './sandboxColorUtils';
import { SANDBOX_DEFAULT_FOOD_ENERGY } from './sandboxItemInspectorFields';

export function defaultInventoryEntry(type: SandboxInventoryItemType): SandboxInventoryItemJson {
    if (type === 'ball') {
        return { type: 'ball', color: '#3B82F6' };
    }
    return { type: 'food', energy: SANDBOX_DEFAULT_FOOD_ENERGY };
}

export function formatInventoryEntryLabel(entry: SandboxInventoryItemJson): string {
    if (entry.type === 'ball') {
        return `Ball (${entry.color ?? '?'})`;
    }
    return `Food (energy ${entry.energy ?? '?'})`;
}

export function updateBoardCreatureInventory(
    def: BoardDefinitionJson,
    creatureId: string,
    inventory: SandboxInventoryItemJson[],
): BoardDefinitionJson {
    const index = def.creatures.findIndex(c => c.id === creatureId);
    if (index < 0) return def;
    const creatures = [...def.creatures];
    creatures[index] = { ...creatures[index], inventory: [...inventory] };
    return { ...def, creatures };
}

export function addBoardCreatureInventoryEntry(
    def: BoardDefinitionJson,
    creatureId: string,
    type: SandboxInventoryItemType,
): BoardDefinitionJson {
    const creature = def.creatures.find(c => c.id === creatureId);
    if (!creature) return def;
    const inventory = [...(creature.inventory ?? []), defaultInventoryEntry(type)];
    return updateBoardCreatureInventory(def, creatureId, inventory);
}

export function removeBoardCreatureInventoryEntry(
    def: BoardDefinitionJson,
    creatureId: string,
    index: number,
): BoardDefinitionJson {
    const creature = def.creatures.find(c => c.id === creatureId);
    if (!creature) return def;
    const inventory = [...(creature.inventory ?? [])];
    if (index < 0 || index >= inventory.length) return def;
    inventory.splice(index, 1);
    return updateBoardCreatureInventory(def, creatureId, inventory);
}

export function patchBoardCreatureInventoryEntry(
    def: BoardDefinitionJson,
    creatureId: string,
    index: number,
    patch: Partial<SandboxInventoryItemJson>,
): BoardDefinitionJson {
    const creature = def.creatures.find(c => c.id === creatureId);
    if (!creature) return def;
    const inventory = [...(creature.inventory ?? [])];
    if (index < 0 || index >= inventory.length) return def;
    const current = inventory[index];
    let next: SandboxInventoryItemJson = { ...current, ...patch };
    if (next.type === 'ball') {
        const color = normalizeHexColor(next.color ?? '');
        if (!color) return def;
        next = { type: 'ball', color };
    } else if (next.type === 'food') {
        const energy = next.energy;
        if (energy == null || !Number.isInteger(energy) || energy < 0) return def;
        next = { type: 'food', energy };
    }
    inventory[index] = next;
    return updateBoardCreatureInventory(def, creatureId, inventory);
}
