/**
 * Phaser-only module: swapping renderers means replacing this file + sandboxVisualDefaults.
 */
import Phaser from 'phaser';

import type { SandboxSandboxStateJson } from '../../domain/sandbox/types';
import {
    boardWorldSizePx,
    computeFitViewport,
    computeFitZoomLevel,
    computeStableCameraBounds,
    SANDBOX_BOARD_FIT_PADDING,
    SANDBOX_BOARD_MAX_ZOOM,
    SANDBOX_BOARD_PAN_DRAG_THRESHOLD_PX,
    SANDBOX_BOARD_ZOOM_STEP,
    wheelDeltaToZoomFactor,
    worldPointToGridCell,
    zoomAtAnchor,
} from '../sandboxBoardViewport';
import type { SandboxRuntimeAdapter, SandboxSetStateOptions } from './types';
import {
    BOARD_BG,
    BOARD_PADDING,
    CELL_PX,
    CREATURE_FILL,
    CREATURE_SELECTED_FILL,
    DEFAULT_REGION_COLOR,
    FOOD_FILL,
    GRID_LINE,
    REGION_UNDERLAY_ALPHA,
    WALL_FILL,
    creatureColor,
} from '../sandboxVisualDefaults';

const VIEWPORT_RESIZE_DEBOUNCE_MS = 120;

function hexToRgbInt(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
}

type CellHandler = (cell: { x: number; y: number }) => void;

type ViewportController = {
    fitToView(): void;
    zoomIn(): void;
    zoomOut(): void;
    zoomAt(anchorX: number, anchorY: number, factor: number): void;
    updateWorldSize(worldW: number, worldH: number): void;
    resizeViewport(viewportW: number, viewportH: number): void;
};

class SandboxScene extends Phaser.Scene implements ViewportController {
    private cellHandler: CellHandler | null = null;
    private graphics: Phaser.GameObjects.Graphics | null = null;
    private lastState: SandboxSandboxStateJson | null = null;
    private selectedCreatureId: string | null = null;
    private worldW = 0;
    private worldH = 0;
    private viewportW = 0;
    private viewportH = 0;
    private lastPinchDistance: number | null = null;
    private readyHandler: (() => void) | null = null;
    private panActive = false;
    private panMoved = false;
    private panPointerStartX = 0;
    private panPointerStartY = 0;
    private panScrollStartX = 0;
    private panScrollStartY = 0;
    private panTotalDragPx = 0;

    constructor() {
        super({ key: 'SandboxScene' });
    }

    setReadyHandler(handler: (() => void) | null) {
        this.readyHandler = handler;
    }

    setCellHandler(h: CellHandler | null) {
        this.cellHandler = h;
    }

    setSelectedCreatureId(id: string | null) {
        this.selectedCreatureId = id;
        if (this.lastState) this.sync(this.lastState);
    }

    updateWorldSize(worldW: number, worldH: number) {
        this.worldW = worldW;
        this.worldH = worldH;
    }

    resizeViewport(viewportW: number, viewportH: number) {
        this.viewportW = viewportW;
        this.viewportH = viewportH;
    }

    private minZoom(): number {
        return computeFitZoomLevel(
            this.viewportW,
            this.viewportH,
            this.worldW,
            this.worldH,
            SANDBOX_BOARD_FIT_PADDING,
        );
    }

    private cameraBounds() {
        return computeStableCameraBounds({
            viewportW: this.viewportW,
            viewportH: this.viewportH,
            worldW: this.worldW,
            worldH: this.worldH,
        });
    }

    private applyCameraViewport(
        camera: Phaser.Cameras.Scene2D.Camera,
        zoom: number,
        scrollX?: number,
        scrollY?: number,
    ) {
        const viewport = computeFitViewport({
            viewportW: this.viewportW,
            viewportH: this.viewportH,
            worldW: this.worldW,
            worldH: this.worldH,
            zoom,
            scrollX,
            scrollY,
        });
        const bounds = this.cameraBounds();
        camera.setZoom(zoom);
        camera.setBounds(bounds.boundsX, bounds.boundsY, bounds.boundsW, bounds.boundsH);
        camera.setScroll(viewport.scrollX, viewport.scrollY);
    }

