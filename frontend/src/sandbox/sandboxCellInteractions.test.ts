import { describe, expect, it } from 'vitest';

import { placeFoodInteraction, removeItemAtCellInteraction } from './sandboxCellInteractions';

describe('sandboxCellInteractions', () => {
    it('builds place_item payload', () => {
        expect(placeFoodInteraction({ x: 2, y: 3 })).toEqual({
            type: 'place_item',
            cell: { x: 2, y: 3 },
            item_type: 'food',
        });
    });

    it('builds remove_item payload', () => {
        expect(removeItemAtCellInteraction({ x: 0, y: 1 })).toEqual({
            type: 'remove_item',
            cell: { x: 0, y: 1 },
        });
    });
});
