/** Keys historically stored at the top level of Simple LLM `details` (now also in `resolved_inputs`). */
const LLM_INPUT_DETAIL_KEYS = ['system_prompt', 'user_prompt', 'additional_context'] as const;

/**
 * Merged object for Last Run / Run logs **Inputs**: executor `details.resolved_inputs` plus
 * legacy top-level LLM prompt fields when present.
 */
export function lastRunInputsPayload(
    details: Record<string, unknown> | undefined | null,
): Record<string, unknown> | null {
    if (!details || typeof details !== 'object') return null;
    const merged: Record<string, unknown> = {};
    const ri = details.resolved_inputs;
    if (ri && typeof ri === 'object' && !Array.isArray(ri)) {
        Object.assign(merged, ri as Record<string, unknown>);
    }
    for (const k of LLM_INPUT_DETAIL_KEYS) {
        if (k in details && details[k] !== undefined && !(k in merged)) {
            merged[k] = details[k];
        }
    }
    if (Object.keys(merged).length === 0) return null;
    return merged;
}
