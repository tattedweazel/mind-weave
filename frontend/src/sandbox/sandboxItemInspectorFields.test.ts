import { describe, expect, it } from 'vitest';

import type { SandboxItemJson } from '../domain/sandbox/types';
import {
    getEditableItemFields,
    getItemFieldValue,
    SANDBOX_DEFAULT_FOOD_ENERGY,
    validateItemFieldValue,
} from './sandboxItemInspectorFields';

const foodItem: SandboxItemJson = {
    id: 'f1',
    type: 'food',
    position: { x: 1, y: 2 },
    energy: 30,
};

describe('sandboxItemInspectorFields', () => {
    it('returns energy field for food', () => {
        expect(getEditableItemFields('food').map(f => f.key)).toEqual(['energy']);
    });

    it('returns no fields for wall', () => {
        expect(getEditableItemFields('wall')).toEqual([]);
    });

    it('returns no fields for unknown types', () => {
        expect(getEditableItemFields('unknown')).toEqual([]);
    });

    it('reads energy from item', () => {
        expect(getItemFieldValue(foodItem, 'energy')).toBe(30);
        expect(getItemFieldValue({ ...foodItem, energy: undefined }, 'energy')).toBeUndefined();
    });

    it('validates integer energy values and clamps to min', () => {
        const field = getEditableItemFields('food')[0];
        expect(validateItemFieldValue(field, '12')).toBe(12);
        expect(validateItemFieldValue(field, '-5')).toBe(0);
        expect(validateItemFieldValue(field, '')).toBeNull();
        expect(validateItemFieldValue(field, 'abc')).toBeNull();
        expect(validateItemFieldValue(field, '1.5')).toBeNull();
    });

    it('exports default food energy aligned with backend', () => {
        expect(SANDBOX_DEFAULT_FOOD_ENERGY).toBe(48);
    });
});
