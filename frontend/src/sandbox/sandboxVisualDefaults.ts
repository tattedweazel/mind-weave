/**
 * V1 placeholder visuals only — see docs/SANDBOX.md (Placeholder catalog).
 */
export const CELL_PX = 48;
export const BOARD_PADDING = 8;
export const BOARD_BG = '#0f172a';
export const GRID_LINE = '#334155';
export const CREATURE_FILL = '#38bdf8';
export const CREATURE_SELECTED_FILL = '#fbbf24';
export const FOOD_FILL = '#f472b6';
export const WALL_FILL = '#64748b';
export const REGION_UNDERLAY_ALPHA = 0.35;
export const DEFAULT_REGION_COLOR = '#3B82F6';

export const REGION_PRESET_COLORS = [
    '#3B82F6',
    '#EF4444',
    '#22C55E',
    '#EAB308',
    '#A855F7',
    '#F97316',
    '#06B6D4',
    '#EC4899',
];

/** @deprecated use CREATURE_FILL */
export const PET_FILL = CREATURE_FILL;
export const DEFAULT_TICK_RATE_MS = 1000;
export const SANDBOX_GRID_MIN_SIZE = 8;
export const SANDBOX_GRID_MAX_SIZE = 64;
export const SANDBOX_GRID_DEFAULT_WIDTH = 16;
export const SANDBOX_GRID_DEFAULT_HEIGHT = 16;

export const CREATURE_PALETTE = ['#38bdf8', '#a78bfa', '#34d399', '#fb923c', '#f472b6'];

export function creatureColor(index: number): string {
    return CREATURE_PALETTE[index % CREATURE_PALETTE.length];
}
