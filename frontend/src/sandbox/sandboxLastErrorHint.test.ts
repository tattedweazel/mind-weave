import { describe, expect, it } from 'vitest';

import {
    SANDBOX_DECISION_ERROR_HINT,
    SANDBOX_REGION_LABEL_NULL_HINT,
    sandboxErrorHintForMessage,
    shouldShowSandboxDecisionHint,
    shouldShowSandboxRegionLabelNullHint,
} from './sandboxLastErrorHint';

describe('shouldShowSandboxDecisionHint', () => {
    it('returns false for null, undefined, and empty', () => {
        expect(shouldShowSandboxDecisionHint(null)).toBe(false);
        expect(shouldShowSandboxDecisionHint(undefined)).toBe(false);
        expect(shouldShowSandboxDecisionHint('')).toBe(false);
    });

    it('returns true for Stop / DecisionIntent parse errors from the backend', () => {
        expect(shouldShowSandboxDecisionHint('unexpected Stop output type: StringNodeOutput')).toBe(true);
        expect(shouldShowSandboxDecisionHint('Stop output empty')).toBe(true);
        expect(shouldShowSandboxDecisionHint('Stop node did not produce output')).toBe(true);
        expect(shouldShowSandboxDecisionHint('invalid DecisionIntent: ...')).toBe(true);
        expect(shouldShowSandboxDecisionHint('workflow has no Stop node')).toBe(true);
    });

    it('returns false for unrelated strings', () => {
        expect(shouldShowSandboxDecisionHint('Network error')).toBe(false);
        expect(shouldShowSandboxDecisionHint('409 conflict')).toBe(false);
    });
});

describe('shouldShowSandboxRegionLabelNullHint', () => {
    it('returns true for dictionary value by key region_label null errors', () => {
        expect(
            shouldShowSandboxRegionLabelNullHint(
                "Dictionary value by key: value for key 'region_label' is null",
            ),
        ).toBe(true);
    });

    it('returns false for unrelated strings', () => {
        expect(shouldShowSandboxRegionLabelNullHint('Stop node did not produce output')).toBe(false);
    });
});

describe('sandboxErrorHintForMessage', () => {
    it('prefers region_label hint over generic decision hint', () => {
        expect(
            sandboxErrorHintForMessage("Dictionary value by key: value for key 'region_label' is null"),
        ).toBe(SANDBOX_REGION_LABEL_NULL_HINT);
    });

    it('returns decision hint for Stop errors', () => {
        expect(sandboxErrorHintForMessage('Stop node did not produce output')).toBe(SANDBOX_DECISION_ERROR_HINT);
    });

    it('returns null for unrelated errors', () => {
        expect(sandboxErrorHintForMessage('Network error')).toBeNull();
    });
});

describe('SANDBOX_DECISION_ERROR_HINT', () => {
    it('is non-empty guidance text', () => {
        expect(SANDBOX_DECISION_ERROR_HINT.length).toBeGreaterThan(20);
        expect(SANDBOX_DECISION_ERROR_HINT).toContain('SANDBOX.md');
        expect(SANDBOX_DECISION_ERROR_HINT).toContain('Execution limits');
    });
});

describe('SANDBOX_REGION_LABEL_NULL_HINT', () => {
    it('mentions fallback and SANDBOX.md', () => {
        expect(SANDBOX_REGION_LABEL_NULL_HINT).toContain('fallback');
        expect(SANDBOX_REGION_LABEL_NULL_HINT).toContain('SANDBOX.md');
    });
});
