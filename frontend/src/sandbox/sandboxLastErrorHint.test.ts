import { describe, expect, it } from 'vitest';

import { SANDBOX_DECISION_ERROR_HINT, shouldShowSandboxDecisionHint } from './sandboxLastErrorHint';

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

describe('SANDBOX_DECISION_ERROR_HINT', () => {
    it('is non-empty guidance text', () => {
        expect(SANDBOX_DECISION_ERROR_HINT.length).toBeGreaterThan(20);
        expect(SANDBOX_DECISION_ERROR_HINT).toContain('SANDBOX.md');
    });
});
