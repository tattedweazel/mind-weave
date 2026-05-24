import { describe, expect, it } from 'vitest';

import { BOARD_PADDING, CELL_PX } from './sandboxVisualDefaults';
import {
    boardWorldSizePx,
    clampZoom,
    computeFitViewport,
    computeFitZoom,
    computeFitZoomLevel,
    computeStableCameraBounds,
    SANDBOX_BOARD_FIT_PADDING,
    SANDBOX_BOARD_MAX_ZOOM,
    SANDBOX_BOARD_WHEEL_DELTA_SCALE,
    SANDBOX_BOARD_ZOOM_STEP,
    scrollForWorldPointAtScreen,
    wheelDeltaToZoomFactor,
    worldPointAtScreen,
    worldPointToGridCell,
    zoomAtAnchor,
} from './sandboxBoardViewport';

describe('boardWorldSizePx', () => {
    it('includes padding and cell dimensions', () => {
        expect(boardWorldSizePx(16, 16)).toEqual({
            width: BOARD_PADDING * 2 + 16 * CELL_PX,
            height: BOARD_PADDING * 2 + 16 * CELL_PX,
        });
    });
});

describe('computeFitZoom', () => {
    it('fits the larger axis with padding', () => {
        const world = boardWorldSizePx(64, 64);
        const zoom = computeFitZoom(800, 600, world.width, world.height, SANDBOX_BOARD_FIT_PADDING);
        const innerW = 800 * (1 - 2 * SANDBOX_BOARD_FIT_PADDING);
        const innerH = 600 * (1 - 2 * SANDBOX_BOARD_FIT_PADDING);
        expect(zoom).toBe(Math.min(innerW / world.width, innerH / world.height));
    });

    it('returns 1 for non-positive dimensions', () => {
        expect(computeFitZoom(0, 600, 100, 100)).toBe(1);
        expect(computeFitZoom(800, 0, 100, 100)).toBe(1);
    });
});

describe('computeFitZoomLevel', () => {
    it('caps fit zoom at 1 for small boards', () => {
        const world = boardWorldSizePx(9, 9);
        const raw = computeFitZoom(800, 600, world.width, world.height, SANDBOX_BOARD_FIT_PADDING);
        expect(raw).toBeGreaterThan(1);
        expect(computeFitZoomLevel(800, 600, world.width, world.height, SANDBOX_BOARD_FIT_PADDING)).toBe(
            1,
        );
    });

    it('matches computeFitZoom for large boards', () => {
        const world = boardWorldSizePx(64, 64);
        expect(computeFitZoomLevel(800, 600, world.width, world.height, SANDBOX_BOARD_FIT_PADDING)).toBe(
            computeFitZoom(800, 600, world.width, world.height, SANDBOX_BOARD_FIT_PADDING),
        );
    });
});

describe('clampZoom', () => {
    it('clamps to min and max', () => {
        expect(clampZoom(0.01, 0.05, 2)).toBe(0.05);
        expect(clampZoom(5, 0.05, 2)).toBe(2);
        expect(clampZoom(1, 0.05, 2)).toBe(1);
    });
});

describe('worldPointAtScreen / scrollForWorldPointAtScreen', () => {
    it('round-trips a world point through screen coordinates', () => {
        const viewportW = 640;
        const viewportH = 480;
        const zoom = 1.5;
        const scrollX = 12;
        const scrollY = -8;
        const screenX = 200;
        const screenY = 150;

        const world = worldPointAtScreen({
            scrollX,
            scrollY,
            screenX,
            screenY,
            zoom,
            viewportW,
            viewportH,
        });
        const scroll = scrollForWorldPointAtScreen({
            worldX: world.worldX,
            worldY: world.worldY,
            screenX,
            screenY,
            zoom,
            viewportW,
            viewportH,
        });

        expect(scroll.scrollX).toBeCloseTo(scrollX);
        expect(scroll.scrollY).toBeCloseTo(scrollY);
    });
});

describe('wheelDeltaToZoomFactor', () => {
    it('zooms in on negative deltaY with magnitude scaling', () => {
        expect(wheelDeltaToZoomFactor(-SANDBOX_BOARD_WHEEL_DELTA_SCALE)).toBeCloseTo(
            SANDBOX_BOARD_ZOOM_STEP,
        );
    });

    it('zooms out on positive deltaY with magnitude scaling', () => {
        expect(wheelDeltaToZoomFactor(SANDBOX_BOARD_WHEEL_DELTA_SCALE)).toBeCloseTo(
            1 / SANDBOX_BOARD_ZOOM_STEP,
        );
    });

    it('applies partial step for smaller deltas', () => {
        const factor = wheelDeltaToZoomFactor(-50);
        expect(factor).toBeGreaterThan(1);
        expect(factor).toBeLessThan(SANDBOX_BOARD_ZOOM_STEP);
    });

    it('returns 1 for zero delta', () => {
        expect(wheelDeltaToZoomFactor(0)).toBe(1);
    });
});

describe('worldPointToGridCell', () => {
    it('maps world coordinates to grid cells', () => {
        const cell = worldPointToGridCell(
            BOARD_PADDING + CELL_PX * 2 + 10,
            BOARD_PADDING + CELL_PX * 3 + 5,
            16,
            16,
        );
        expect(cell).toEqual({ x: 2, y: 3 });
    });

    it('returns null outside the grid', () => {
        expect(worldPointToGridCell(0, 0, 16, 16)).toBeNull();
        expect(
            worldPointToGridCell(BOARD_PADDING + 16 * CELL_PX, BOARD_PADDING, 16, 16),
        ).toBeNull();
    });
});

