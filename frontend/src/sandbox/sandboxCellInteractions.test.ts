import { describe, expect, it } from 'vitest';

import {
    materializeItemDefinitionPlacementOptions,
    placeBallInteraction,
    placeCreatureInteraction,
    placeFoodInteraction,
    placeItemDefinitionInteraction,
    placeRegionInteraction,
    removeItemAtCellInteraction,
    removeRegionAtCellInteraction,
} from './sandboxCellInteractions';
import { SANDBOX_DEFAULT_FOOD_ENERGY } from './sandboxItemInspectorFields';

describe('sandboxCellInteractions', () => {
    it('builds place_item payload', () => {
        expect(placeFoodInteraction({ x: 2, y: 3 })).toEqual({
            type: 'place_item',
            cell: { x: 2, y: 3 },
            item_type: 'food',
        });
    });

    it('builds place_ball payload', () => {
        expect(placeBallInteraction({ x: 2, y: 3 }, '#AABBCC')).toEqual({
            type: 'place_item',
            cell: { x: 2, y: 3 },
            item_type: 'ball',
            color: '#AABBCC',
        });
    });

    it('builds place_region payload', () => {
        expect(placeRegionInteraction({ x: 1, y: 2 }, '#3B82F6')).toEqual({
            type: 'place_region',
            cell: { x: 1, y: 2 },
            color: '#3B82F6',
            label: '',
        });
        expect(placeRegionInteraction({ x: 1, y: 2 }, '#3B82F6', 'target')).toEqual({
            type: 'place_region',
            cell: { x: 1, y: 2 },
            color: '#3B82F6',
            label: 'target',
        });
    });

    it('builds remove_item payload', () => {
        expect(removeItemAtCellInteraction({ x: 0, y: 1 })).toEqual({
            type: 'remove_item',
            cell: { x: 0, y: 1 },
        });
    });

    it('builds place_creature payload', () => {
        expect(
            placeCreatureInteraction({ x: 2, y: 3 }, 'wf-1', { facing: 'E', color: '#3B82F6' }),
        ).toEqual({
            type: 'place_creature',
            cell: { x: 2, y: 3 },
            workflow_id: 'wf-1',
            facing: 'E',
            color: '#3B82F6',
        });
    });

    it('materializes energy-only placement when definition has both defaults', () => {
        expect(
            materializeItemDefinitionPlacementOptions({
                default_energy: 25,
                default_color: '#FFFFFF',
            }),
        ).toEqual({ energy: 25 });
        expect(
            placeItemDefinitionInteraction(
                { x: 1, y: 1 },
                'item-def-milk',
                materializeItemDefinitionPlacementOptions({
                    default_energy: 25,
                    default_color: '#FFFFFF',
                }),
            ),
        ).toEqual({
            type: 'place_item',
            cell: { x: 1, y: 1 },
            definition_id: 'item-def-milk',
            energy: 25,
        });
    });

    it('materializes color-only placement for ball-like definitions', () => {
        expect(
            materializeItemDefinitionPlacementOptions({
                default_color: '#AABBCC',
            }),
        ).toEqual({ color: '#AABBCC' });
    });

    it('falls back to default food energy when definition has no defaults', () => {
        expect(materializeItemDefinitionPlacementOptions({})).toEqual({
            energy: SANDBOX_DEFAULT_FOOD_ENERGY,
        });
    });

    it('builds remove_region payload', () => {
        expect(removeRegionAtCellInteraction({ x: 0, y: 1 })).toEqual({
            type: 'remove_region',
            cell: { x: 0, y: 1 },
        });
    });
});
