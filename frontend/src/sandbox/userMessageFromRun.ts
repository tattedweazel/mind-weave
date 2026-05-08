import type { NodeRunResult } from '../api/types';

/** UI cap for toast text (server caps at 2048 per node). */
export const SANDBOX_USER_MESSAGE_UI_MAX_LEN = 4000;

/**
 * Collect `details.user_message` strings from a workflow run, ordered by `step_number`
 * (then stable order), joined for a single toast body.
 */
export function collectUserMessagesFromNodeResults(nodeResults: NodeRunResult[] | undefined): string {
    if (!nodeResults?.length) return '';
    const sorted = [...nodeResults].sort((a, b) => {
        const sa = a.step_number ?? 0;
        const sb = b.step_number ?? 0;
        return sa - sb;
    });
    const parts: string[] = [];
    for (const nr of sorted) {
        if (nr.status !== 'ok' || !nr.details) continue;
        const um = (nr.details as Record<string, unknown>).user_message;
        if (typeof um === 'string' && um.length > 0) {
            parts.push(um);
        }
    }
    const joined = parts.join('\n\n');
    if (joined.length <= SANDBOX_USER_MESSAGE_UI_MAX_LEN) return joined;
    return `${joined.slice(0, SANDBOX_USER_MESSAGE_UI_MAX_LEN)}…`;
}
