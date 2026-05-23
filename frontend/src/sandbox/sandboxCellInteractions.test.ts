import { describe, expect, it } from 'vitest';

import {
    placeBallInteraction,
    placeCreatureInteraction,
    placeFoodInteraction,
    placeRegionInteraction,
    removeItemAtCellInteraction,
    removeRegionAtCellInteraction,
} from './sandboxCellInteractions';

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

    it('builds remove_region payload', () => {
        expect(removeRegionAtCellInteraction({ x: 0, y: 1 })).toEqual({
            type: 'remove_region',
            cell: { x: 0, y: 1 },
        });
    });
});
