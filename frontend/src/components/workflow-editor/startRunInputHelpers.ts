import type { RequiredInput } from '../../api/types';
import { parseRfc3339ToUtcMs } from '../../domain/gmailRfc3339Date';

/**
 * Resolves persisted Start `required_inputs` for run + modal logic.
 * `required_inputs === undefined` means legacy single `user_input` from `text`.
 */
export function normalizeStartInputsForRun(
    rawInputs: RequiredInput[] | undefined,
    legacyText: string | null | undefined,
): RequiredInput[] {
    if (rawInputs === undefined) {
        return [{ key: 'user_input', type: 'string', value: legacyText ?? null }];
    }
    return rawInputs;
}

/** Same rule as the pre-run prompt: strings also treat '' as missing. */
export function isStartInputMissingForRun(inp: RequiredInput): boolean {
    const v = inp.value;
    if (inp.type === 'string' || inp.type === 'datetime') return v == null || v === '';
    return v == null;
}

export function missingStartInputsForRun(inputs: RequiredInput[]): RequiredInput[] {
    return inputs.filter(isStartInputMissingForRun);
}

export function defaultDraftValueForRunWizard(type: RequiredInput['type']): unknown {
    if (type === 'string') return '';
    return null;
}

/**
 * Initial draft when entering a step: reuse a value from `overrides` when going **Back**, else default.
 */
export function initialWizardDraftForStep(
    inp: RequiredInput,
    overrides: Record<string, unknown>,
): unknown {
    if (Object.prototype.hasOwnProperty.call(overrides, inp.key)) {
        return overrides[inp.key];
    }
    return defaultDraftValueForRunWizard(inp.type);
}

export function draftValueToOverride(type: RequiredInput['type'], draft: unknown): unknown {
    if (type === 'string') return draft ?? '';
    if (type === 'datetime') return typeof draft === 'string' ? draft : '';
    if (type === 'list') return draft;
    if (type === 'dictionary') return draft;
    if (type === 'any' || type === 'document' || type === 'structure') return draft;
    if (type === 'int') return draft;
    if (type === 'boolean') return draft === null || draft === undefined ? false : draft;
    return draft;
}

/**
 * Parse list/dictionary JSON from the run wizard textarea (may be incomplete while typing).
 * Returns null for empty/invalid/incomplete JSON.
 */
export function parseRunWizardListOrDictJson(
    type: 'list' | 'dictionary',
    raw: string,
): unknown[] | Record<string, unknown> | null {
    const t = raw.trim();
    if (t === '') return null;
    try {
        const parsed: unknown = JSON.parse(t);
        if (type === 'list' && Array.isArray(parsed)) return parsed;
        if (
            type === 'dictionary' &&
            typeof parsed === 'object' &&
            parsed !== null &&
            !Array.isArray(parsed)
        ) {
            return parsed as Record<string, unknown>;
        }
    } catch {
        /* incomplete or invalid JSON */
    }
    return null;
}

/**
 * Parse any JSON value from the run wizard textarea (may be incomplete while typing).
 * Returns `undefined` for empty/invalid; `null` is a valid parsed value (JSON `null`).
 */
export function parseRunWizardAnyJson(raw: string): unknown | undefined {
    const t = raw.trim();
    if (t === '') return undefined;
    try {
        return JSON.parse(t);
    } catch {
        return undefined;
    }
}

/** Whether the user can leave this step via Continue / Run. */
export function isValidRunWizardDraft(type: RequiredInput['type'], draft: unknown): boolean {
    if (type === 'string') return typeof draft === 'string' && draft.trim() !== '';
    if (type === 'int') {
        return typeof draft === 'number' && !Number.isNaN(draft);
    }
    if (type === 'boolean') {
        return draft === true || draft === false || draft === null || draft === undefined;
    }
    if (type === 'list') return Array.isArray(draft);
    if (type === 'dictionary') {
        return typeof draft === 'object' && draft !== null && !Array.isArray(draft);
    }
    if (type === 'any' || type === 'document' || type === 'structure') return draft !== undefined;
    if (type === 'datetime') {
        if (typeof draft !== 'string' || !draft.trim()) return false;
        return parseRfc3339ToUtcMs(draft.trim()) != null;
    }
    return false;
}
