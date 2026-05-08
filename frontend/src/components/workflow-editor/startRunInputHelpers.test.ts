import { describe, expect, it } from 'vitest';
import type { RequiredInput } from '../../api/types';
import {
    defaultDraftValueForRunWizard,
    draftValueToOverride,
    initialWizardDraftForStep,
    isStartInputMissingForRun,
    isValidRunWizardDraft,
    missingStartInputsForRun,
    normalizeStartInputsForRun,
    parseRunWizardAnyJson,
    parseRunWizardListOrDictJson,
} from './startRunInputHelpers';

describe('normalizeStartInputsForRun', () => {
    it('uses legacy user_input when required_inputs is undefined', () => {
        expect(normalizeStartInputsForRun(undefined, null)).toEqual([
            { key: 'user_input', type: 'string', value: null },
        ]);
        expect(normalizeStartInputsForRun(undefined, 'hi')).toEqual([
            { key: 'user_input', type: 'string', value: 'hi' },
        ]);
    });

    it('returns raw array when defined (including empty)', () => {
        const inputs: RequiredInput[] = [
            { key: 'target_list', type: 'list', value: null },
            { key: 'needle', type: 'string', value: null },
        ];
        expect(normalizeStartInputsForRun(inputs, 'ignored')).toEqual(inputs);
        expect(normalizeStartInputsForRun([], 'ignored')).toEqual([]);
    });
});

describe('isStartInputMissingForRun / missingStartInputsForRun', () => {
    it('treats string null and empty as missing', () => {
        expect(isStartInputMissingForRun({ key: 'a', type: 'string', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'a', type: 'string', value: '' })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'a', type: 'string', value: 'x' })).toBe(false);
    });

    it('treats datetime null and empty string as missing', () => {
        expect(isStartInputMissingForRun({ key: 't', type: 'datetime', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 't', type: 'datetime', value: '' })).toBe(true);
        expect(isStartInputMissingForRun({ key: 't', type: 'datetime', value: '2026-01-01T00:00:00Z' })).toBe(false);
    });

    it('treats non-string missing only when value is null', () => {
        expect(isStartInputMissingForRun({ key: 'b', type: 'boolean', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'b', type: 'boolean', value: false })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'b', type: 'boolean', value: true })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'n', type: 'int', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'n', type: 'int', value: 0 })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'l', type: 'list', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'l', type: 'list', value: [] })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'd', type: 'dictionary', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'd', type: 'dictionary', value: {} })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'x', type: 'any', value: null })).toBe(true);
        expect(isStartInputMissingForRun({ key: 'x', type: 'any', value: false })).toBe(false);
        expect(isStartInputMissingForRun({ key: 'x', type: 'any', value: 0 })).toBe(false);
    });

    it('preserves order of missing inputs', () => {
        const inputs: RequiredInput[] = [
            { key: 'target_list', type: 'string', value: null },
            { key: 'needle', type: 'string', value: null },
        ];
        expect(missingStartInputsForRun(inputs).map(i => i.key)).toEqual(['target_list', 'needle']);
    });
});

describe('defaultDraftValueForRunWizard', () => {
    it('returns empty string for string and null for other types', () => {
        expect(defaultDraftValueForRunWizard('string')).toBe('');
        expect(defaultDraftValueForRunWizard('list')).toBeNull();
        expect(defaultDraftValueForRunWizard('dictionary')).toBeNull();
        expect(defaultDraftValueForRunWizard('int')).toBeNull();
        expect(defaultDraftValueForRunWizard('datetime')).toBeNull();
        expect(defaultDraftValueForRunWizard('boolean')).toBeNull();
        expect(defaultDraftValueForRunWizard('any')).toBeNull();
    });
});

describe('initialWizardDraftForStep', () => {
    it('prefers override when key exists', () => {
        const inp: RequiredInput = { key: 'needle', type: 'string', value: null };
        expect(initialWizardDraftForStep(inp, { needle: 'revisit' })).toBe('revisit');
    });

    it('falls back to default when key missing', () => {
        const inp: RequiredInput = { key: 'needle', type: 'string', value: null };
        expect(initialWizardDraftForStep(inp, {})).toBe('');
    });

    it('falls back to null for list when key missing', () => {
        const inp: RequiredInput = { key: 'items', type: 'list', value: null };
        expect(initialWizardDraftForStep(inp, {})).toBeNull();
    });
});

