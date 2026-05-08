/**
 * Whether to show authoring guidance under Sandbox envelope `last_error`.
 * Matches messages from `workflow_bridge.decision_intent_from_workflow_result` and related paths.
 */
export function shouldShowSandboxDecisionHint(lastError: string | null | undefined): boolean {
    if (!lastError) return false;
    const s = lastError.toLowerCase();
    return (
        s.includes('decisionintent') ||
        s.includes('stop output') ||
        s.includes('stop node did not') ||
        s.includes('unexpected stop') ||
        s.includes('workflow has no stop')
    );
}

export const SANDBOX_DECISION_ERROR_HINT =
    'Sandbox expects Stop to receive a dictionary-shaped DecisionIntent. Add a dictionary slot `sandbox_tick` on Start and wire sandbox utilities into Stop, or pick a compatible workflow. See docs/SANDBOX.md.';
