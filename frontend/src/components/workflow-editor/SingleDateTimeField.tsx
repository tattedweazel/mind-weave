import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
    parseHtmlDateString,
    parseHtmlTimeToHms,
    parseRfc3339ToUtcMs,
    ymdHmsInZone,
    zonedWallTimeToRfc3339Utc,
} from '../../domain/gmailRfc3339Date';

function pad2(n: number): string {
    return String(n).padStart(2, '0');
}

export interface SingleDateTimeFieldProps {
    /** Field label (e.g. slot key or "Value") */
    label: string;
    value: string | null | undefined;
    /** IANA zone from My Profile (`resolveWorkflowTimeZone`); wall-clock pickers + RFC3339 encoding. */
    timeZone: string;
    onChange: (v: string | null) => void;
    /** When false, omit the workflow time zone hint line (e.g. compact wizard). */
    showZoneHint?: boolean;
}

/**
 * One RFC3339 instant: native date + time, optional raw RFC3339 edit (matches Gmail / Calendar Explorer skills).
 */
export function SingleDateTimeField({
    label,
    value,
    timeZone,
    onChange,
    showZoneHint = true,
}: SingleDateTimeFieldProps) {
    const [showRaw, setShowRaw] = useState(false);

    const ms = value?.trim() ? parseRfc3339ToUtcMs(String(value)) : null;
    const local = ms != null ? ymdHmsInZone(ms, timeZone) : null;
    const ymd = local ? `${local.y}-${pad2(local.m)}-${pad2(local.d)}` : '';
    const timeInput = local ? `${pad2(local.h)}:${pad2(local.mi)}` : '';

    const apply = (dateStr: string, timeStr: string) => {
        if (!dateStr?.trim()) {
            onChange(null);
            return;
        }
        const parts = parseHtmlDateString(dateStr);
        if (!parts) {
            return;
        }
        const hms = parseHtmlTimeToHms(timeStr || '00:00');
        if (!hms) {
            return;
        }
        const iso = zonedWallTimeToRfc3339Utc(parts.y, parts.m, parts.d, hms.h, hms.mi, hms.s, timeZone);
        if (iso) {
            onChange(iso);
        }
    };

    const hint = useMemo(
        () => (
            <span className="text-[10px] text-mw-text-secondary">
                Wall clock uses your{' '}
                <strong className="text-mw-text-primary">My Profile → Workflow time zone</strong>.
            </span>
        ),
        [],
    );

    return (
        <div className="space-y-3">
            {showZoneHint ? <div className="flex items-center gap-1 flex-wrap">{hint}</div> : null}

            <div>
                <div className="flex items-center justify-between gap-2 mb-1">
                    <label className="text-xs font-medium text-mw-text-secondary">{label}</label>
                    {ymd && (
                        <button
                            type="button"
                            onClick={() => onChange(null)}
                            className="text-[10px] text-mw-primary hover:underline"
                        >
                            Clear
                        </button>
                    )}
                </div>
                <div className="flex flex-wrap gap-2">
                    <input
                        type="date"
                        value={ymd}
                        onChange={e => apply(e.target.value, timeInput || '00:00')}
                        className="min-w-0 flex-1 px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                    />
                    <input
                        type="time"
                        step={60}
                        value={timeInput}
                        onChange={e => apply(ymd, e.target.value)}
                        disabled={!ymd}
                        className="w-[7.5rem] px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg disabled:opacity-50"
                    />
                </div>
            </div>

            <button
                type="button"
                onClick={() => setShowRaw(!showRaw)}
                className="flex items-center gap-1 text-[11px] font-medium text-mw-primary hover:underline"
                aria-expanded={showRaw}
            >
                {showRaw ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Edit raw RFC3339
            </button>
            {showRaw && (
                <div className="pl-1 border-l-2 border-mw-border">
                    <label className="text-xs font-medium text-mw-text-secondary block mb-1">RFC3339</label>
                    <input
                        value={String(value ?? '')}
                        onChange={e => {
                            const v = e.target.value;
                            onChange(v === '' ? null : v);
                        }}
                        placeholder="e.g. 2026-03-01T15:00:00Z"
                        className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg font-mono text-mw-text-primary"
                    />
                </div>
            )}
        </div>
    );
}