describe('zoomAtAnchor', () => {
    const viewportW = 640;
    const viewportH = 480;

    function anchorWorldAfter(params: {
        scrollX: number;
        scrollY: number;
        zoom: number;
        screenX: number;
        screenY: number;
    }) {
        return worldPointAtScreen({ ...params, viewportW, viewportH });
    }

    it('keeps the anchor world point fixed when zooming in at zoom 0.5', () => {
        const before = { scrollX: 10, scrollY: 20, zoom: 0.5 };
        const screenX = 200;
        const screenY = 150;
        const beforeWorld = anchorWorldAfter({ ...before, screenX, screenY });

        const after = zoomAtAnchor({
            ...before,
            screenX,
            screenY,
            viewportW,
            viewportH,
            factor: SANDBOX_BOARD_ZOOM_STEP,
            minZoom: 0.01,
            maxZoom: SANDBOX_BOARD_MAX_ZOOM,
        });

        const afterWorld = anchorWorldAfter({
            scrollX: after.scrollX,
            scrollY: after.scrollY,
            zoom: after.zoom,
            screenX,
            screenY,
        });

        expect(afterWorld.worldX).toBeCloseTo(beforeWorld.worldX);
        expect(afterWorld.worldY).toBeCloseTo(beforeWorld.worldY);
        expect(after.zoom).toBeGreaterThan(before.zoom);
    });

    it('keeps the anchor world point fixed when zooming in at zoom 1.5', () => {
        const before = { scrollX: -40, scrollY: 30, zoom: 1.5 };
        const screenX = 320;
        const screenY = 240;
        const beforeWorld = anchorWorldAfter({ ...before, screenX, screenY });

        const after = zoomAtAnchor({
            ...before,
            screenX,
            screenY,
            viewportW,
            viewportH,
            factor: SANDBOX_BOARD_ZOOM_STEP,
            minZoom: 0.01,
            maxZoom: SANDBOX_BOARD_MAX_ZOOM,
        });

        const afterWorld = anchorWorldAfter({
            scrollX: after.scrollX,
            scrollY: after.scrollY,
            zoom: after.zoom,
            screenX,
            screenY,
        });

        expect(afterWorld.worldX).toBeCloseTo(beforeWorld.worldX);
        expect(afterWorld.worldY).toBeCloseTo(beforeWorld.worldY);
    });

    it('does not change when already at max zoom and zooming in', () => {
        const result = zoomAtAnchor({
            scrollX: 0,
            scrollY: 0,
            zoom: SANDBOX_BOARD_MAX_ZOOM,
            screenX: 100,
            screenY: 100,
            viewportW,
            viewportH,
            factor: SANDBOX_BOARD_ZOOM_STEP,
            minZoom: 0.1,
            maxZoom: SANDBOX_BOARD_MAX_ZOOM,
        });
        expect(result.zoom).toBe(SANDBOX_BOARD_MAX_ZOOM);
    });
});

describe('computeStableCameraBounds', () => {
    it('expands world bounds by half the viewport for letterbox and pan', () => {
        const world = boardWorldSizePx(16, 16);
        const bounds = computeStableCameraBounds({
            viewportW: 800,
            viewportH: 600,
            worldW: world.width,
            worldH: world.height,
        });

        expect(bounds.boundsX).toBe(-400);
        expect(bounds.boundsY).toBe(-300);
        expect(bounds.boundsW).toBe(world.width + 800);
        expect(bounds.boundsH).toBe(world.height + 600);
    });
});

describe('computeFitViewport', () => {
    it('centers a small board with negative scroll and stable bounds', () => {
        const world = boardWorldSizePx(9, 9);
        const viewportW = 800;
        const viewportH = 600;
        const viewport = computeFitViewport({
            viewportW,
            viewportH,
            worldW: world.width,
            worldH: world.height,
            zoom: 1,
        });

        expect(viewport.scrollX).toBe((world.width - viewportW) / 2);
        expect(viewport.scrollY).toBe((world.height - viewportH) / 2);
        expect(viewport.scrollX).toBeLessThan(0);
        expect(viewport.boundsX).toBe(-viewportW / 2);
        expect(viewport.boundsY).toBe(-viewportH / 2);
    });

    it('centers a large board at fit zoom with stable bounds', () => {
        const world = boardWorldSizePx(64, 64);
        const viewportW = 800;
        const viewportH = 600;
        const zoom = computeFitZoomLevel(viewportW, viewportH, world.width, world.height, SANDBOX_BOARD_FIT_PADDING);
        const viewport = computeFitViewport({
            viewportW,
            viewportH,
            worldW: world.width,
            worldH: world.height,
            zoom,
        });

        expect(viewport.scrollX).toBeCloseTo(world.width / 2 - viewportW / 2);
        expect(viewport.scrollY).toBeCloseTo(world.height / 2 - viewportH / 2);
        expect(viewport.boundsX).toBe(-viewportW / 2);
        expect(viewport.boundsY).toBe(-viewportH / 2);
    });

    it('preserves explicit scroll when computing bounds after zoom', () => {
        const world = boardWorldSizePx(9, 9);
        const viewport = computeFitViewport({
            viewportW: 800,
            viewportH: 600,
            worldW: world.width,
            worldH: world.height,
            zoom: 1.5,
            scrollX: 12,
            scrollY: -8,
        });

        expect(viewport.scrollX).toBe(12);
        expect(viewport.scrollY).toBe(-8);
        expect(viewport.boundsX).toBe(-400);
        expect(viewport.boundsY).toBe(-300);
    });
});
