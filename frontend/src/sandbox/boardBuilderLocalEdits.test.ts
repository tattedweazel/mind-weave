import { describe, expect, it } from 'vitest';

import {
    applyBoardBuilderInteraction,
    createEmptyBoardDefinition,
    updateBoardItemMetadata,
} from './boardBuilderLocalEdits';
import { placeFoodInteraction } from './sandboxCellInteractions';
import { SANDBOX_DEFAULT_FOOD_ENERGY } from './sandboxItemInspectorFields';

describe('boardBuilderLocalEdits', () => {
    it('seeds food with default energy aligned to backend', () => {
        const def = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeFoodInteraction({ x: 1, y: 1 }));
        expect(def.items[0]?.energy).toBe(SANDBOX_DEFAULT_FOOD_ENERGY);
    });

    it('updates editable metadata for food items', () => {
        const placed = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeFoodInteraction({ x: 0, y: 0 }));
        const itemId = placed.items[0]?.id;
        expect(itemId).toBeTruthy();

        const updated = updateBoardItemMetadata(placed, itemId!, { energy: 72 });
        expect(updated.items[0]?.energy).toBe(72);
    });

    it('no-ops when item id is missing', () => {
        const def = createEmptyBoardDefinition(4, 4);
        expect(updateBoardItemMetadata(def, 'missing', { energy: 10 })).toBe(def);
    });

    it('ignores disallowed metadata for wall items', () => {
        const def = {
            ...createEmptyBoardDefinition(4, 4),
            items: [{ id: 'w1', type: 'wall', position: { x: 0, y: 0 } }],
        };
        const updated = updateBoardItemMetadata(def, 'w1', { energy: 99 });
        expect(updated).toBe(def);
        expect(updated.items[0]?.energy).toBeUndefined();
    });
});
