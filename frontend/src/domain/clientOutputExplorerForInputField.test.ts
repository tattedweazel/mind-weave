import { describe, it, expect } from 'vitest';
import {
    buildClientExplorerForInputField,
    CLIENT_OUTPUT_EXPLORER_MAX_ITEMS,
    inferPrimitiveKindForExplorer,
} from './clientOutputExplorerForInputField';

describe('inferPrimitiveKindForExplorer', () => {
    it('classifies JSON-like values', () => {
        expect(inferPrimitiveKindForExplorer(null)).toBe('null');
        expect(inferPrimitiveKindForExplorer(undefined)).toBe('undefined');
        expect(inferPrimitiveKindForExplorer(true)).toBe('boolean');
        expect(inferPrimitiveKindForExplorer(3)).toBe('int');
        expect(inferPrimitiveKindForExplorer(3.5)).toBe('number');
        expect(inferPrimitiveKindForExplorer('x')).toBe('string');
        expect(inferPrimitiveKindForExplorer([])).toBe('list');
        expect(inferPrimitiveKindForExplorer({})).toBe('dictionary');
    });
});

describe('buildClientExplorerForInputField', () => {
    it('uses field key as summary line for a string', () => {
        const b = buildClientExplorerForInputField('user_prompt', 'hello');
        expect(b.explorer.kind).toBe('string_primitive');
        expect(b.explorer.summary.line).toBe('user_prompt');
        expect(b.headerClipboardText).toBe('hello');
    });

    it('preserves dictionary key order in items', () => {
        const data: Record<string, unknown> = {};
        data.z = 1;
        data.a = 2;
        const b = buildClientExplorerForInputField('ctx', data);
        expect(b.explorer.kind).toBe('dictionary_primitive');
        expect(b.explorer.items.map(i => i.primary_line)).toEqual(['z', 'a']);
    });

    it('caps list items and sets overflow_count', () => {
        const arr = Array.from({ length: CLIENT_OUTPUT_EXPLORER_MAX_ITEMS + 4 }, (_, i) => i);
        const b = buildClientExplorerForInputField('items', arr);
        expect(b.explorer.items.length).toBe(CLIENT_OUTPUT_EXPLORER_MAX_ITEMS);
        expect(b.explorer.overflow_count).toBe(4);
    });

    it('returns header copy for null', () => {
        const b = buildClientExplorerForInputField('x', null);
        expect(b.headerClipboardText).toBe('null');
    });

    it('includes expandNoRowsDetail for scalar fields so the explorer header can open the detail modal', () => {
        const b = buildClientExplorerForInputField('k', 'hello');
        expect(b.expandNoRowsDetail).toEqual({
            payload: 'hello',
            title: 'k',
            subtitle: 'string',
        });
        const dict = buildClientExplorerForInputField('d', { a: 1 });
        expect(dict.expandNoRowsDetail).toBeUndefined();
    });
});