describe('draftValueToOverride', () => {
    it('maps types for API overrides', () => {
        expect(draftValueToOverride('string', 'x')).toBe('x');
        expect(draftValueToOverride('string', null)).toBe('');
        expect(draftValueToOverride('list', [1])).toEqual([1]);
        expect(draftValueToOverride('list', [])).toEqual([]);
        expect(draftValueToOverride('list', null)).toBeNull();
        expect(draftValueToOverride('dictionary', { a: 1 })).toEqual({ a: 1 });
        expect(draftValueToOverride('dictionary', {})).toEqual({});
        expect(draftValueToOverride('int', 42)).toBe(42);
        expect(draftValueToOverride('datetime', '2026-01-01T00:00:00Z')).toBe('2026-01-01T00:00:00Z');
        expect(draftValueToOverride('boolean', true)).toBe(true);
        expect(draftValueToOverride('boolean', false)).toBe(false);
        expect(draftValueToOverride('boolean', null)).toBe(false);
        expect(draftValueToOverride('any', null)).toBeNull();
        expect(draftValueToOverride('any', [1, 2])).toEqual([1, 2]);
    });
});

describe('parseRunWizardListOrDictJson', () => {
    it('returns null for empty or incomplete JSON', () => {
        expect(parseRunWizardListOrDictJson('list', '')).toBeNull();
        expect(parseRunWizardListOrDictJson('list', '   ')).toBeNull();
        expect(parseRunWizardListOrDictJson('list', '[')).toBeNull();
        expect(parseRunWizardListOrDictJson('list', '[1,')).toBeNull();
        expect(parseRunWizardListOrDictJson('dictionary', '{')).toBeNull();
    });

    it('parses valid list and dictionary', () => {
        expect(parseRunWizardListOrDictJson('list', '[1,2]')).toEqual([1, 2]);
        expect(parseRunWizardListOrDictJson('list', '[]')).toEqual([]);
        expect(parseRunWizardListOrDictJson('dictionary', '{}')).toEqual({});
        expect(parseRunWizardListOrDictJson('dictionary', '{"a":1}')).toEqual({ a: 1 });
    });

    it('rejects wrong JSON shape for type', () => {
        expect(parseRunWizardListOrDictJson('list', '{}')).toBeNull();
        expect(parseRunWizardListOrDictJson('dictionary', '[]')).toBeNull();
        expect(parseRunWizardListOrDictJson('list', '"hi"')).toBeNull();
    });
});

describe('parseRunWizardAnyJson', () => {
    it('returns undefined for empty or invalid', () => {
        expect(parseRunWizardAnyJson('')).toBeUndefined();
        expect(parseRunWizardAnyJson('[')).toBeUndefined();
    });

    it('parses any valid JSON including null', () => {
        expect(parseRunWizardAnyJson('null')).toBeNull();
        expect(parseRunWizardAnyJson('42')).toBe(42);
        expect(parseRunWizardAnyJson('"hi"')).toBe('hi');
        expect(parseRunWizardAnyJson('true')).toBe(true);
        expect(parseRunWizardAnyJson('[1]')).toEqual([1]);
    });
});

describe('isValidRunWizardDraft', () => {
    it('requires non-empty string', () => {
        expect(isValidRunWizardDraft('string', '')).toBe(false);
        expect(isValidRunWizardDraft('string', '  ')).toBe(false);
        expect(isValidRunWizardDraft('string', 'ok')).toBe(true);
    });

    it('requires finite int', () => {
        expect(isValidRunWizardDraft('int', null)).toBe(false);
        expect(isValidRunWizardDraft('int', NaN)).toBe(false);
        expect(isValidRunWizardDraft('int', 0)).toBe(true);
    });

    it('allows boolean true, false, or unset (implicit false on submit)', () => {
        expect(isValidRunWizardDraft('boolean', true)).toBe(true);
        expect(isValidRunWizardDraft('boolean', false)).toBe(true);
        expect(isValidRunWizardDraft('boolean', null)).toBe(true);
    });

    it('requires array or object shapes', () => {
        expect(isValidRunWizardDraft('list', [])).toBe(true);
        expect(isValidRunWizardDraft('list', {})).toBe(false);
        expect(isValidRunWizardDraft('list', null)).toBe(false);
        expect(isValidRunWizardDraft('dictionary', {})).toBe(true);
        expect(isValidRunWizardDraft('dictionary', [])).toBe(false);
        expect(isValidRunWizardDraft('dictionary', null)).toBe(false);
    });

    it('accepts any parsed JSON value for any', () => {
        expect(isValidRunWizardDraft('any', undefined)).toBe(false);
        expect(isValidRunWizardDraft('any', null)).toBe(true);
        expect(isValidRunWizardDraft('any', 0)).toBe(true);
        expect(isValidRunWizardDraft('any', false)).toBe(true);
    });

    it('requires parseable RFC3339 for datetime', () => {
        expect(isValidRunWizardDraft('datetime', '')).toBe(false);
        expect(isValidRunWizardDraft('datetime', 'not-a-date')).toBe(false);
        expect(isValidRunWizardDraft('datetime', '2026-03-01T15:00:00Z')).toBe(true);
    });
});
