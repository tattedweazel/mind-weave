import { parseRfc3339ToUtcMs } from '../../domain/gmailRfc3339Date';

export interface CalendarTimeWindowHelpContentProps {
    timeMinValue: string | null | undefined;
    timeMaxValue: string | null | undefined;
}

function formatStoredLine(raw: string | null | undefined): string {
    const s = raw?.trim();
    if (!s) {
        return '—';
    }
    const ms = parseRfc3339ToUtcMs(s);
    if (ms != null) {
        return new Date(ms).toISOString();
    }
    return s;
}

/**
 * Primer for Calendar List time window: timezone, RFC3339, and raw editor—shown in ContextHelpModal.
 */
export function CalendarTimeWindowHelpContent({ timeMinValue, timeMaxValue }: CalendarTimeWindowHelpContentProps) {
    const minLine = formatStoredLine(timeMinValue);
    const maxLine = formatStoredLine(timeMaxValue);

    return (
        <div className="space-y-3 text-mw-text-primary">
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                <strong className="text-mw-text-primary">Start</strong> and <strong className="text-mw-text-primary">End</strong> use the
                date and time you pick as wall-clock values in your <strong className="text-mw-text-primary">My Profile → Workflow time
                zone</strong>. The editor converts those to a single <strong className="text-mw-text-primary">UTC instant</strong> and stores{' '}
                <strong className="text-mw-text-primary">RFC3339</strong> strings for <code className="font-mono text-[10px]">time_min</code>{' '}
                and <code className="font-mono text-[10px]">time_max</code>, which the Calendar API expects for{' '}
                <code className="font-mono text-[10px]">events.list</code>.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                To use a different zone, change <strong className="text-mw-text-primary">My Profile → Workflow time zone</strong>. Existing
                stored instants are unchanged; adjust the pickers if you need new wall-clock values.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                Use <strong className="text-mw-text-primary">Edit raw RFC3339</strong> below when you need an explicit offset (
                <code className="font-mono text-[10px]">+05:30</code> etc.), to paste from run logs, or for edge cases.
            </p>
            <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary mb-1">
                    Current values (RFC3339)
                </div>
                <p className="text-[10px] text-mw-text-secondary mb-1">
                    <span className="font-medium text-mw-text-primary">time_min:</span>{' '}
                    <code className="font-mono text-[10px] text-mw-text-primary break-all">{minLine}</code>
                </p>
                <p className="text-[10px] text-mw-text-secondary">
                    <span className="font-medium text-mw-text-primary">time_max:</span>{' '}
                    <code className="font-mono text-[10px] text-mw-text-primary break-all">{maxLine}</code>
                </p>
            </div>
        </div>
    );
}
