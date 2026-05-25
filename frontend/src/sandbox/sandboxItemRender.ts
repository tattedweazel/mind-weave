import type { SandboxItemJson } from '../domain/sandbox/types';
import {
    isFixtureItem,
    isPickableItem,
    isRegionItemResolved,
    isSolidItem,
    resolvedItemType,
} from './sandboxItemResolve';
import {
    CELL_PX,
    DEFAULT_REGION_COLOR,
    FOOD_FILL,
    REGION_UNDERLAY_ALPHA,
    WALL_FILL,
} from './sandboxVisualDefaults';

export type SandboxItemRenderLayer = 'region' | 'solid' | 'pickable';

export const SANDBOX_ITEM_RENDER_LAYERS: readonly SandboxItemRenderLayer[] = [
    'region',
    'solid',
    'pickable',
];

export type DefinitionShape = 'circle' | 'square';

export interface SandboxItemDefinitionRenderEntry {
    id: string;
    shape: DefinitionShape;
    default_color?: string | null;
}

export interface SandboxItemRenderCatalog {
    itemDefinitions: ReadonlyArray<SandboxItemDefinitionRenderEntry>;
}

export const EMPTY_SANDBOX_ITEM_RENDER_CATALOG: SandboxItemRenderCatalog = {
    itemDefinitions: [],
};

export interface SandboxPickableVisual {
    color: string;
    shape: DefinitionShape;
    isBall: boolean;
}

export interface SandboxGraphics {
    fillStyle(color: number, alpha: number): void;
    fillRect(x: number, y: number, width: number, height: number): void;
    fillCircle(x: number, y: number, radius: number): void;
    lineStyle(lineWidth: number, color: number, alpha: number): void;
    strokeCircle(x: number, y: number, radius: number): void;
    strokeRect(x: number, y: number, width: number, height: number): void;
}

function hexToRgbInt(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
}

export function getSandboxItemRenderLayer(item: SandboxItemJson): SandboxItemRenderLayer | null {
    if (isRegionItemResolved(item)) return 'region';
    if (isSolidItem(item)) return 'solid';
    if (isPickableItem(item)) return 'pickable';
    return null;
}

function lookupItemDefinition(
    catalog: SandboxItemRenderCatalog,
    definitionId: string | undefined,
): SandboxItemDefinitionRenderEntry | undefined {
    if (!definitionId) return undefined;
    return catalog.itemDefinitions.find(def => def.id === definitionId);
}

export function resolvePickableVisual(
    item: SandboxItemJson,
    catalog: SandboxItemRenderCatalog = EMPTY_SANDBOX_ITEM_RENDER_CATALOG,
): SandboxPickableVisual {
    const definition = lookupItemDefinition(catalog, item.definition_id);
    const isBall = resolvedItemType(item) === 'ball';
    const color = item.color ?? definition?.default_color ?? FOOD_FILL;
    const shape = definition?.shape ?? 'circle';
    return { color, shape, isBall };
}

export function drawSandboxItem(
    g: SandboxGraphics,
    item: SandboxItemJson,
    ox: number,
    oy: number,
    catalog: SandboxItemRenderCatalog = EMPTY_SANDBOX_ITEM_RENDER_CATALOG,
): void {
    const layer = getSandboxItemRenderLayer(item);
    if (layer == null) return;

    const px = item.position.x;
    const py = item.position.y;
    const cellX = ox + px * CELL_PX;
    const cellY = oy + py * CELL_PX;
    const cx = cellX + CELL_PX / 2;
    const cy = cellY + CELL_PX / 2;

    if (layer === 'region') {
        const color = item.color ?? DEFAULT_REGION_COLOR;
        g.fillStyle(hexToRgbInt(color), REGION_UNDERLAY_ALPHA);
        g.fillRect(cellX, cellY, CELL_PX, CELL_PX);
        return;
    }

    if (layer === 'solid') {
        if (isFixtureItem(item)) {
            const fixtureColor = item.color ?? '#8B5CF6';
            g.fillStyle(hexToRgbInt(fixtureColor), 1);
            g.fillRect(cellX + 4, cellY + 4, CELL_PX - 8, CELL_PX - 8);
            g.lineStyle(2, hexToRgbInt('#ffffff'), 0.6);
            g.strokeRect(cellX + 4, cellY + 4, CELL_PX - 8, CELL_PX - 8);
            return;
        }

        g.fillStyle(hexToRgbInt(WALL_FILL), 1);
        g.fillRect(cellX + 2, cellY + 2, CELL_PX - 4, CELL_PX - 4);
        return;
    }

    const visual = resolvePickableVisual(item, catalog);
    g.fillStyle(hexToRgbInt(visual.color), 1);
    if (visual.shape === 'square') {
        g.fillRect(cellX + 6, cellY + 6, CELL_PX - 12, CELL_PX - 12);
        return;
    }

    const radius = visual.isBall ? CELL_PX * 0.32 : CELL_PX * 0.28;
    g.fillCircle(cx, cy, radius);
    if (visual.isBall) {
        g.lineStyle(2, hexToRgbInt('#ffffff'), 0.85);
        g.strokeCircle(cx, cy, radius);
    }
}

export function buildSandboxItemRenderCatalog(
    itemDefinitions: ReadonlyArray<{
        id: string;
        shape: DefinitionShape;
        default_color?: string | null;
    }>,
): SandboxItemRenderCatalog {
    return { itemDefinitions };
}
