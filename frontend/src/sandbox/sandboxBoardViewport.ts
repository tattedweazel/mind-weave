import { BOARD_PADDING, CELL_PX } from './sandboxVisualDefaults';

/** Maximum zoom (2× native cell size). */
export const SANDBOX_BOARD_MAX_ZOOM = 2.0;

/** Padding fraction when fitting the board into the viewport (matches workflow editor). */
export const SANDBOX_BOARD_FIT_PADDING = 0.12;

/** Multiplicative step per control click (+ / −). */
export const SANDBOX_BOARD_ZOOM_STEP = 1.12;

/** Wheel delta divisor for smooth exponential zoom (see wheelDeltaToZoomFactor). */
export const SANDBOX_BOARD_WHEEL_DELTA_SCALE = 100;

/** Max pointer movement (px) before a left click is treated as pan, not cell select. */
export const SANDBOX_BOARD_PAN_DRAG_THRESHOLD_PX = 5;

export function boardWorldSizePx(gridW: number, gridH: number): { width: number; height: number } {
    return {
        width: BOARD_PADDING * 2 + gridW * CELL_PX,
        height: BOARD_PADDING * 2 + gridH * CELL_PX,
    };
}

export function computeFitZoom(
    viewportW: number,
    viewportH: number,
    worldW: number,
    worldH: number,
    padding = SANDBOX_BOARD_FIT_PADDING,
): number {
    if (viewportW <= 0 || viewportH <= 0 || worldW <= 0 || worldH <= 0) {
        return 1;
    }
    const innerW = viewportW * (1 - 2 * padding);
    const innerH = viewportH * (1 - 2 * padding);
    return Math.min(innerW / worldW, innerH / worldH);
}

/** Fit zoom capped at native 1× so small boards are not upscaled on fit. */
export function computeFitZoomLevel(
    viewportW: number,
    viewportH: number,
    worldW: number,
    worldH: number,
    padding = SANDBOX_BOARD_FIT_PADDING,
): number {
    return Math.min(computeFitZoom(viewportW, viewportH, worldW, worldH, padding), 1);
}

export function clampZoom(zoom: number, minZoom: number, maxZoom: number): number {
    return Math.min(maxZoom, Math.max(minZoom, zoom));
}

/**
 * Phaser 3 camera: screen (sx, sy) maps to world via scroll + viewport center offset.
 * worldView.x = scrollX + viewportW/2 - viewportW/(2*zoom)
 */
export function worldPointAtScreen(params: {
    scrollX: number;
    scrollY: number;
    screenX: number;
    screenY: number;
    zoom: number;
    viewportW: number;
    viewportH: number;
}): { worldX: number; worldY: number } {
    const { scrollX, scrollY, screenX, screenY, zoom, viewportW, viewportH } = params;
    return {
        worldX: scrollX + viewportW / 2 - viewportW / (2 * zoom) + screenX / zoom,
        worldY: scrollY + viewportH / 2 - viewportH / (2 * zoom) + screenY / zoom,
    };
}

/** Inverse of worldPointAtScreen — keeps a world point fixed under a screen point at zoom. */
export function scrollForWorldPointAtScreen(params: {
    worldX: number;
    worldY: number;
    screenX: number;
    screenY: number;
    zoom: number;
    viewportW: number;
    viewportH: number;
}): { scrollX: number; scrollY: number } {
    const { worldX, worldY, screenX, screenY, zoom, viewportW, viewportH } = params;
    return {
        scrollX: worldX - viewportW / 2 + viewportW / (2 * zoom) - screenX / zoom,
        scrollY: worldY - viewportH / 2 + viewportH / (2 * zoom) - screenY / zoom,
    };
}

/** Returns multiplicative zoom factor for a wheel delta (negative deltaY = zoom in). */
export function wheelDeltaToZoomFactor(
    deltaY: number,
    step = SANDBOX_BOARD_ZOOM_STEP,
    scale = SANDBOX_BOARD_WHEEL_DELTA_SCALE,
): number {
    if (deltaY === 0) return 1;
    return Math.pow(step, -deltaY / scale);
}