    fitToView() {
        if (
            !this.cameras?.main ||
            this.viewportW <= 0 ||
            this.viewportH <= 0 ||
            this.worldW <= 0 ||
            this.worldH <= 0
        ) {
            return;
        }
        this.applyCameraViewport(this.cameras.main, this.minZoom());
    }

    zoomAt(anchorX: number, anchorY: number, factor: number) {
        if (!this.cameras?.main || this.viewportW <= 0 || this.viewportH <= 0) return;
        const camera = this.cameras.main;
        const world = camera.getWorldPoint(anchorX, anchorY);
        const result = zoomAtAnchor({
            scrollX: camera.scrollX,
            scrollY: camera.scrollY,
            zoom: camera.zoom,
            anchorWorldX: world.x,
            anchorWorldY: world.y,
            screenX: anchorX,
            screenY: anchorY,
            viewportW: this.viewportW,
            viewportH: this.viewportH,
            factor,
            minZoom: this.minZoom(),
            maxZoom: SANDBOX_BOARD_MAX_ZOOM,
        });
        this.applyCameraViewport(camera, result.zoom, result.scrollX, result.scrollY);
    }

    zoomIn() {
        this.zoomAt(this.viewportW / 2, this.viewportH / 2, SANDBOX_BOARD_ZOOM_STEP);
    }

    zoomOut() {
        this.zoomAt(this.viewportW / 2, this.viewportH / 2, 1 / SANDBOX_BOARD_ZOOM_STEP);
    }

    private beginPan(pointer: Phaser.Input.Pointer, camera: Phaser.Cameras.Scene2D.Camera) {
        this.panActive = true;
        this.panMoved = false;
        this.panTotalDragPx = 0;
        this.panPointerStartX = pointer.x;
        this.panPointerStartY = pointer.y;
        this.panScrollStartX = camera.scrollX;
        this.panScrollStartY = camera.scrollY;
    }

    private updatePan(pointer: Phaser.Input.Pointer, camera: Phaser.Cameras.Scene2D.Camera) {
        if (!this.panActive) return;
        const dx = pointer.x - this.panPointerStartX;
        const dy = pointer.y - this.panPointerStartY;
        this.panTotalDragPx = Math.hypot(dx, dy);
        if (this.panTotalDragPx >= SANDBOX_BOARD_PAN_DRAG_THRESHOLD_PX) {
            this.panMoved = true;
        }
        const zoom = camera.zoom;
        this.applyCameraViewport(
            camera,
            zoom,
            this.panScrollStartX - dx / zoom,
            this.panScrollStartY - dy / zoom,
        );
    }

    private endPan(pointer: Phaser.Input.Pointer) {
        if (!this.panActive) return;
        const wasPan = this.panMoved;
        this.panActive = false;

        if (
            !wasPan &&
            pointer.leftButtonReleased() &&
            this.lastState &&
            this.cellHandler &&
            this.cameras?.main
        ) {
            const world = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
            const { width, height } = this.lastState.world.grid;
            const cell = worldPointToGridCell(world.x, world.y, width, height);
            if (cell) this.cellHandler(cell);
        }
    }

