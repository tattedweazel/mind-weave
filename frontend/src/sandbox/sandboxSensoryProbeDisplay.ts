/**
 * Display helpers for sandbox sensory probe readouts in the Remote Control modal.
 */

import type { NearbyCellJson, NearbyCellKind } from './sandboxSensoryProbes';
import { hexChipStyle, normalizeHexColor } from './sandboxColorUtils';

const DEFAULT_BALL_COLOR = '#3B82F6';

export function resolveBallDisplayColor(raw?: string): string {
    return normalizeHexColor(raw ?? '') ?? DEFAULT_BALL_COLOR;
}

export type NearbyRingSlot =
    | 'nw'
    | 'n'
    | 'ne'
    | 'w'
    | 'e'
    | 'sw'
    | 's'
    | 'se';

const OFFSET_TO_RING_SLOT: Record<string, NearbyRingSlot> = {
    '-1,-1': 'nw',
    '0,-1': 'n',
    '1,-1': 'ne',
    '-1,0': 'w',
    '1,0': 'e',
    '-1,1': 'sw',
    '0,1': 's',
    '1,1': 'se',
};

export const NEARBY_RING_LAYOUT: readonly (NearbyRingSlot | 'center')[] = [
    'nw',
    'n',
    'ne',
    'w',
    'center',
    'e',
    'sw',
    's',
    'se',
];

const NEARBY_CELL_KIND_LABELS: Record<NearbyCellKind, string> = {
    empty: 'Empty',
    wall: 'Wall',
    food: 'Food',
    ball: 'Ball',
    fixture: 'Fixture',
    creature: 'Creature',
    out_of_bounds: 'Out of bounds',
};

const NEARBY_CELL_KIND_BADGE_CLASSES: Record<NearbyCellKind, string> = {
    empty: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700/60 dark:text-slate-300 dark:border-slate-600',
    wall: 'bg-slate-200 text-slate-700 border-slate-300 dark:bg-slate-600 dark:text-slate-100 dark:border-slate-500',
    food: 'bg-pink-100 text-pink-800 border-pink-200 dark:bg-pink-950/50 dark:text-pink-200 dark:border-pink-800',
    ball: 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-200 dark:border-amber-800',
    fixture: 'bg-violet-100 text-violet-800 border-violet-200 dark:bg-violet-950/50 dark:text-violet-200 dark:border-violet-800',
    creature: 'bg-sky-100 text-sky-800 border-sky-200 dark:bg-sky-950/50 dark:text-sky-200 dark:border-sky-800',
    out_of_bounds: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-800',
};

export function nearbyCellKindLabel(kind: NearbyCellKind): string {
    return NEARBY_CELL_KIND_LABELS[kind];
}

export function nearbyCellKindBadgeClass(kind: NearbyCellKind): string {
    return NEARBY_CELL_KIND_BADGE_CLASSES[kind];
}

/** Inline badge styles for fixture cells with a resolved color; null when Tailwind fallback applies. */
export function nearbyCellKindBadgeStyle(
    cell: Pick<NearbyCellJson, 'kind' | 'color'>,
): { backgroundColor: string; color: string; borderColor: string } | null {
    if (cell.kind !== 'fixture' || cell.color == null) return null;
    const normalized = normalizeHexColor(cell.color);
    if (!normalized) return null;
    return hexChipStyle(normalized);
}

/** Label for the Region chip in Remote Control nearby tiles; null when no region on cell. */
export function nearbyRegionChipLabel(regionLabel: string | null | undefined): string | null {
    if (regionLabel == null) {
        return null;
    }
    const trimmed = regionLabel.trim();
    return trimmed === '' ? 'Region' : trimmed;
}

export function nearbyRegionChipBadgeClass(): string {
    return 'bg-violet-100 text-violet-800 border-violet-200 dark:bg-violet-950/50 dark:text-violet-200 dark:border-violet-800';
}

export function offsetToRingSlot(dx: number, dy: number): NearbyRingSlot | null {
    return OFFSET_TO_RING_SLOT[`${dx},${dy}`] ?? null;
}

export function nearbyCellsToRingMap(
    cells: NearbyCellJson[],
    origin: { x: number; y: number },
): Partial<Record<NearbyRingSlot, NearbyCellJson>> {
    const map: Partial<Record<NearbyRingSlot, NearbyCellJson>> = {};
    for (const cell of cells) {
        const slot = offsetToRingSlot(cell.x - origin.x, cell.y - origin.y);
        if (slot) {
            map[slot] = cell;
        }
    }
    return map;
}

export function forwardRingSlot(facing: 'N' | 'E' | 'S' | 'W'): NearbyRingSlot {
    switch (facing) {
        case 'N':
            return 'n';
        case 'E':
            return 'e';
        case 'S':
            return 's';
        case 'W':
            return 'w';
    }
}

export const PROBE_HINTS: Record<'nearby' | 'position' | 'facing' | 'inventory', string> = {
    nearby: '8 neighbors, clockwise from forward; cells with a region also show a Region badge',
    position: 'Current cell coordinates with kind and Region badges when present',
    facing: 'Current heading on the board',
    inventory: 'Items held by this creature',
};

export const INVENTORY_SELECTION_HINT = 'Choose an item to place';

export const PICK_UP_SELECTION_HINT = 'Choose an item to pick up';

export const PROBE_LABELS: Record<'nearby' | 'position' | 'facing' | 'inventory', string> = {
    nearby: 'Nearby',
    position: 'Position',
    facing: 'Facing',
    inventory: 'Inventory',
};
