import { describe, expect, it, vi } from 'vitest';

import type { SandboxItemJson } from '../domain/sandbox/types';
import {
    drawSandboxItem,
    getSandboxItemRenderLayer,
    resolvePickableVisual,
    SANDBOX_ITEM_RENDER_LAYERS,
} from './sandboxItemRender';

function mockGraphics() {
    return {
        fillStyle: vi.fn(),
        fillRect: vi.fn(),
        fillCircle: vi.fn(),
        lineStyle: vi.fn(),
        strokeCircle: vi.fn(),
        strokeRect: vi.fn(),
    };
}

function drawItemsInLayerOrder(
    items: SandboxItemJson[],
    catalog = { itemDefinitions: [] as const },
) {
    const g = mockGraphics();
    for (const layer of SANDBOX_ITEM_RENDER_LAYERS) {
        for (const item of items) {
            if (getSandboxItemRenderLayer(item) === layer) {
                drawSandboxItem(g, item, 8, 8, catalog);
            }
        }
    }
    return g;
}

describe('getSandboxItemRenderLayer', () => {
    it('classifies stacked cell occupants into region, solid, and pickable layers', () => {
        const region: SandboxItemJson = {
            id: 'r1',
            type: 'region',
            position: { x: 0, y: 0 },
            color: '#3B82F6',
        };
        const fixture: SandboxItemJson = {
            id: 'fx1',
            type: 'fixture',
            definition_kind: 'fixture',
            role: 'solid',
            definition_id: 'fx-def-1',
            position: { x: 0, y: 0 },
        };
        const pickable: SandboxItemJson = {
            id: 'p1',
            definition_kind: 'item',
            role: 'pickable',
            definition_id: 'item-def-1',
            color: '#FFFFFF',
            position: { x: 0, y: 0 },
        };

        expect(getSandboxItemRenderLayer(region)).toBe('region');
        expect(getSandboxItemRenderLayer(fixture)).toBe('solid');
        expect(getSandboxItemRenderLayer(pickable)).toBe('pickable');
    });
});

describe('resolvePickableVisual', () => {
    const catalog = {
        itemDefinitions: [
            { id: 'item-def-circle', shape: 'circle' as const, default_color: '#EEEEEE' },
            { id: 'item-def-square', shape: 'square' as const, default_color: '#CCCCCC' },
        ],
    };

    it('uses instance color and definition shape when both are present', () => {
        expect(
            resolvePickableVisual(
                {
                    id: 'p1',
                    definition_kind: 'item',
                    role: 'pickable',
                    definition_id: 'item-def-circle',
                    color: '#FFFFFF',
                    position: { x: 0, y: 0 },
                },
                catalog,
            ),
        ).toEqual({ color: '#FFFFFF', shape: 'circle', isBall: true });
    });

    it('uses circle shape without ball stroke when instance color is absent', () => {
        expect(
            resolvePickableVisual(
                {
                    id: 'p1b',
                    definition_kind: 'item',
                    role: 'pickable',
                    definition_id: 'item-def-circle',
                    position: { x: 0, y: 0 },
                },
                catalog,
            ),
        ).toEqual({ color: '#EEEEEE', shape: 'circle', isBall: false });
    });

    it('falls back to definition default_color when instance color is missing', () => {
        expect(
            resolvePickableVisual(
                {
                    id: 'p2',
                    definition_kind: 'item',
                    role: 'pickable',
                    definition_id: 'item-def-square',
                    position: { x: 0, y: 0 },
                },
                catalog,
            ),
        ).toEqual({ color: '#CCCCCC', shape: 'square', isBall: false });
    });

    it('marks built-in ball items for stroke rendering', () => {
        expect(
            resolvePickableVisual(
                {
                    id: 'b1',
                    type: 'ball',
                    color: '#AABBCC',
                    position: { x: 0, y: 0 },
                },
                catalog,
            ),
        ).toEqual({ color: '#AABBCC', shape: 'circle', isBall: true });
    });
});

describe('drawSandboxItem layer ordering', () => {
    it('draws fixture solid before definition-backed pickable regardless of array order', () => {
        const fixture: SandboxItemJson = {
            id: 'fx1',
            type: 'fixture',
            definition_kind: 'fixture',
            role: 'solid',
            definition_id: 'fx-def-1',
            position: { x: 0, y: 0 },
        };
        const pickable: SandboxItemJson = {
            id: 'p1',
            definition_kind: 'item',
            role: 'pickable',
            definition_id: 'item-def-1',
            color: '#FFFFFF',
            position: { x: 0, y: 0 },
        };

        const g = drawItemsInLayerOrder([pickable, fixture], {
            itemDefinitions: [{ id: 'item-def-1', shape: 'circle', default_color: '#FFFFFF' }],
        });

        expect(g.fillRect).toHaveBeenCalled();
        expect(g.fillCircle).toHaveBeenCalled();
        const rectOrder = g.fillRect.mock.invocationCallOrder.at(-1)!;
        const circleOrder = g.fillCircle.mock.invocationCallOrder[0]!;
        expect(circleOrder).toBeGreaterThan(rectOrder);
    });

    it('draws region under pickable regardless of array order', () => {
        const region: SandboxItemJson = {
            id: 'r1',
            type: 'region',
            position: { x: 0, y: 0 },
            color: '#3B82F6',
        };
        const pickable: SandboxItemJson = {
            id: 'p1',
            definition_kind: 'item',
            role: 'pickable',
            definition_id: 'item-def-1',
            color: '#FFFFFF',
            position: { x: 0, y: 0 },
        };

        const g = drawItemsInLayerOrder([pickable, region], {
            itemDefinitions: [{ id: 'item-def-1', shape: 'circle', default_color: '#FFFFFF' }],
        });

        const regionRectOrder = g.fillRect.mock.invocationCallOrder[0]!;
        const circleOrder = g.fillCircle.mock.invocationCallOrder[0]!;
        expect(circleOrder).toBeGreaterThan(regionRectOrder);
    });

    it('draws square definition pickables with fillRect', () => {
        const pickable: SandboxItemJson = {
            id: 'p1',
            definition_kind: 'item',
            role: 'pickable',
            definition_id: 'item-def-square',
            color: '#111111',
            position: { x: 1, y: 1 },
        };
        const g = mockGraphics();
        drawSandboxItem(g, pickable, 8, 8, {
            itemDefinitions: [{ id: 'item-def-square', shape: 'square', default_color: '#111111' }],
        });

        expect(g.fillRect).toHaveBeenCalled();
        expect(g.fillCircle).not.toHaveBeenCalled();
    });
});
