/**
 * Phaser-only module: swapping renderers means replacing this file + sandboxVisualDefaults.
 */
import Phaser from 'phaser';

import type { SandboxSandboxStateJson } from '../../domain/sandbox/types';
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
    SANDBOX_GRID_DEFAULT_HEIGHT,
    SANDBOX_GRID_DEFAULT_WIDTH,
    WALL_FILL,
    creatureColor,
} from '../sandboxVisualDefaults';

function hexToRgbInt(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
}

type CellHandler = (cell: { x: number; y: number }) => void;

class SandboxScene extends Phaser.Scene {
    private cellHandler: CellHandler | null = null;
    private graphics: Phaser.GameObjects.Graphics | null = null;
    private lastState: SandboxSandboxStateJson | null = null;
    private selectedCreatureId: string | null = null;

    constructor() {
        super({ key: 'SandboxScene' });
    }

    setCellHandler(h: CellHandler | null) {
        this.cellHandler = h;
    }

    setSelectedCreatureId(id: string | null) {
        this.selectedCreatureId = id;
        if (this.lastState) this.sync(this.lastState);
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
            const cx = ox + it.position.x * CELL_PX + CELL_PX / 2;
            const cy = oy + it.position.y * CELL_PX + CELL_PX / 2;
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
            }
        }

        state.creatures.forEach((creature, idx) => {
            const px = creature.position.x;
            const py = creature.position.y;
            const selected = creature.id === this.selectedCreatureId;
            const fill = selected ? CREATURE_SELECTED_FILL : creatureColor(idx);
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

    setState(state: SandboxSandboxStateJson, options?: SandboxSetStateOptions): void {
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
            if (options?.selectedCreatureId !== undefined) {
                scene.setSelectedCreatureId(options.selectedCreatureId);
            }
            scene.sync(state);
        }
    }

    setOnCellClick(handler: (cell: { x: number; y: number }) => void): void {
        this.scene?.setCellHandler(handler);
    }
}