    create() {
        this.graphics = this.add.graphics();
        this.input.addPointer(2);

        this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
            if (!this.cameras?.main) return;
            if (pointer.middleButtonDown() || pointer.leftButtonDown()) {
                this.beginPan(pointer, this.cameras.main);
            }
        });

        this.input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
            if (!this.cameras?.main || !pointer.isDown) return;
            if (this.panActive) {
                this.updatePan(pointer, this.cameras.main);
            }
        });

        this.input.on('pointerup', (pointer: Phaser.Input.Pointer) => {
            this.endPan(pointer);
        });

        this.input.on('wheel', (pointer: Phaser.Input.Pointer) => {
            const factor = wheelDeltaToZoomFactor(pointer.deltaY);
            if (factor !== 1) {
                this.zoomAt(pointer.x, pointer.y, factor);
            }
        });

        this.input.on('pinchstart', () => {
            this.lastPinchDistance = null;
        });

        this.input.on(
            'pinch',
            (
                _pointer1: Phaser.Input.Pointer,
                _pointer2: Phaser.Input.Pointer,
                distance: number,
            ) => {
                if (this.lastPinchDistance != null && this.lastPinchDistance > 0) {
                    const factor = distance / this.lastPinchDistance;
                    if (Math.abs(factor - 1) > 0.001) {
                        this.zoomAt(this.viewportW / 2, this.viewportH / 2, factor);
                    }
                }
                this.lastPinchDistance = distance;
            },
        );

        this.input.on('pinchend', () => {
            this.lastPinchDistance = null;
        });

        // React may call setState before Phaser create(); replay deferred draw once graphics exist.
        if (this.lastState) {
            this.sync(this.lastState);
        }

        this.readyHandler?.();
    }

    sync(state: SandboxSandboxStateJson) {
        this.lastState = state;
        const g = this.graphics;
        if (!g) return;
        g.clear();
        const { width, height } = state.world.grid;
        const wpx = width * CELL_PX;
        const hpx = height * CELL_PX;
        const ox = BOARD_PADDING;
        const oy = BOARD_PADDING;

        g.fillStyle(hexToRgbInt(BOARD_BG), 1);
        g.fillRect(ox, oy, wpx, hpx);

        g.lineStyle(1, hexToRgbInt(GRID_LINE), 0.9);
        for (let x = 0; x <= width; x++) {
            g.lineBetween(ox + x * CELL_PX, oy, ox + x * CELL_PX, oy + hpx);
        }
        for (let y = 0; y <= height; y++) {
            g.lineBetween(ox, oy + y * CELL_PX, ox + wpx, oy + y * CELL_PX);
        }

        for (const it of state.world.items) {
            if (it.type === 'region') {
                const color = it.color ?? DEFAULT_REGION_COLOR;
                g.fillStyle(hexToRgbInt(color), REGION_UNDERLAY_ALPHA);
                g.fillRect(
                    ox + it.position.x * CELL_PX,
                    oy + it.position.y * CELL_PX,
                    CELL_PX,
                    CELL_PX,
                );
            }
        }

        for (const it of state.world.items) {
            const cx = ox + it.position.x * CELL_PX + CELL_PX / 2;
            const cy = oy + it.position.y * CELL_PX + CELL_PX / 2;
            if (it.type === 'wall') {
                g.fillStyle(hexToRgbInt(WALL_FILL), 1);
                g.fillRect(
                    ox + it.position.x * CELL_PX + 2,
                    oy + it.position.y * CELL_PX + 2,
                    CELL_PX - 4,
                    CELL_PX - 4,
                );
            } else if (it.type === 'food') {
                g.fillStyle(hexToRgbInt(FOOD_FILL), 1);
                g.fillCircle(cx, cy, CELL_PX * 0.28);
            } else if (it.type === 'ball') {
                const ballColor = it.color ?? '#F59E0B';
                g.fillStyle(hexToRgbInt(ballColor), 1);
                g.fillCircle(cx, cy, CELL_PX * 0.32);
                g.lineStyle(2, hexToRgbInt('#ffffff'), 0.85);
                g.strokeCircle(cx, cy, CELL_PX * 0.32);
            }
        }

        state.creatures.forEach((creature, idx) => {
            const px = creature.position.x;
            const py = creature.position.y;
            const selected = creature.id === this.selectedCreatureId;
            const fill = selected ? CREATURE_SELECTED_FILL : (creature.color ?? creatureColor(idx));
            const cx = ox + px * CELL_PX + CELL_PX / 2;
            const cy = oy + py * CELL_PX + CELL_PX / 2;
            const half = (CELL_PX - 8) / 2;
            g.fillStyle(hexToRgbInt(fill), 1);
            g.fillRect(ox + px * CELL_PX + 4, oy + py * CELL_PX + 4, CELL_PX - 8, CELL_PX - 8);
            const nose = CELL_PX * 0.18;
            g.fillStyle(hexToRgbInt('#ffffff'), 0.95);
            if (creature.facing === 'N') {
                g.fillTriangle(cx, cy - half + 2, cx - nose, cy - 2, cx + nose, cy - 2);
            } else if (creature.facing === 'E') {
                g.fillTriangle(cx + half - 2, cy, cx + 2, cy - nose, cx + 2, cy + nose);
            } else if (creature.facing === 'S') {
                g.fillTriangle(cx, cy + half - 2, cx - nose, cy + 2, cx + nose, cy + 2);
            } else {
                g.fillTriangle(cx - half + 2, cy, cx - 2, cy - nose, cx - 2, cy + nose);
            }
            if (selected) {
                g.lineStyle(2, hexToRgbInt(CREATURE_FILL), 1);
                g.strokeRect(ox + px * CELL_PX + 2, oy + py * CELL_PX + 2, CELL_PX - 4, CELL_PX - 4);
            }
        });
    }
}

