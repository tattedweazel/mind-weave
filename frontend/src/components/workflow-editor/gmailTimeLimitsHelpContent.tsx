import { parseRfc3339ToUtcMs } from '../../domain/gmailRfc3339Date';

export interface GmailTimeLimitsHelpContentProps {
    afterValue: string | null | undefined;
    beforeValue: string | null | undefined;
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
 * Primer for Gmail List **After** / **Before**: timezone, RFC3339, `q` date mapping—ContextHelpModal.
 */
export function GmailTimeLimitsHelpContent({ afterValue, beforeValue }: GmailTimeLimitsHelpContentProps) {
    const afterLine = formatStoredLine(afterValue);
    const beforeLine = formatStoredLine(beforeValue);

    return (
        <div className="space-y-3 text-mw-text-primary">
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                <strong className="text-mw-text-primary">After</strong> and <strong className="text-mw-text-primary">Before</strong> use the
                date and time you pick as wall-clock values in your <strong className="text-mw-text-primary">My Profile → Workflow time
                zone</strong> (same zone as Calendar List pickers). The editor stores <strong className="text-mw-text-primary">RFC3339</strong>{' '}
                instants on the node.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                Gmail search only supports <strong className="text-mw-text-primary">date</strong> in{' '}
                <code className="font-mono text-[10px]">after:</code> / <code className="font-mono text-[10px]">before:</code> (not a time
                of day). When this workflow runs, those operators use the <strong className="text-mw-text-primary">calendar day</strong> in
                that workflow zone for each stored instant—or, if your profile uses <strong className="text-mw-text-primary">System default</strong>,
                the zone your browser sends when you click Run. The time you pick still matters near midnight when the zoned date can differ
                from UTC. Gmail&apos;s UI may interpret day boundaries in the mailbox settings; behavior usually matches what users expect
                from the Gmail search box.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                To change the zone for pickers and derived days, update <strong className="text-mw-text-primary">My Profile → Workflow time
                zone</strong>. Changing profile zone does not rewrite existing RFC3339 values; reopen the pickers if you need to adjust
                wall-clock display.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                Use <strong className="text-mw-text-primary">Edit raw RFC3339</strong> for explicit offsets, paste from logs, or edge cases.
            </p>
            <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary mb-1">
                    Current values (RFC3339)
                </div>
                <p className="text-[10px] text-mw-text-secondary mb-1">
                    <span className="font-medium text-mw-text-primary">after:</span>{' '}
                    <code className="font-mono text-[10px] text-mw-text-primary break-all">{afterLine}</code>
                </p>
                <p className="text-[10px] text-mw-text-secondary">
                    <span className="font-medium text-mw-text-primary">before:</span>{' '}
                    <code className="font-mono text-[10px] text-mw-text-primary break-all">{beforeLine}</code>
                </p>
            </div>
        </div>
    );
}
