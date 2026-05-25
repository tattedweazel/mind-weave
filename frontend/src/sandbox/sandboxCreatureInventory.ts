import type { ItemDefinitionRead } from '../api/types';
import type {
    BoardDefinitionJson,
    SandboxInventoryItemJson,
    SandboxInventoryItemType,
} from '../domain/sandbox/types';
import { normalizeHexColor } from './sandboxColorUtils';
import { SANDBOX_DEFAULT_FOOD_ENERGY } from './sandboxItemInspectorFields';
import { resolveBallDisplayColor } from './sandboxSensoryProbeDisplay';

export interface InventoryLabelContext {
    itemDefinitions?: ReadonlyArray<Pick<ItemDefinitionRead, 'id' | 'name' | 'label' | 'default_color'>>;
}

function definitionForEntry(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): Pick<ItemDefinitionRead, 'id' | 'name' | 'label' | 'default_color'> | undefined {
    const defId = entry.definition_id;
    if (!defId) return undefined;
    return ctx.itemDefinitions?.find(d => d.id === defId);
}

export function inventoryEntryTitle(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): string {
    const def = definitionForEntry(entry, ctx);
    if (def?.label) {
        return `Item · ${def.label}`;
    }
    if (entry.type === 'ball') {
        return 'Ball';
    }
    return 'Food';
}

export function inventoryEntryShowsEnergy(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): boolean {
    return entry.type === 'food';
}

export function inventoryEntryEnergy(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): number | null {
    if (!inventoryEntryShowsEnergy(entry, ctx)) return null;
    if (typeof entry.energy === 'number') return entry.energy;
    return null;
}

export function inventoryEntryColor(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): string | null {
    if (entry.type !== 'ball') return null;
    const def = definitionForEntry(entry, ctx);
    return resolveBallDisplayColor(entry.color ?? def?.default_color ?? undefined);
}

export function defaultInventoryEntry(type: SandboxInventoryItemType): SandboxInventoryItemJson {
    if (type === 'ball') {
        return { type: 'ball', color: '#3B82F6' };
    }
    return { type: 'food', energy: SANDBOX_DEFAULT_FOOD_ENERGY };
}

export function formatInventoryEntryLabel(
    entry: SandboxInventoryItemJson,
    ctx: InventoryLabelContext = {},
): string {
    const title = inventoryEntryTitle(entry, ctx);
    if (entry.type === 'ball') {
        const color = inventoryEntryColor(entry, ctx);
        return `${title} (${color ?? '?'})`;
    }
    const energy = inventoryEntryEnergy(entry, ctx);
    return `${title} (energy ${energy ?? '?'})`;
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
        next = {
            type: 'ball',
            color,
            ...(next.definition_id ? { definition_id: next.definition_id } : {}),
        };
    } else if (next.type === 'food') {
        const energy = next.energy;
        if (energy == null || !Number.isInteger(energy) || energy < 0) return def;
        next = {
            type: 'food',
            energy,
            ...(next.definition_id ? { definition_id: next.definition_id } : {}),
        };
    }
    inventory[index] = next;
    return updateBoardCreatureInventory(def, creatureId, inventory);
}
