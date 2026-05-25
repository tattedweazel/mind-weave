import { describe, expect, it } from 'vitest';

import {
    addBoardCreatureInventoryEntry,
    formatInventoryEntryLabel,
    inventoryEntryColor,
    inventoryEntryEnergy,
    inventoryEntryTitle,
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

    it('formats definition-backed inventory labels', () => {
        const ctx = {
            itemDefinitions: [
                {
                    id: 'item-def-golden-key',
                    name: 'golden_key',
                    label: 'Golden Key',
                    default_color: null,
                },
            ],
        };
        expect(
            inventoryEntryTitle(
                { type: 'food', energy: 10, definition_id: 'item-def-golden-key' },
                ctx,
            ),
        ).toBe('Item · Golden Key');
        expect(
            formatInventoryEntryLabel(
                { type: 'food', energy: 10, definition_id: 'item-def-golden-key' },
                ctx,
            ),
        ).toContain('Golden Key');
        expect(
            formatInventoryEntryLabel(
                { type: 'food', energy: 10, definition_id: 'item-def-golden-key' },
                ctx,
            ),
        ).not.toContain('Food');
        expect(inventoryEntryEnergy({ type: 'food', energy: 10 }, ctx)).toBe(10);
        expect(
            inventoryEntryColor(
                { type: 'ball', color: '#AABBCC', definition_id: 'missing' },
                ctx,
            ),
        ).toBe('#AABBCC');
    });
});
