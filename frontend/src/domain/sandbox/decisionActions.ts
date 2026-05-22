/** Aligned with ``DecisionAction`` on the backend sandbox schema. */
export const SANDBOX_DECISION_ACTIONS = ['move_forward', 'turn_left', 'turn_right', 'idle'] as const;

export type SandboxDecisionAction = (typeof SANDBOX_DECISION_ACTIONS)[number];

export const DEFAULT_SANDBOX_DECISION_ACTION: SandboxDecisionAction = 'idle';

export function isSandboxDecisionAction(s: string): s is SandboxDecisionAction {
    return (SANDBOX_DECISION_ACTIONS as readonly string[]).includes(s);
}
