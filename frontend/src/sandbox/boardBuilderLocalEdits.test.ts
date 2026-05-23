import { describe, expect, it } from 'vitest';

import {
    applyBoardBuilderInteraction,
    createEmptyBoardDefinition,
    updateBoardItemMetadata,
} from './boardBuilderLocalEdits';
import { placeBallInteraction, placeFoodInteraction, placeRegionInteraction } from './sandboxCellInteractions';
import { SANDBOX_DEFAULT_FOOD_ENERGY } from './sandboxItemInspectorFields';

describe('boardBuilderLocalEdits', () => {
    it('seeds food with default energy aligned to backend', () => {
        const def = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeFoodInteraction({ x: 1, y: 1 }));
        expect(def.items[0]?.energy).toBe(SANDBOX_DEFAULT_FOOD_ENERGY);
    });

    it('places ball with color', () => {
        const def = applyBoardBuilderInteraction(
            createEmptyBoardDefinition(4, 4),
            placeBallInteraction({ x: 1, y: 1 }, '#AABBCC'),
        );
        expect(def.items[0]).toMatchObject({ type: 'ball', color: '#AABBCC', position: { x: 1, y: 1 } });
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

    it('coexists region with food and remove_item keeps region', () => {
        let def = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeRegionInteraction({ x: 1, y: 1 }, '#FF0000'));
        def = applyBoardBuilderInteraction(def, placeFoodInteraction({ x: 1, y: 1 }));
        expect(def.items.filter(it => it.position.x === 1 && it.position.y === 1).map(it => it.type).sort()).toEqual([
            'food',
            'region',
        ]);
        def = applyBoardBuilderInteraction(def, { type: 'remove_item', cell: { x: 1, y: 1 } });
        expect(def.items).toHaveLength(1);
        expect(def.items[0]?.type).toBe('region');
    });

    it('updates region color metadata', () => {
        const placed = applyBoardBuilderInteraction(
            createEmptyBoardDefinition(4, 4),
            placeRegionInteraction({ x: 0, y: 0 }, '#111111'),
        );
        const itemId = placed.items[0]?.id;
        const updated = updateBoardItemMetadata(placed, itemId!, { color: '#222222' });
        expect(updated.items[0]?.color).toBe('#222222');
    });

    it('remove_region leaves food intact', () => {
        let def = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeRegionInteraction({ x: 0, y: 0 }, '#111111'));
        def = applyBoardBuilderInteraction(def, placeFoodInteraction({ x: 0, y: 0 }));
        def = applyBoardBuilderInteraction(def, { type: 'remove_region', cell: { x: 0, y: 0 } });
        expect(def.items).toHaveLength(1);
        expect(def.items[0]?.type).toBe('food');
    });

    it('place_creature keeps region at cell', () => {
        let def = applyBoardBuilderInteraction(createEmptyBoardDefinition(4, 4), placeRegionInteraction({ x: 1, y: 1 }, '#111111'));
        def = applyBoardBuilderInteraction(def, {
            type: 'place_creature',
            cell: { x: 1, y: 1 },
            workflow_id: 'wf-1',
            color: '#3B82F6',
        });
        expect(def.items.some(it => it.type === 'region')).toBe(true);
        expect(def.creatures).toHaveLength(1);
        expect(def.creatures[0]?.color).toBe('#3B82F6');
    });
});
