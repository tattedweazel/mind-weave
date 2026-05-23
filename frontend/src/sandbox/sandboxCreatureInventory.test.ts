import { describe, expect, it } from 'vitest';

import {
    addBoardCreatureInventoryEntry,
    formatInventoryEntryLabel,
    removeBoardCreatureInventoryEntry,
} from './sandboxCreatureInventory';

describe('sandboxCreatureInventory', () => {
    const baseDef = {
        grid: { width: 4, height: 4 },
        items: [],
        creatures: [
            {
                id: 'c1',
                workflow_id: 'wf',
                position: { x: 0, y: 0 },
                inventory: [],
            },
        ],
    };

    it('adds and removes inventory entries', () => {
        let def = addBoardCreatureInventoryEntry(baseDef, 'c1', 'ball');
        expect(def.creatures[0].inventory).toHaveLength(1);
        def = addBoardCreatureInventoryEntry(def, 'c1', 'food');
        expect(def.creatures[0].inventory).toHaveLength(2);
        def = removeBoardCreatureInventoryEntry(def, 'c1', 0);
        expect(def.creatures[0].inventory).toHaveLength(1);
        expect(def.creatures[0].inventory?.[0].type).toBe('food');
    });

    it('formats labels', () => {
        expect(formatInventoryEntryLabel({ type: 'ball', color: '#FF0000' })).toContain('Ball');
        expect(formatInventoryEntryLabel({ type: 'food', energy: 48 })).toContain('48');
    });
});
