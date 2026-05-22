import { describe, expect, it } from 'vitest';

import { normalizeHexColor } from './sandboxColorUtils';

describe('sandboxColorUtils', () => {
    it('normalizes 6-digit hex', () => {
        expect(normalizeHexColor('#3b82f6')).toBe('#3B82F6');
    });

    it('expands 3-digit hex', () => {
        expect(normalizeHexColor('#f00')).toBe('#FF0000');
    });

    it('returns null for invalid values', () => {
        expect(normalizeHexColor('red')).toBeNull();
        expect(normalizeHexColor('#gggggg')).toBeNull();
    });
});
