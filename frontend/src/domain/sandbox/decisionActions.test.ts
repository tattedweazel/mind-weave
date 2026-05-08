import { describe, expect, it } from 'vitest';

import { DEFAULT_SANDBOX_DECISION_ACTION, isSandboxDecisionAction, SANDBOX_DECISION_ACTIONS } from './decisionActions';

describe('decisionActions', () => {
    it('lists five canonical actions', () => {
        expect(SANDBOX_DECISION_ACTIONS.length).toBe(5);
    });

    it('validates known actions only', () => {
        expect(isSandboxDecisionAction('wander')).toBe(true);
        expect(isSandboxDecisionAction('invalid')).toBe(false);
    });

    it('default is wander', () => {
        expect(DEFAULT_SANDBOX_DECISION_ACTION).toBe('wander');
    });
});
