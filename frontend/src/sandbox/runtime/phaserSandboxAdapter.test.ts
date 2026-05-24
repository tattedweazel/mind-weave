import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
    SANDBOX_BOARD_WHEEL_DELTA_SCALE,
    SANDBOX_BOARD_ZOOM_STEP,
    worldPointAtScreen,
} from '../sandboxBoardViewport';
import { BOARD_PADDING, CELL_PX } from '../sandboxVisualDefaults';

const resizeSpy = vi.fn();
const destroySpy = vi.fn();

let resizeObserverCallback: ResizeObserverCallback | null = null;
let lastResizeObserver: { observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> } | null =
    null;

type MockPointer = {
    x: number;
    y: number;
    deltaY?: number;
    isDown: boolean;
    middleButtonDown: () => boolean;
    leftButtonDown: () => boolean;
    leftButtonReleased: () => boolean;
};

type MockSceneInstance = {
    key: string;
    input: {
        on: ReturnType<typeof vi.fn>;
        addPointer: ReturnType<typeof vi.fn>;
        handlers: Record<string, Array<(pointer: MockPointer) => void>>;
    };
    cameras: {
        main: {
            zoom: number;
            scrollX: number;
            scrollY: number;
            width: number;
            height: number;
            setZoom: ReturnType<typeof vi.fn>;
            setScroll: ReturnType<typeof vi.fn>;
            setBounds: ReturnType<typeof vi.fn>;
            getWorldPoint: ReturnType<typeof vi.fn>;
        };
    };
    add: { graphics: ReturnType<typeof vi.fn> };
    sys: { isActive: () => boolean };
    create?: () => void;
};

let lastMountedScene: MockSceneInstance | null = null;

class MockResizeObserver {
    observe = vi.fn();
    disconnect = vi.fn();
    constructor(callback: ResizeObserverCallback) {
        resizeObserverCallback = callback;
        lastResizeObserver = this;
    }
}

vi.stubGlobal('ResizeObserver', MockResizeObserver);

function mockGraphics() {
    return {
        clear: vi.fn(),
        fillStyle: vi.fn(),
        fillRect: vi.fn(),
        lineStyle: vi.fn(),
        lineBetween: vi.fn(),
        fillCircle: vi.fn(),
        strokeCircle: vi.fn(),
        fillTriangle: vi.fn(),
        strokeRect: vi.fn(),
    };
}

function mockPointer(overrides: Partial<MockPointer> = {}): MockPointer {
    return {
        x: 100,
        y: 100,
        isDown: true,
        middleButtonDown: () => false,
        leftButtonDown: () => true,
        leftButtonReleased: () => true,
        ...overrides,
    };
}

vi.mock('phaser', () => {
    class MockScene {
        key: string;
        input: MockSceneInstance['input'];
        cameras: MockSceneInstance['cameras'];
        add: MockSceneInstance['add'];
        sys = { isActive: () => true };

        constructor(config?: { key: string }) {
            this.key = config?.key ?? '';
            const handlers: Record<string, Array<(pointer: MockPointer) => void>> = {};
            this.input = {
                handlers,
                addPointer: vi.fn(),
                on: vi.fn((event: string, handler: (pointer: MockPointer) => void) => {
                    if (!handlers[event]) handlers[event] = [];
                    handlers[event].push(handler);
                }),
            };
            const mainCamera = {
                zoom: 1,
                scrollX: 0,
                scrollY: 0,
                width: 640,
                height: 480,
                setZoom: vi.fn(function (this: { zoom: number }, zoom: number) {
                    this.zoom = zoom;
                }),
                setScroll: vi.fn(function (this: { scrollX: number; scrollY: number }, x: number, y: number) {
                    this.scrollX = x;
                    this.scrollY = y;
                }),
                setBounds: vi.fn(),
                getWorldPoint: vi.fn(function (
                    this: {
                        scrollX: number;
                        scrollY: number;
                        zoom: number;
                        width: number;
                        height: number;
                    },
                    x: number,
                    y: number,
                ) {
                    const world = worldPointAtScreen({
                        scrollX: this.scrollX,
                        scrollY: this.scrollY,
                        screenX: x,
                        screenY: y,
                        zoom: this.zoom,
                        viewportW: this.width,
                        viewportH: this.height,
                    });
                    return { x: world.worldX, y: world.worldY };
                }),
            };
            this.cameras = { main: mainCamera };
            this.add = { graphics: vi.fn(() => mockGraphics()) };
        }
    }

    class MockGame {
        scale = { width: 0, height: 0, resize: resizeSpy };
        destroy = destroySpy;

        constructor(config: { scene?: MockSceneInstance[] }) {
            for (const scene of config.scene ?? []) {
                lastMountedScene = scene;
                scene.create?.();
            }
        }
    }

    return {
        default: {
            AUTO: 0,
            Scale: {
                NONE: 0,
                NO_CENTER: 0,
                FIT: 1,
                CENTER_BOTH: 1,
            },
            Game: MockGame,
            Scene: MockScene,
        },
    };
});

