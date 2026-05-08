import { describe, expect, it } from 'vitest';
import type { RequiredInput } from '../../api/types';
import { nextUniqueStartSlotKey, validateStartSlotKey } from './startSlotKeyHelpers';

describe('nextUniqueStartSlotKey', () => {
    it('returns user_input for the first slot', () => {
        expect(nextUniqueStartSlotKey([])).toBe('user_input');
    });

    it('returns input_2 when one slot exists', () => {
        const inputs: RequiredInput[] = [{ key: 'user_input', type: 'string', value: null }];
        expect(nextUniqueStartSlotKey(inputs)).toBe('input_2');
    });

    it('skips colliding input_N when a slot already uses that key', () => {
        const inputs: RequiredInput[] = [
            { key: 'user_input', type: 'string', value: null },
            { key: 'input_3', type: 'string', value: null },
        ];
        expect(nextUniqueStartSlotKey(inputs)).toBe('input_2');
    });
});

describe('validateStartSlotKey', () => {
    const base: RequiredInput[] = [
        { key: 'a', type: 'string', value: null },
        { key: 'b', type: 'string', value: null },
    ];

    it('rejects empty keys', () => {
        expect(validateStartSlotKey('', base, 0)).toBe('Key is required');
    });

    it('rejects duplicate keys', () => {
        expect(validateStartSlotKey('b', base, 0)).toBe('Key must be unique');
    });

    it('allows same key at the current index', () => {
        expect(validateStartSlotKey('a', base, 0)).toBeNull();
    });

    it('rejects reserved control-flow ids', () => {
        expect(validateStartSlotKey('signal_out', base, 0)).toBe('This key is reserved for control-flow handles');
        expect(validateStartSlotKey('trigger', base, 0)).toBe('This key is reserved for control-flow handles');
    });
});
