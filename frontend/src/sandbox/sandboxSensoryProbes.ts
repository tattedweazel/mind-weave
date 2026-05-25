/**
 * Client-side sensory reads for sandbox simulation (mirrors backend/app/domain/sandbox/query.py).
 */

import type {
    SandboxCreatureJson,
    SandboxFacing,
    SandboxInventoryItemJson,
    SandboxItemJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';
import { canPlacePickableItem } from './sandboxCellOccupants';
import { isPickableItem, isRegionItemResolved, isSolidItem, resolvedItemType } from './sandboxItemResolve';

export type NearbyCellKind =
    | 'empty'
    | 'wall'
    | 'food'
    | 'ball'
    | 'fixture'
    | 'creature'
    | 'out_of_bounds';

export interface NearbyCellItemSummaryJson {
    id: string;
    kind: string;
    definition_id?: string | null;
    energy?: number | null;
    color?: string | null;
    label?: string;
}

export interface PickableLabelContext {
    itemDefinitions?: ReadonlyArray<{
        id: string;
        name: string;
        label: string;
        default_energy?: number | null;
        default_color?: string | null;
    }>;
}

function probeItemKind(item: SandboxItemJson): string {
    if (item.definition_kind === 'item' && item.definition_id) {
        return 'item';
    }
    return resolvedItemType(item);
}

function definitionDefaultsForItem(
    item: SandboxItemJson,
    context?: PickableLabelContext,
): { default_energy?: number | null; default_color?: string | null } | null {
    const defId = item.definition_id;
    if (!defId || !context?.itemDefinitions) return null;
    const def = context.itemDefinitions.find(d => d.id === defId);
    if (!def) return null;
    return { default_energy: def.default_energy, default_color: def.default_color };
}

function resolvedPickableEnergy(item: SandboxItemJson, context?: PickableLabelContext): number | null {
    if (item.energy != null) return item.energy;
    return definitionDefaultsForItem(item, context)?.default_energy ?? null;
}

function resolvedPickableColor(item: SandboxItemJson, context?: PickableLabelContext): string | null {
    if (item.color != null) return item.color;
    return definitionDefaultsForItem(item, context)?.default_color ?? null;
}

function resolvePickableDisplayLabel(item: SandboxItemJson, context?: PickableLabelContext): string {
    if (item.label?.trim()) return item.label.trim();
    const defId = item.definition_id;
    if (defId && context?.itemDefinitions) {
        const def = context.itemDefinitions.find(d => d.id === defId);
        if (def) return def.label || def.name;
    }
    const type = resolvedItemType(item);
    const energy = resolvedPickableEnergy(item, context);
    const color = resolvedPickableColor(item, context);
    if (type === 'food') return energy != null ? `Food (${energy})` : 'Food';
    if (type === 'ball') return color ? `Ball (${color})` : 'Ball';
    return type;
}

export interface NearbyCellJson {
    x: number;
    y: number;
    kind: NearbyCellKind;
    region_label?: string | null;
    stack_count?: number;
    items?: NearbyCellItemSummaryJson[];
}

/** Cell probe shape shared by Position probe and Get position utility output. */
export type CellProbeJson = NearbyCellJson;

const NEIGHBOR_OFFSETS_N: readonly { dx: number; dy: number }[] = [
    { dx: 0, dy: -1 },
    { dx: 1, dy: -1 },
    { dx: 1, dy: 0 },
    { dx: 1, dy: 1 },
    { dx: 0, dy: 1 },
    { dx: -1, dy: 1 },
    { dx: -1, dy: 0 },
    { dx: -1, dy: -1 },
];

const FACING_START_INDEX: Record<SandboxFacing, number> = {
    N: 0,
    E: 2,
    S: 4,
    W: 6,
};

function itemsAtCell(items: SandboxItemJson[], x: number, y: number): SandboxItemJson[] {
    return items.filter(it => it.position.x === x && it.position.y === y);
}

function cellItemsSummary(
    x: number,
    y: number,
    state: SandboxSandboxStateJson,
    labelContext?: PickableLabelContext,
): { stack_count: number; items: NearbyCellItemSummaryJson[] } {
    const cellItems = itemsAtCell(state.world.items, x, y);
    const pickables = cellItems.filter(isPickableItem);
    return {
        stack_count: pickables.length,
        items: pickables.map(it => ({
            id: it.id,
            kind: probeItemKind(it),
            definition_id: it.definition_id ?? null,
            energy: resolvedPickableEnergy(it, labelContext),
            color: resolvedPickableColor(it, labelContext),
            label: resolvePickableDisplayLabel(it, labelContext),
        })),
    };
}

export function creaturePositionFromState(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
    labelContext?: PickableLabelContext,
): CellProbeJson {
    const { x, y } = creature.position;
    const { width, height } = state.world.grid;
    const { stack_count, items } = cellItemsSummary(x, y, state, labelContext);
    return {
        x,
        y,
        kind: cellKind(x, y, width, height, state, creature.id),
        region_label: regionLabelAtCell(x, y, state),
        stack_count,
        items,
    };
}

export function creatureFacingFromState(creature: SandboxCreatureJson): SandboxFacing {
    return creature.facing;
}

export function inventoryFromCreature(creature: SandboxCreatureJson): SandboxInventoryItemJson[] {
    return creature.inventory ?? [];
}

function cellKind(
    x: number,
    y: number,
    width: number,
    height: number,
    state: SandboxSandboxStateJson,
    excludeCreatureId: string,
): NearbyCellKind {
    if (x < 0 || y < 0 || x >= width || y >= height) {
        return 'out_of_bounds';
    }
    for (const c of state.creatures) {
        if (c.id === excludeCreatureId) continue;
        if (c.position.x === x && c.position.y === y) {
            return 'creature';
        }
    }
    const cellItems = itemsAtCell(state.world.items, x, y);
    for (const it of cellItems) {
        if (isRegionItemResolved(it)) continue;
        const t = resolvedItemType(it);
        if (t === 'fixture') return 'fixture';
        if (isSolidItem(it)) return 'wall';
        if (t === 'ball') return 'ball';
        if (t === 'food') return 'food';
    }
    return 'empty';
}

function regionLabelAtCell(x: number, y: number, state: SandboxSandboxStateJson): string | null {
    for (const it of state.world.items) {
        if (it.position.x === x && it.position.y === y && isRegionItemResolved(it)) {
            return it.label ?? '';
        }
    }
    return null;
}

export function nearbyCellsFromState(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
    labelContext?: PickableLabelContext,
): NearbyCellJson[] {
    const { width, height } = state.world.grid;
    const start = FACING_START_INDEX[creature.facing];
    const ordered = [...NEIGHBOR_OFFSETS_N.slice(start), ...NEIGHBOR_OFFSETS_N.slice(0, start)];
    const { x: px, y: py } = creature.position;
    return ordered.map(({ dx, dy }) => {
        const x = px + dx;
        const y = py + dy;
        const { stack_count, items } = cellItemsSummary(x, y, state, labelContext);
        return {
            x,
            y,
            kind: cellKind(x, y, width, height, state, creature.id),
            region_label: regionLabelAtCell(x, y, state),
            stack_count,
            items,
        };
    });
}

/** Kind of the cell immediately in front of the creature (index 0 of nearby ring). */
export function forwardCellKind(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): NearbyCellKind {
    const nearby = nearbyCellsFromState(creature, state);
    return nearby[0]?.kind ?? 'out_of_bounds';
}

function forwardCellCoordinates(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): { x: number; y: number } | null {
    const nearby = nearbyCellsFromState(creature, state);
    const forward = nearby[0];
    if (!forward || forward.kind === 'out_of_bounds' || forward.kind === 'creature') {
        return null;
    }
    return { x: forward.x, y: forward.y };
}

/** Pickable summaries in the forward adjacent cell (may coexist with a fixture). */
export function forwardCellPickables(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
    labelContext?: PickableLabelContext,
): NearbyCellItemSummaryJson[] {
    const coords = forwardCellCoordinates(creature, state);
    if (!coords) return [];
    return cellItemsSummary(coords.x, coords.y, state, labelContext).items;
}

/** True when the forward cell holds one or more pickables (including on fixture cells). */
export function forwardCellPickable(creature: SandboxCreatureJson, state: SandboxSandboxStateJson): boolean {
    return forwardCellPickables(creature, state).length > 0;
}

/** True when the forward cell holds a fixture that can be used. */
export function forwardCellHasFixture(creature: SandboxCreatureJson, state: SandboxSandboxStateJson): boolean {
    return forwardCellKind(creature, state) === 'fixture';
}

/** True when an inventory pickable may be placed on the forward cell (empty, fixture stack, or pickable stack). */
export function forwardCellAllowsPlaceItem(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): boolean {
    const coords = forwardCellCoordinates(creature, state);
    if (!coords) return false;
    const cellItems = itemsAtCell(state.world.items, coords.x, coords.y);
    const hasCreature = state.creatures.some(
        c => c.position.x === coords.x && c.position.y === coords.y,
    );
    return canPlacePickableItem(cellItems, hasCreature);
}

/** User-facing reason when forwardCellAllowsPlaceItem is false; null when placement is allowed. */
export function forwardCellPlaceBlockedReason(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): string | null {
    if (forwardCellAllowsPlaceItem(creature, state)) return null;
    const kind = forwardCellKind(creature, state);
    if (kind === 'out_of_bounds') return 'Forward cell is out of bounds';
    if (kind === 'creature') return 'Forward cell is occupied by a creature';
    if (kind === 'wall') return 'Forward cell is blocked by terrain';
    return 'Forward cell cannot accept items';
}

export type SandboxSensoryProbeKind = 'nearby' | 'position' | 'facing' | 'inventory';

export function runSensoryProbe(
    kind: SandboxSensoryProbeKind,
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): unknown {
    switch (kind) {
        case 'nearby':
            return nearbyCellsFromState(creature, state);
        case 'position':
            return creaturePositionFromState(creature, state);
        case 'facing':
            return creatureFacingFromState(creature);
        case 'inventory':
            return inventoryFromCreature(creature);
        default:
            return null;
    }
}