import { PhaserSandboxAdapter } from './phaserSandboxAdapter';

function sizedContainer(width: number, height: number): HTMLDivElement {
    const el = document.createElement('div');
    Object.defineProperty(el, 'clientWidth', { value: width, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: height, configurable: true });
    return el;
}

const baseState = {
    tick: 1,
    creatures: [] as const,
    world: {
        grid: { width: 16, height: 16 },
        items: [] as const,
    },
    recent_actions: [] as const,
};

function firePointerEvent(scene: MockSceneInstance, event: string, pointer: MockPointer) {
    for (const handler of scene.input.handlers[event] ?? []) {
        handler(pointer);
    }
}

describe('PhaserSandboxAdapter', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        resizeObserverCallback = null;
        lastResizeObserver = null;
        lastMountedScene = null;
    });

    afterEach(() => {
        vi.useRealTimers();
        resizeSpy.mockClear();
        destroySpy.mockClear();
    });

    it('sizes the game to the viewport on mount', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = sizedContainer(640, 480);
        adapter.mount(el);

        expect(resizeSpy).toHaveBeenCalledWith(640, 480);
        expect(resizeObserverCallback).not.toBeNull();

        adapter.destroy();
    });

    it('does not call scale.resize again when grid dimensions change', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = sizedContainer(640, 480);
        adapter.mount(el);
        resizeSpy.mockClear();

        adapter.setState(baseState);
        adapter.setState(baseState);
        adapter.setState({ ...baseState, world: { ...baseState.world, grid: { width: 9, height: 16 } } });
        adapter.setState({ ...baseState, world: { ...baseState.world, grid: { width: 9, height: 16 } } });

        expect(resizeSpy).not.toHaveBeenCalled();

        adapter.destroy();
    });

    it('debounces viewport resize and refits', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = sizedContainer(640, 480);
        adapter.mount(el);
        resizeSpy.mockClear();

        Object.defineProperty(el, 'clientWidth', { value: 800, configurable: true });
        Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true });
        resizeObserverCallback?.([], {} as ResizeObserver);

        expect(resizeSpy).not.toHaveBeenCalled();
        vi.advanceTimersByTime(120);
        expect(resizeSpy).toHaveBeenCalledWith(800, 600);

        adapter.destroy();
    });

    it('disconnects ResizeObserver on destroy', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = sizedContainer(640, 480);
        adapter.mount(el);
        adapter.destroy();
        expect(lastResizeObserver?.disconnect).toHaveBeenCalled();
        expect(destroySpy).toHaveBeenCalled();
    });

    it('zooms in when the wheel handler receives pointer.deltaY', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = sizedContainer(640, 480);
        adapter.mount(el);

        const scene = lastMountedScene!;
        expect(scene.input.handlers.wheel).toHaveLength(1);

        const camera = scene.cameras.main;
        camera.zoom = 1;
        camera.scrollX = 0;
        camera.scrollY = 0;

        firePointerEvent(scene, 'wheel', mockPointer({ x: 100, y: 200, deltaY: -SANDBOX_BOARD_WHEEL_DELTA_SCALE }));

        expect(camera.setZoom).toHaveBeenCalled();
        expect(camera.zoom).toBeCloseTo(SANDBOX_BOARD_ZOOM_STEP);
        expect(camera.setScroll).toHaveBeenCalled();

        adapter.destroy();
    });

    it('preserves the anchor world point when wheel zooming', () => {
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(sizedContainer(640, 480));
        const scene = lastMountedScene!;
        const camera = scene.cameras.main;
        camera.zoom = 1.25;
        camera.scrollX = 20;
        camera.scrollY = -10;

        const screenX = 180;
        const screenY = 220;
        const beforeWorld = worldPointAtScreen({
            scrollX: camera.scrollX,
            scrollY: camera.scrollY,
            screenX,
            screenY,
            zoom: camera.zoom,
            viewportW: 640,
            viewportH: 480,
        });

        firePointerEvent(scene, 'wheel', mockPointer({ x: screenX, y: screenY, deltaY: -50 }));

        const afterWorld = worldPointAtScreen({
            scrollX: camera.scrollX,
            scrollY: camera.scrollY,
            screenX,
            screenY,
            zoom: camera.zoom,
            viewportW: 640,
            viewportH: 480,
        });

        expect(afterWorld.worldX).toBeCloseTo(beforeWorld.worldX);
        expect(afterWorld.worldY).toBeCloseTo(beforeWorld.worldY);

        adapter.destroy();
    });

    it('ignores wheel events with zero deltaY', () => {
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(sizedContainer(640, 480));

        const scene = lastMountedScene!;
        const camera = scene.cameras.main;
        camera.zoom = 1;

        firePointerEvent(scene, 'wheel', mockPointer({ deltaY: 0 }));

        expect(camera.setZoom).not.toHaveBeenCalled();

        adapter.destroy();
    });

    it('pans the camera on pointer drag', () => {
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(sizedContainer(640, 480));
        const scene = lastMountedScene!;
        const camera = scene.cameras.main;
        camera.scrollX = 50;
        camera.scrollY = 30;

        firePointerEvent(scene, 'pointerdown', mockPointer({ x: 100, y: 100, isDown: true }));
        firePointerEvent(scene, 'pointermove', mockPointer({ x: 130, y: 110, isDown: true }));
        firePointerEvent(scene, 'pointerup', mockPointer({ x: 130, y: 110, isDown: false }));

        expect(camera.scrollX).toBeCloseTo(50 - 30);
        expect(camera.scrollY).toBeCloseTo(30 - 10);

        adapter.destroy();
    });

    it('fires cell click on short left click but not after pan drag', () => {
        const adapter = new PhaserSandboxAdapter();
        adapter.mount(sizedContainer(640, 480));
        adapter.setState(baseState);

        const scene = lastMountedScene!;
        const camera = scene.cameras.main;
        camera.zoom = 1;
        camera.scrollX = 0;
        camera.scrollY = 0;

        const cellHandler = vi.fn();
        adapter.setOnCellClick(cellHandler);

        const wx = BOARD_PADDING + CELL_PX / 2;
        const wy = BOARD_PADDING + CELL_PX / 2;

        firePointerEvent(scene, 'pointerdown', mockPointer({ x: wx, y: wy }));
        firePointerEvent(scene, 'pointerup', mockPointer({ x: wx, y: wy, isDown: false }));

        expect(cellHandler).toHaveBeenCalledWith({ x: 0, y: 0 });

        cellHandler.mockClear();

        firePointerEvent(scene, 'pointerdown', mockPointer({ x: 100, y: 100 }));
        firePointerEvent(scene, 'pointermove', mockPointer({ x: 140, y: 100, isDown: true }));
        firePointerEvent(scene, 'pointerup', mockPointer({ x: 140, y: 100, isDown: false }));

        expect(cellHandler).not.toHaveBeenCalled();

        adapter.destroy();
    });
});
