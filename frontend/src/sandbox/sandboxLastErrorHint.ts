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

export function shouldShowSandboxRegionLabelNullHint(lastError: string | null | undefined): boolean {
    if (!lastError) return false;
    const s = lastError.toLowerCase();
    return (
        s.includes('dictionary value by key') &&
        s.includes('region_label') &&
        (s.includes('is null') || s.includes('not present'))
    );
}

export const SANDBOX_DECISION_ERROR_HINT =
    'Sandbox expects Stop to receive a dictionary-shaped DecisionIntent. Add a dictionary slot `sandbox_tick` on Start and wire sandbox utilities into Stop, or pick a compatible workflow. If the run stops after only one or two steps, check saved Execution limits on the workflow (max node executions). See docs/SANDBOX.md.';

export const SANDBOX_REGION_LABEL_NULL_HINT =
    'Nearby cells always include a region_label key; when no region is on that cell the value is null. Set a fallback (e.g. empty string) on Dictionary value by key before Is?, or compare only when a region exists. See docs/SANDBOX.md (Schema 2.4.0).';

/** Return contextual hint text for a sandbox last_error message, or null when none applies. */
export function sandboxErrorHintForMessage(message: string | null | undefined): string | null {
    if (!message) return null;
    if (shouldShowSandboxRegionLabelNullHint(message)) {
        return SANDBOX_REGION_LABEL_NULL_HINT;
    }
    if (shouldShowSandboxDecisionHint(message)) {
        return SANDBOX_DECISION_ERROR_HINT;
    }
    return null;
}
