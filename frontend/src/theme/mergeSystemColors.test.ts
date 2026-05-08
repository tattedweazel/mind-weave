import { describe, it, expect } from 'vitest';
import { DEFAULT_SYSTEM_COLORS_LIGHT } from './defaults';
import { mergeResolvedSystemColors } from './mergeSystemColors';

describe('mergeResolvedSystemColors', () => {
    it('applies preset then user partial on top of defaults', () => {
        const out = mergeResolvedSystemColors(
            DEFAULT_SYSTEM_COLORS_LIGHT,
            { primary: '#aaaaaa' },
            { page_bg: '#eeeeee' },
        );
        expect(out.primary).toBe('#aaaaaa');
        expect(out.page_bg).toBe('#eeeeee');
        expect(out.sidebar_bg).toBe(DEFAULT_SYSTEM_COLORS_LIGHT.sidebar_bg);
    });

    it('tolerates undefined partials', () => {
        const out = mergeResolvedSystemColors(DEFAULT_SYSTEM_COLORS_LIGHT, undefined, undefined);
        expect(out).toEqual(DEFAULT_SYSTEM_COLORS_LIGHT);
    });
});
