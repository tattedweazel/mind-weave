/**
 * Phaser-only module: swapping renderers means replacing this file + sandboxVisualDefaults.
 */
import Phaser from 'phaser';

import type { SandboxSandboxStateJson } from '../../domain/sandbox/types';
import type { SandboxRuntimeAdapter } from './types';
import {
    BOARD_BG,
    BOARD_PADDING,
    CELL_PX,
    FOOD_FILL,
    GRID_LINE,
    PET_FILL,
    SANDBOX_GRID_DEFAULT_HEIGHT,
    SANDBOX_GRID_DEFAULT_WIDTH,
} from '../sandboxVisualDefaults';

function hexToRgbInt(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
}

type CellHandler = (cell: { x: number; y: number }) => void;

class SandboxScene extends Phaser.Scene {
    private cellHandler: CellHandler | null = null;
    private graphics: Phaser.GameObjects.Graphics | null = null;
    private lastState: SandboxSandboxStateJson | null = null;

    constructor() {
        super({ key: 'SandboxScene' });
    }

    setCellHandler(h: CellHandler | null) {
        this.cellHandler = h;
    }

    create() {
        this.graphics = this.add.graphics();
        this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
            if (!this.lastState || !this.cellHandler) return;
            const ox = BOARD_PADDING;
            const oy = BOARD_PADDING;
            const lx = pointer.x - ox;
            const ly = pointer.y - oy;
            if (lx < 0 || ly < 0) return;
            const gx = Math.floor(lx / CELL_PX);
            const gy = Math.floor(ly / CELL_PX);
            const { width, height } = this.lastState.world.grid;
            if (gx >= 0 && gx < width && gy >= 0 && gy < height) {
                this.cellHandler({ x: gx, y: gy });
            }
        });
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
            if (it.type !== 'food') continue;
            const cx = ox + it.position.x * CELL_PX + CELL_PX / 2;
            const cy = oy + it.position.y * CELL_PX + CELL_PX / 2;
            g.fillStyle(hexToRgbInt(FOOD_FILL), 1);
            g.fillCircle(cx, cy, CELL_PX * 0.28);
        }

        const px = state.pet.position.x;
        const py = state.pet.position.y;
        g.fillStyle(hexToRgbInt(PET_FILL), 1);
        g.fillRect(ox + px * CELL_PX + 4, oy + py * CELL_PX + 4, CELL_PX - 8, CELL_PX - 8);
    }
}

export class PhaserSandboxAdapter implements SandboxRuntimeAdapter {
    private game: Phaser.Game | null = null;
    private scene: SandboxScene | null = null;
    /** Last grid dimensions used for scale.resize — avoid FIT/resize feedback loops each tick. */
    private lastGridW = -1;
    private lastGridH = -1;

    mount(container: HTMLElement): void {
        const scene = new SandboxScene();
        this.scene = scene;
        const initialW = BOARD_PADDING * 2 + SANDBOX_GRID_DEFAULT_WIDTH * CELL_PX;
        const initialH = BOARD_PADDING * 2 + SANDBOX_GRID_DEFAULT_HEIGHT * CELL_PX;
        this.lastGridW = SANDBOX_GRID_DEFAULT_WIDTH;
        this.lastGridH = SANDBOX_GRID_DEFAULT_HEIGHT;
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
    }

    destroy(): void {
        this.game?.destroy(true);
        this.game = null;
        this.scene = null;
        this.lastGridW = -1;
        this.lastGridH = -1;
    }

    setState(state: SandboxSandboxStateJson): void {
        const scene = this.scene;
        const game = this.game;
        if (scene && game) {
            const { width, height } = state.world.grid;
            if (width !== this.lastGridW || height !== this.lastGridH) {
                this.lastGridW = width;
                this.lastGridH = height;
                const wpx = BOARD_PADDING * 2 + width * CELL_PX;
                const hpx = BOARD_PADDING * 2 + height * CELL_PX;
                game.scale.resize(wpx, hpx);
            }
            scene.sync(state);
        }
    }

    setOnCellClick(handler: (cell: { x: number; y: number }) => void): void {
        this.scene?.setCellHandler(handler);
    }
}
