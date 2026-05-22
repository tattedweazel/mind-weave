import type { BoardDefinitionJson, SandboxFacing, SandboxItemJson } from '../domain/sandbox/types';
import { DEFAULT_SANDBOX_FACING } from '../domain/sandbox/types';
import type { SandboxCellInteraction } from './sandboxCellInteractions';
import {
    getEditableItemFields,
    isEditableItemFieldKey,
    SANDBOX_DEFAULT_FOOD_ENERGY,
    validateItemFieldValue,
    type SandboxItemEditableFieldKey,
} from './sandboxItemInspectorFields';

export function createEmptyBoardDefinition(width: number, height: number): BoardDefinitionJson {
    return {
        grid: { width, height },
        items: [],
        creatures: [],
    };
}

export function applyBoardBuilderInteraction(
    def: BoardDefinitionJson,
    interaction: SandboxCellInteraction,
): BoardDefinitionJson {
    const { x, y } = interaction.cell;
    const inBounds = (cx: number, cy: number) =>
        cx >= 0 && cy >= 0 && cx < def.grid.width && cy < def.grid.height;

    if (interaction.type === 'place_item') {
        if (!inBounds(x, y)) return def;
        const items = def.items.filter(it => !(it.position.x === x && it.position.y === y));
        const creatures = def.creatures.filter(c => !(c.position.x === x && c.position.y === y));
        return {
            ...def,
            items: [
                ...items,
                {
                    id: `item-${crypto.randomUUID()}`,
                    type: interaction.item_type,
                    position: { x, y },
                    ...(interaction.item_type === 'food' ? { energy: SANDBOX_DEFAULT_FOOD_ENERGY } : {}),
                },
            ],
            creatures,
        };
    }
    if (interaction.type === 'remove_item') {
        return {
            ...def,
            items: def.items.filter(it => !(it.position.x === x && it.position.y === y)),
        };
    }
    if (interaction.type === 'place_creature') {
        if (!inBounds(x, y)) return def;
        const items = def.items.filter(it => !(it.position.x === x && it.position.y === y));
        const creatures = def.creatures.filter(c => !(c.position.x === x && c.position.y === y));
        return {
            ...def,
            items,
            creatures: [
                ...creatures,
                {
                    id: `creature-${crypto.randomUUID()}`,
                    workflow_id: interaction.workflow_id,
                    name: interaction.name ?? null,
                    position: { x, y },
                    facing: DEFAULT_SANDBOX_FACING,
                },
            ],
        };
    }
    if (interaction.type === 'remove_creature') {
        return {
            ...def,
            creatures: def.creatures.filter(c => !(c.position.x === x && c.position.y === y)),
        };
    }
    return def;
}

export type BoardItemMetadataPatch = Partial<Pick<SandboxItemJson, SandboxItemEditableFieldKey>>;

export function updateBoardItemMetadata(
    def: BoardDefinitionJson,
    itemId: string,
    patch: BoardItemMetadataPatch,
): BoardDefinitionJson {
    const index = def.items.findIndex(it => it.id === itemId);
    if (index < 0) {
        return def;
    }

    const item = def.items[index];
    const allowedFields = getEditableItemFields(item.type);
    const nextItem = { ...item };
    let changed = false;

    for (const [rawKey, rawValue] of Object.entries(patch)) {
        if (!isEditableItemFieldKey(item.type, rawKey)) {
            continue;
        }
        const field = allowedFields.find(f => f.key === rawKey);
        if (!field || rawValue == null) {
            continue;
        }
        const validated = validateItemFieldValue(field, String(rawValue));
        if (validated == null) {
            continue;
        }
        if (rawKey === 'energy') {
            if (nextItem.energy !== validated) {
                nextItem.energy = validated;
                changed = true;
            }
        }
    }

    if (!changed) {
        return def;
    }

    const items = [...def.items];
    items[index] = nextItem;
    return { ...def, items };
}

export function updateBoardCreatureFacing(
    def: BoardDefinitionJson,
    creatureId: string,
    facing: SandboxFacing,
): BoardDefinitionJson {
    const index = def.creatures.findIndex(c => c.id === creatureId);
    if (index < 0 || def.creatures[index]?.facing === facing) {
        return def;
    }
    const creatures = [...def.creatures];
    creatures[index] = { ...creatures[index], facing };
    return { ...def, creatures };
}

export function resizeBoardDefinition(
    def: BoardDefinitionJson,
    width: number,
    height: number,
): BoardDefinitionJson {
    return {
        ...def,
        grid: { width, height },
        items: def.items.filter(it => it.position.x < width && it.position.y < height),
        creatures: def.creatures.filter(c => c.position.x < width && c.position.y < height),
    };
}
