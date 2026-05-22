import { afterEach, describe, expect, it, vi } from 'vitest';

const resizeSpy = vi.fn();
const destroySpy = vi.fn();

vi.mock('phaser', () => {
    class MockScene {
        key: string;
        constructor(config: { key: string }) {
            this.key = config.key;
        }
    }
    class MockGame {
        scale = { resize: resizeSpy };
        destroy = destroySpy;
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

describe('PhaserSandboxAdapter', () => {
    afterEach(() => {
        resizeSpy.mockClear();
        destroySpy.mockClear();
    });

    it('calls scale.resize only when grid dimensions change', () => {
        const adapter = new PhaserSandboxAdapter();
        const el = document.createElement('div');
        adapter.mount(el);

        const base = {
            tick: 1,
            creatures: [
                {
                    id: 'c1',
                    workflow_id: 'wf-1',
                    position: { x: 0, y: 0 },
                    facing: 'N' as const,
                },
            ],
            world: {
                grid: { width: 16, height: 16 },
                items: [],
            },
            recent_actions: [],
        };

        adapter.setState(base);
        adapter.setState(base);
        adapter.setState({ ...base, world: { ...base.world, grid: { width: 9, height: 16 } } });
        adapter.setState({ ...base, world: { ...base.world, grid: { width: 9, height: 16 } } });

        expect(resizeSpy).toHaveBeenCalledTimes(1);

        adapter.destroy();
    });
});