export function worldPointToGridCell(
    worldX: number,
    worldY: number,
    gridW: number,
    gridH: number,
): { x: number; y: number } | null {
    const lx = worldX - BOARD_PADDING;
    const ly = worldY - BOARD_PADDING;
    if (lx < 0 || ly < 0) return null;
    const gx = Math.floor(lx / CELL_PX);
    const gy = Math.floor(ly / CELL_PX);
    if (gx >= 0 && gx < gridW && gy >= 0 && gy < gridH) {
        return { x: gx, y: gy };
    }
    return null;
}

/** Cursor-anchored zoom using Phaser-correct scroll math. */
export function zoomAtAnchor(params: {
    scrollX: number;
    scrollY: number;
    zoom: number;
    anchorWorldX?: number;
    anchorWorldY?: number;
    screenX: number;
    screenY: number;
    viewportW: number;
    viewportH: number;
    factor: number;
    minZoom: number;
    maxZoom: number;
}): { scrollX: number; scrollY: number; zoom: number } {
    const newZoom = clampZoom(params.zoom * params.factor, params.minZoom, params.maxZoom);
    if (newZoom === params.zoom) {
        return { scrollX: params.scrollX, scrollY: params.scrollY, zoom: params.zoom };
    }

    const anchorWorld =
        params.anchorWorldX !== undefined && params.anchorWorldY !== undefined
            ? { worldX: params.anchorWorldX, worldY: params.anchorWorldY }
            : worldPointAtScreen({
                  scrollX: params.scrollX,
                  scrollY: params.scrollY,
                  screenX: params.screenX,
                  screenY: params.screenY,
                  zoom: params.zoom,
                  viewportW: params.viewportW,
                  viewportH: params.viewportH,
              });

    const scroll = scrollForWorldPointAtScreen({
        worldX: anchorWorld.worldX,
        worldY: anchorWorld.worldY,
        screenX: params.screenX,
        screenY: params.screenY,
        zoom: newZoom,
        viewportW: params.viewportW,
        viewportH: params.viewportH,
    });

    return { scrollX: scroll.scrollX, scrollY: scroll.scrollY, zoom: newZoom };
}

/** Fixed world bounds for Phaser clamp — letterbox margin + pan room at all zoom levels. */
export function computeStableCameraBounds(params: {
    viewportW: number;
    viewportH: number;
    worldW: number;
    worldH: number;
}): {
    boundsX: number;
    boundsY: number;
    boundsW: number;
    boundsH: number;
} {
    const marginX = params.viewportW / 2;
    const marginY = params.viewportH / 2;
    return {
        boundsX: -marginX,
        boundsY: -marginY,
        boundsW: params.worldW + params.viewportW,
        boundsH: params.worldH + params.viewportH,
    };
}

/** Fit scroll + stable bounds for a given zoom (centers board when scroll omitted). */
export function computeFitViewport(params: {
    viewportW: number;
    viewportH: number;
    worldW: number;
    worldH: number;
    zoom: number;
    scrollX?: number;
    scrollY?: number;
}): {
    scrollX: number;
    scrollY: number;
    boundsX: number;
    boundsY: number;
    boundsW: number;
    boundsH: number;
} {
    const scroll =
        params.scrollX !== undefined && params.scrollY !== undefined
            ? { scrollX: params.scrollX, scrollY: params.scrollY }
            : scrollForWorldPointAtScreen({
                  worldX: params.worldW / 2,
                  worldY: params.worldH / 2,
                  screenX: params.viewportW / 2,
                  screenY: params.viewportH / 2,
                  zoom: params.zoom,
                  viewportW: params.viewportW,
                  viewportH: params.viewportH,
              });

    const bounds = computeStableCameraBounds({
        viewportW: params.viewportW,
        viewportH: params.viewportH,
        worldW: params.worldW,
        worldH: params.worldH,
    });

    return {
        scrollX: scroll.scrollX,
        scrollY: scroll.scrollY,
        ...bounds,
    };
}
