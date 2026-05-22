import { describe, expect, it } from 'vitest';

import { defaultRegionPlacementColor, parseSandboxFavoriteColors } from './sandboxFavoriteColors';

describe('sandboxFavoriteColors', () => {
    it('parses valid favorite colors', () => {
        expect(parseSandboxFavoriteColors({ sandbox_favorite_colors: ['#3b82f6', '#f00'] })).toEqual([
            '#3B82F6',
            '#FF0000',
        ]);
    });

    it('deduplicates favorites', () => {
        expect(parseSandboxFavoriteColors({ sandbox_favorite_colors: ['#3B82F6', '#3b82f6'] })).toEqual(['#3B82F6']);
    });

    it('defaults placement color from first favorite', () => {
        expect(defaultRegionPlacementColor(['#FF0000'])).toBe('#FF0000');
        expect(defaultRegionPlacementColor([])).toBe('#3B82F6');
    });
});
