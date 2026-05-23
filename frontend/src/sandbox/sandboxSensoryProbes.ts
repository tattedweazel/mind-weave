/**
 * Client-side sensory reads for sandbox simulation (mirrors backend/app/domain/sandbox/query.py).
 */

import type {
    SandboxCreatureJson,
    SandboxFacing,
    SandboxInventoryItemJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';

export type NearbyCellKind =
    | 'empty'
    | 'wall'
    | 'food'
    | 'ball'
    | 'creature'
    | 'out_of_bounds';

export interface NearbyCellJson {
    x: number;
    y: number;
    kind: NearbyCellKind;
    region_label?: string | null;
}

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

const SOLID_ITEM_TYPES = new Set(['wall']);
const REGION_ITEM_TYPE = 'region';
const BALL_ITEM_TYPE = 'ball';

export function creaturePositionFromState(creature: SandboxCreatureJson): { x: number; y: number } {
    return { x: creature.position.x, y: creature.position.y };
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
    for (const it of state.world.items) {
        if (it.position.x !== x || it.position.y !== y) continue;
        if (it.type === REGION_ITEM_TYPE) continue;
        if (SOLID_ITEM_TYPES.has(it.type)) return 'wall';
        if (it.type === BALL_ITEM_TYPE) return 'ball';
        if (it.type === 'food') return 'food';
    }
    return 'empty';
}

function regionLabelAtCell(x: number, y: number, state: SandboxSandboxStateJson): string | null {
    for (const it of state.world.items) {
        if (it.position.x === x && it.position.y === y && it.type === REGION_ITEM_TYPE) {
            return it.label ?? '';
        }
    }
    return null;
}

export function nearbyCellsFromState(
    creature: SandboxCreatureJson,
    state: SandboxSandboxStateJson,
): NearbyCellJson[] {
    const { width, height } = state.world.grid;
    const start = FACING_START_INDEX[creature.facing];
    const ordered = [...NEIGHBOR_OFFSETS_N.slice(start), ...NEIGHBOR_OFFSETS_N.slice(0, start)];
    const { x: px, y: py } = creature.position;
    return ordered.map(({ dx, dy }) => {
        const x = px + dx;
        const y = py + dy;
        return {
            x,
            y,
            kind: cellKind(x, y, width, height, state, creature.id),
            region_label: regionLabelAtCell(x, y, state),
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

/** True when the forward cell holds a ball or food that can be picked up. */
export function forwardCellPickable(creature: SandboxCreatureJson, state: SandboxSandboxStateJson): boolean {
    const kind = forwardCellKind(creature, state);
    return kind === 'ball' || kind === 'food';
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
            return creaturePositionFromState(creature);
        case 'facing':
            return creatureFacingFromState(creature);
        case 'inventory':
            return inventoryFromCreature(creature);
        default:
            return null;
    }
}
