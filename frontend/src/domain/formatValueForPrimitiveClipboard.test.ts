import { describe, expect, it } from 'vitest';
import {
    formatListOrDictionaryForClipboard,
    formatValueForPrimitiveClipboard,
} from './formatValueForPrimitiveClipboard';

describe('formatListOrDictionaryForClipboard', () => {
    it('formats arrays and objects for paste', () => {
        expect(formatListOrDictionaryForClipboard([1, 'a'], 'list')).toBe(JSON.stringify([1, 'a'], null, 2));
        expect(formatListOrDictionaryForClipboard({ a: 1 }, 'dictionary')).toBe(JSON.stringify({ a: 1 }, null, 2));
    });

    it('handles empty and invalid containers', () => {
        expect(formatListOrDictionaryForClipboard([], 'list')).toBe('[]');
        expect(formatListOrDictionaryForClipboard({}, 'dictionary')).toBe('{}');
        expect(formatListOrDictionaryForClipboard(null, 'list')).toBe('[]');
        expect(formatListOrDictionaryForClipboard([], 'dictionary')).toBe('{}');
    });
});

describe('formatValueForPrimitiveClipboard', () => {
    it('formats string and scalars', () => {
        expect(formatValueForPrimitiveClipboard('hi', 'string')).toBe('hi');
        expect(formatValueForPrimitiveClipboard(42, 'int')).toBe('42');
        expect(formatValueForPrimitiveClipboard(true, 'boolean')).toBe('true');
    });

    it('JSON-stringifies structured values', () => {
        expect(formatValueForPrimitiveClipboard({ a: 1 }, 'dictionary')).toBe(JSON.stringify({ a: 1 }, null, 2));
        expect(formatValueForPrimitiveClipboard([1, 2], 'list')).toBe(JSON.stringify([1, 2], null, 2));
    });

    it('handles nullish', () => {
        expect(formatValueForPrimitiveClipboard(null, 'null')).toBe('');
        expect(formatValueForPrimitiveClipboard(undefined, undefined)).toBe('');
    });
});
