import { describe, expect, it } from 'vitest';
import {
    extractBalancedJsonSlice,
    normalizeText,
    normalizeTextAsDictionary,
    normalizeTextAsList,
    normalizationTimingForKind,
    stripCommonJsonWrappers,
} from './normalizeText';

describe('normalizationTimingForKind', () => {
    it('returns explicit for list and dictionary', () => {
        expect(normalizationTimingForKind('list')).toBe('explicit');
        expect(normalizationTimingForKind('dictionary')).toBe('explicit');
    });
});

describe('stripCommonJsonWrappers', () => {
    it('trims and strips BOM', () => {
        expect(stripCommonJsonWrappers('\uFEFF  [1]  ')).toBe('[1]');
    });

    it('removes markdown fences', () => {
        const s = '```json\n[1,2]\n```';
        expect(stripCommonJsonWrappers(s)).toBe('[1,2]');
    });

    it('removes standalone --- lines', () => {
        expect(stripCommonJsonWrappers('---\n[1]\n---')).toBe('[1]');
    });
});

describe('extractBalancedJsonSlice', () => {
    it('extracts array from surrounding text', () => {
        expect(extractBalancedJsonSlice('prefix [1, [2]] tail', '[')).toBe('[1, [2]]');
    });

    it('extracts object respecting strings with brackets', () => {
        const s = 'x {"a": "[not]"} y';
        expect(extractBalancedJsonSlice(s, '{')).toBe('{"a": "[not]"}');
    });

    it('returns null when no opener', () => {
        expect(extractBalancedJsonSlice('no array', '[')).toBeNull();
    });
});

describe('normalizeTextAsList', () => {
    it('accepts plain JSON array', () => {
        const r = normalizeTextAsList('[1,2]');
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.value).toEqual([1, 2]);
    });

    it('accepts fenced and dashed noise', () => {
        const r = normalizeTextAsList('---\n```json\n[]\n```\n');
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.value).toEqual([]);
    });

    it('extracts array from prose', () => {
        const r = normalizeTextAsList('here: [true] end');
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.value).toEqual([true]);
    });

    it('fails when top-level is object', () => {
        const r = normalizeTextAsList('{"a":1}');
        expect(r.ok).toBe(false);
    });

    it('fails on invalid JSON', () => {
        const r = normalizeTextAsList('[');
        expect(r.ok).toBe(false);
    });
});

describe('normalizeTextAsDictionary', () => {
    it('accepts plain object', () => {
        const r = normalizeTextAsDictionary('{"x":1}');
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.value).toEqual({ x: 1 });
    });

    it('extracts object from prose', () => {
        const r = normalizeTextAsDictionary('output: {"k":"v"}');
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.value).toEqual({ k: 'v' });
    });

    it('fails when top-level is array', () => {
        const r = normalizeTextAsDictionary('[1]');
        expect(r.ok).toBe(false);
    });
});

describe('normalizeText facade', () => {
    it('dispatches by kind', () => {
        expect(normalizeText('[1]', 'list').ok).toBe(true);
        expect(normalizeText('{}', 'dictionary').ok).toBe(true);
    });
});
