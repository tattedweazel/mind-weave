import { describe, expect, it } from 'vitest';

import { DEFAULT_SANDBOX_DECISION_ACTION, isSandboxDecisionAction, SANDBOX_DECISION_ACTIONS } from './decisionActions';

describe('decisionActions', () => {
    it('lists four navigation actions', () => {
        expect(SANDBOX_DECISION_ACTIONS).toEqual(['move_forward', 'turn_left', 'turn_right', 'idle']);
    });

    it('validates known actions only', () => {
        expect(isSandboxDecisionAction('move_forward')).toBe(true);
        expect(isSandboxDecisionAction('wander')).toBe(false);
    });

    it('default is idle', () => {
        expect(DEFAULT_SANDBOX_DECISION_ACTION).toBe('idle');
    });
});
