/** Aligned with ``DecisionAction`` / ``DECISION_ACTION_STRINGS`` on the backend. */
export const SANDBOX_DECISION_ACTIONS = ['move_to', 'wander', 'eat_nearby', 'sleep', 'idle'] as const;

export type SandboxDecisionAction = (typeof SANDBOX_DECISION_ACTIONS)[number];

export const DEFAULT_SANDBOX_DECISION_ACTION: SandboxDecisionAction = 'wander';

export function isSandboxDecisionAction(s: string): s is SandboxDecisionAction {
    return (SANDBOX_DECISION_ACTIONS as readonly string[]).includes(s);
}
