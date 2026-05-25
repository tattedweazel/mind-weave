import type {
    BoardDefinitionJson,
    RegionTriggerConfigJson,
    SandboxFacing,
    SandboxItemJson,
} from '../domain/sandbox/types';
import { DEFAULT_SANDBOX_FACING } from '../domain/sandbox/types';
import type { SandboxCellInteraction } from './sandboxCellInteractions';
import { normalizeHexColor } from './sandboxColorUtils';
import { isFixtureItem, isPickableItem, isSolidItem, REGION_ITEM_TYPE } from './sandboxCellOccupants';
import { resolvedItemType } from './sandboxItemResolve';
import {
    getEditableItemFields,
    isEditableItemFieldKey,
    SANDBOX_DEFAULT_FOOD_ENERGY,
    validateItemFieldValue,
    type SandboxItemEditableFieldKey,
} from './sandboxItemInspectorFields';

function filterSolidAt(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return items.filter(it => !(it.position.x === x && it.position.y === y && isSolidItem(it)));
}

function isRemovableAtCell(it: SandboxItemJson, x: number, y: number): boolean {
    if (it.position.x !== x || it.position.y !== y) return false;
    if (isFixtureItem(it) || it.type === REGION_ITEM_TYPE) return false;
    return isPickableItem(it) || isSolidItem(it);
}

function filterRemovableAt(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return items.filter(it => !isRemovableAtCell(it, x, y));
}

function filterRemovableItemById(
    items: SandboxItemJson[],
    itemId: string,
    x: number,
    y: number,
): SandboxItemJson[] {
    return items.filter(it => !(it.id === itemId && isRemovableAtCell(it, x, y)));
}

function filterPickablesAndSolidAt(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return filterRemovableAt(items, x, y);
}

function filterFixtureAt(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return items.filter(it => !(it.position.x === x && it.position.y === y && isFixtureItem(it)));
}

function filterRegionAt(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return items.filter(it => !(it.position.x === x && it.position.y === y && it.type === REGION_ITEM_TYPE));
}

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
        const cellItems = def.items.filter(it => it.position.x === x && it.position.y === y);
        const hasCreature = def.creatures.some(c => c.position.x === x && c.position.y === y);
        if (hasCreature) return def;
        const solid = cellItems.filter(isSolidItem);
        const placingSolid = interaction.item_type === 'wall';
        if (placingSolid && solid.length > 0) return def;
        if (!placingSolid && solid.some(it => !isFixtureItem(it))) return def;

        const normalizedBallColor =
            interaction.item_type === 'ball' ? normalizeHexColor(interaction.color ?? '') : null;
        if (interaction.item_type === 'ball' && !normalizedBallColor) return def;

        let items = def.items;
        if (placingSolid || interaction.item_type === 'food' || interaction.item_type === 'ball') {
            items = placingSolid ? filterSolidAt(def.items, x, y) : def.items;
        }

        if (interaction.definition_id) {
            const isTerrain = interaction.item_type === 'wall';
            const defColor =
                interaction.color != null ? normalizeHexColor(interaction.color) : null;
            return {
                ...def,
                items: [
                    ...(isTerrain ? filterSolidAt(def.items, x, y) : items),
                    {
                        id: `item-${crypto.randomUUID()}`,
                        definition_id: interaction.definition_id,
                        definition_kind: isTerrain ? 'terrain' : 'item',
                        role: isTerrain ? 'solid' : 'pickable',
                        type: isTerrain ? 'wall' : undefined,
                        position: { x, y },
                        ...(interaction.energy != null
                            ? { energy: interaction.energy }
                            : defColor
                              ? { color: defColor }
                              : {}),
                    },
                ],
            };
        }

        return {
            ...def,
            items: [
                ...items,
                {
                    id: `item-${crypto.randomUUID()}`,
                    type: interaction.item_type,
                    position: { x, y },
                    ...(interaction.item_type === 'food' ? { energy: SANDBOX_DEFAULT_FOOD_ENERGY } : {}),
                    ...(interaction.item_type === 'ball' && normalizedBallColor
                        ? { color: normalizedBallColor }
                        : {}),
                },
            ],
        };
    }
    if (interaction.type === 'remove_item') {
        const items = interaction.item_id
            ? filterRemovableItemById(def.items, interaction.item_id, x, y)
            : filterRemovableAt(def.items, x, y);
        return {
            ...def,
            items,
        };
    }
    if (interaction.type === 'place_fixture') {
        if (!inBounds(x, y)) return def;
        const hasCreature = def.creatures.some(c => c.position.x === x && c.position.y === y);
        if (hasCreature) return def;
        if (def.items.some(it => it.position.x === x && it.position.y === y && isSolidItem(it))) return def;
        return {
            ...def,
            items: [
                ...def.items,
                {
                    id: `fixture-${crypto.randomUUID()}`,
                    definition_id: interaction.definition_id,
                    definition_kind: 'fixture',
                    role: 'solid',
                    type: 'fixture',
                    position: { x, y },
                },
            ],
        };
    }
    if (interaction.type === 'remove_fixture') {
        return {
            ...def,
            items: filterFixtureAt(def.items, x, y),
        };
    }
    if (interaction.type === 'place_region') {
        if (!inBounds(x, y)) return def;
        const normalized = normalizeHexColor(interaction.color);
        if (!normalized) return def;
        const items = filterRegionAt(def.items, x, y);
        return {
            ...def,
            items: [
                ...items,
                {
                    id: `region-${crypto.randomUUID()}`,
                    type: REGION_ITEM_TYPE,
                    position: { x, y },
                    color: normalized,
                    label: interaction.label ?? '',
                    trigger: { enabled: false, mode: null, workflow_id: null, inputs: {} },
                    ...(interaction.definition_id
                        ? { definition_id: interaction.definition_id, definition_kind: 'region' as const }
                        : {}),
                },
            ],
        };
    }
    if (interaction.type === 'remove_region') {
        return {
            ...def,
            items: filterRegionAt(def.items, x, y),
        };
    }
    if (interaction.type === 'place_creature') {
        if (!inBounds(x, y)) return def;
        const normalized = normalizeHexColor(interaction.color);
        if (!normalized) return def;
        const items = filterPickablesAndSolidAt(def.items, x, y);
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
                    facing: interaction.facing ?? DEFAULT_SANDBOX_FACING,
                    color: normalized,
                    ...(interaction.creature_definition_id
                        ? { creature_definition_id: interaction.creature_definition_id }
                        : {}),
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

export type BoardItemMetadataPatch = Partial<
    Pick<SandboxItemJson, SandboxItemEditableFieldKey | 'color' | 'label' | 'trigger'>
>;

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
    const allowedFields = getEditableItemFields(item);
    const nextItem = { ...item };
    let changed = false;

    if (item.type === REGION_ITEM_TYPE) {
        if (patch.color !== undefined && typeof patch.color === 'string') {
            if (nextItem.color !== patch.color) {
                nextItem.color = patch.color;
                changed = true;
            }
        }
        if (patch.label !== undefined && typeof patch.label === 'string') {
            if (nextItem.label !== patch.label) {
                nextItem.label = patch.label;
                changed = true;
            }
        }
        if (patch.trigger !== undefined) {
            nextItem.trigger = patch.trigger as RegionTriggerConfigJson;
            changed = true;
        }
    }

    for (const [rawKey, rawValue] of Object.entries(patch)) {
        if (rawKey === 'color' || rawKey === 'trigger' || rawKey === 'label') {
            continue;
        }
        if (!isEditableItemFieldKey(item, rawKey)) {
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
