/**
 * IANA zone for Calendar output explorer; matches My Profile → Workflow time zone.
 */
import { resolveWorkflowTimeZone } from '../../domain/gmailRfc3339Date';

export function calendarDisplayTimeZoneForExplorer(
    explorer: { kind: string } | null,
    userSettings: Record<string, unknown> | undefined,
): string | undefined {
    if (!explorer || explorer.kind !== 'calendar_list_events') {
        return undefined;
    }
    return resolveWorkflowTimeZone(userSettings);
}
