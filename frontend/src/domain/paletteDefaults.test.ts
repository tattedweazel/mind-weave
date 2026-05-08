import { describe, it, expect } from 'vitest';
import {
    DEFAULT_PALETTE_COLORS,
    DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME,
    DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG,
    expandWorkflowPaletteColorsForExport,
    normalizeWorkflowPaletteColors,
    resolveFallbackWorkflowPalette,
    resolveWorkflowPaletteColor,
    sortWorkflowPalettesForDisplay,
    WORKFLOW_PALETTE_COLORS,
} from './paletteDefaults';

describe('resolveFallbackWorkflowPalette', () => {
    it('returns null for empty list', () => {
        expect(resolveFallbackWorkflowPalette([])).toBeNull();
    });

    it('prefers system Default by name over other system presets', () => {
        const palettes = [
            { name: 'Arcade', user_id: null },
            { name: DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME, user_id: null },
            { name: 'Slate', user_id: null },
        ];
        expect(resolveFallbackWorkflowPalette(palettes)?.name).toBe(DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME);
    });

    it('prefers system Default by slug even if another system row has display name Default', () => {
        const palettes = [
            { name: 'Wrong', user_id: null, slug: DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG },
            { name: DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME, user_id: null, slug: null },
        ];
        expect(resolveFallbackWorkflowPalette(palettes)?.slug).toBe(DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG);
    });

    it('ignores user-owned palette named Default', () => {
        const palettes = [
            { name: DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME, user_id: 'user-1' },
            { name: 'Slate', user_id: null },
        ];
        expect(resolveFallbackWorkflowPalette(palettes)?.name).toBe('Slate');
    });

    it('uses first system palette by name when Default is absent', () => {
        const palettes = [
            { name: 'Meadow', user_id: null },
            { name: 'Arcade', user_id: null },
        ];
        expect(resolveFallbackWorkflowPalette(palettes)?.name).toBe('Arcade');
    });
});

describe('sortWorkflowPalettesForDisplay', () => {
    it('orders Default first, then other system A–Z, then user palettes A–Z', () => {
        const sorted = sortWorkflowPalettesForDisplay([
            { name: 'Zebra', user_id: 'u1' },
            { name: 'Arcade', user_id: null },
            { name: DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME, user_id: null },
            { name: 'Slate', user_id: null },
            { name: 'Apple', user_id: 'u1' },
        ]);
        expect(sorted.map(p => p.name)).toEqual([
            DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME,
            'Arcade',
            'Slate',
            'Apple',
            'Zebra',
        ]);
    });
});

describe('resolveWorkflowPaletteColor', () => {
    it('uses specific palette key over step family', () => {
        const c = resolveWorkflowPaletteColor(
            {
                control: '#0000ff',
                gt_control: '#ff0000',
            },
            'gt_control'
        );
        expect(c).toBe('#ff0000');
    });

    it('uses step family when specific key is unset', () => {
        const c = resolveWorkflowPaletteColor({ control: '#0000ff' }, 'gt_control');
        expect(c).toBe('#0000ff');
    });

    it('does not apply control family to primitives', () => {
        const c = resolveWorkflowPaletteColor({ control: '#0000ff' }, 'string');
        expect(c).toBe(DEFAULT_PALETTE_COLORS.string);
    });

    it('falls back to built-in default when palette is empty', () => {
        expect(resolveWorkflowPaletteColor({}, 'gt_control')).toBe(DEFAULT_PALETTE_COLORS.gt_control);
    });

    it('uses palette any after defaults for unknown handle keys', () => {
        const c = resolveWorkflowPaletteColor({ any: '#cccccc' }, 'totally_unknown_key');
        expect(c).toBe('#cccccc');
    });

    it('uses default any when nothing else applies', () => {
        const c = resolveWorkflowPaletteColor({}, 'totally_unknown_key');
        expect(c).toBe(DEFAULT_PALETTE_COLORS.any);
    });

    it('treats empty string on specific key as unset and uses family', () => {
        const c = resolveWorkflowPaletteColor(
            { gt_control: '', control: '#00ffff' },
            'gt_control'
        );
        expect(c).toBe('#00ffff');
    });
});

describe('normalizeWorkflowPaletteColors', () => {
    it('removes keys that match shipped defaults', () => {
        const n = normalizeWorkflowPaletteColors({
            string: WORKFLOW_PALETTE_COLORS.string,
            primitive: '#abcdef',
        });
        expect(n).toEqual({ primitive: '#abcdef' });
    });

    it('keeps customized per-step values', () => {
        const n = normalizeWorkflowPaletteColors({ string: '#111111' });
        expect(n).toEqual({ string: '#111111' });
    });

    it('drops empty strings', () => {
        const n = normalizeWorkflowPaletteColors({ string: '', primitive: '#222222' });
        expect(n).toEqual({ primitive: '#222222' });
    });

    it('allows family color after stripping default per-step keys', () => {
        const pal = normalizeWorkflowPaletteColors({
            ...WORKFLOW_PALETTE_COLORS,
            primitive: '#999999',
        });
        expect(resolveWorkflowPaletteColor(pal, 'string')).toBe('#999999');
    });
});

describe('expandWorkflowPaletteColorsForExport', () => {
    it('fills every WORKFLOW_PALETTE_COLORS key using defaults when omitted', () => {
        const full = expandWorkflowPaletteColorsForExport({ primitive: '#abcdef' });
        expect(full.string).toBe(WORKFLOW_PALETTE_COLORS.string);
        expect(full.primitive).toBe('#abcdef');
        expect(Object.keys(full)).toEqual(expect.arrayContaining(Object.keys(WORKFLOW_PALETTE_COLORS)));
    });

    it('preserves overrides and re-normalizes to same sparse shape', () => {
        const sparse = { string: '#111111', primitive: '#222222' };
        const full = expandWorkflowPaletteColorsForExport(sparse);
        expect(normalizeWorkflowPaletteColors(full)).toEqual(normalizeWorkflowPaletteColors(sparse));
    });
});