export class PhaserSandboxAdapter implements SandboxRuntimeAdapter {
    private game: Phaser.Game | null = null;
    private scene: SandboxScene | null = null;
    private container: HTMLElement | null = null;
    private resizeObserver: ResizeObserver | null = null;
    private resizeDebounceId: ReturnType<typeof setTimeout> | null = null;
    private lastGridW = -1;
    private lastGridH = -1;
    private pendingFit = false;

    mount(container: HTMLElement): void {
        this.container = container;
        const scene = new SandboxScene();
        this.scene = scene;

        const initialW = Math.max(container.clientWidth, 320);
        const initialH = Math.max(container.clientHeight, 240);
        const defaultWorld = boardWorldSizePx(16, 16);
        scene.updateWorldSize(defaultWorld.width, defaultWorld.height);
        scene.resizeViewport(initialW, initialH);

        this.game = new Phaser.Game({
            type: Phaser.AUTO,
            parent: container,
            width: initialW,
            height: initialH,
            backgroundColor: '#020617',
            scene: [scene],
            scale: {
                mode: Phaser.Scale.NONE,
                autoCenter: Phaser.Scale.NO_CENTER,
            },
        });
        this.game.scale.resize(initialW, initialH);

        scene.setReadyHandler(() => {
            if (this.pendingFit) {
                this.pendingFit = false;
                scene.fitToView();
            }
        });

        this.resizeObserver = new ResizeObserver(() => {
            this.scheduleViewportResize();
        });
        this.resizeObserver.observe(container);
    }

    destroy(): void {
        if (this.resizeDebounceId != null) {
            clearTimeout(this.resizeDebounceId);
            this.resizeDebounceId = null;
        }
        this.resizeObserver?.disconnect();
        this.resizeObserver = null;
        this.container = null;
        this.game?.destroy(true);
        this.game = null;
        this.scene = null;
        this.lastGridW = -1;
        this.lastGridH = -1;
        this.pendingFit = false;
    }

    fitToView(): void {
        this.scene?.fitToView();
    }

    zoomIn(): void {
        this.scene?.zoomIn();
    }

    zoomOut(): void {
        this.scene?.zoomOut();
    }

    setState(state: SandboxSandboxStateJson, options?: SandboxSetStateOptions): void {
        const scene = this.scene;
        const game = this.game;
        if (!scene || !game) return;

        const { width, height } = state.world.grid;
        const gridChanged = width !== this.lastGridW || height !== this.lastGridH;
        if (gridChanged) {
            this.lastGridW = width;
            this.lastGridH = height;
            const world = boardWorldSizePx(width, height);
            scene.updateWorldSize(world.width, world.height);
            this.pendingFit = true;
        }

        if (options?.selectedCreatureId !== undefined) {
            scene.setSelectedCreatureId(options.selectedCreatureId);
        }
        scene.sync(state);

        // Keep pendingFit until the scene is active so mount()'s readyHandler can fit after create().
        if (this.pendingFit && scene.sys?.isActive()) {
            this.pendingFit = false;
            scene.fitToView();
        }
    }

    setOnCellClick(handler: (cell: { x: number; y: number }) => void): void {
        this.scene?.setCellHandler(handler);
    }

    private scheduleViewportResize(): void {
        if (this.resizeDebounceId != null) {
            clearTimeout(this.resizeDebounceId);
        }
        this.resizeDebounceId = setTimeout(() => {
            this.resizeDebounceId = null;
            this.applyViewportResize(true);
        }, VIEWPORT_RESIZE_DEBOUNCE_MS);
    }

    private applyViewportResize(fit: boolean): void {
        const container = this.container;
        const game = this.game;
        const scene = this.scene;
        if (!container || !game || !scene) return;

        const w = Math.max(container.clientWidth, 1);
        const h = Math.max(container.clientHeight, 1);
        if (w === game.scale.width && h === game.scale.height && !fit) {
            return;
        }
        game.scale.resize(w, h);
        scene.resizeViewport(w, h);
        if (fit) {
            scene.fitToView();
        }
    }
}
