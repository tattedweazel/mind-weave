import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ContextHelpModal } from '../ContextHelpModal';
import { GmailTimeLimitsHelpContent } from './gmailTimeLimitsHelpContent';
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

export interface GmailBoundaryDateFieldsProps {
    afterValue: string | null | undefined;
    beforeValue: string | null | undefined;
    /** IANA zone from My Profile (`resolveWorkflowTimeZone`); wall-clock pickers + RFC3339 encoding. */
    timeZone: string;
    onAfterChange: (v: string | null) => void;
    onBeforeChange: (v: string | null) => void;
}

/**
 * Native date + time for Gmail List After/Before (RFC3339). Time zone comes from user profile.
 */
export function GmailBoundaryDateFields({
    afterValue,
    beforeValue,
    timeZone,
    onAfterChange,
    onBeforeChange,
}: GmailBoundaryDateFieldsProps) {
    const [showRaw, setShowRaw] = useState(false);

    const afterMs = afterValue?.trim() ? parseRfc3339ToUtcMs(String(afterValue)) : null;
    const beforeMs = beforeValue?.trim() ? parseRfc3339ToUtcMs(String(beforeValue)) : null;

    const afterLocal = afterMs != null ? ymdHmsInZone(afterMs, timeZone) : null;
    const beforeLocal = beforeMs != null ? ymdHmsInZone(beforeMs, timeZone) : null;
    const afterYmd = afterLocal ? `${afterLocal.y}-${pad2(afterLocal.m)}-${pad2(afterLocal.d)}` : '';
    const beforeYmd = beforeLocal ? `${beforeLocal.y}-${pad2(beforeLocal.m)}-${pad2(beforeLocal.d)}` : '';
    const afterTimeInput = afterLocal ? `${pad2(afterLocal.h)}:${pad2(afterLocal.mi)}` : '';
    const beforeTimeInput = beforeLocal ? `${pad2(beforeLocal.h)}:${pad2(beforeLocal.mi)}` : '';

    const applyAfter = (dateStr: string, timeStr: string) => {
        if (!dateStr?.trim()) {
            onAfterChange(null);
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
            onAfterChange(iso);
        }
    };

    const applyBefore = (dateStr: string, timeStr: string) => {
        if (!dateStr?.trim()) {
            onBeforeChange(null);
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
            onBeforeChange(iso);
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
            <div className="flex items-center gap-1 flex-wrap">
                {hint}
                <ContextHelpModal title="Gmail time limits" triggerLabel="Gmail After and Before help">
                    <GmailTimeLimitsHelpContent afterValue={afterValue} beforeValue={beforeValue} />
                </ContextHelpModal>
            </div>

            <div className="grid gap-3 sm:grid-cols-1">
                <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <label className="text-xs font-medium text-mw-text-secondary">After (optional)</label>
                        {afterYmd && (
                            <button
                                type="button"
                                onClick={() => onAfterChange(null)}
                                className="text-[10px] text-mw-primary hover:underline"
                            >
                                Clear
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <input
                            type="date"
                            value={afterYmd}
                            onChange={e => applyAfter(e.target.value, afterTimeInput || '00:00')}
                            className="min-w-0 flex-1 px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                        />
                        <input
                            type="time"
                            step={60}
                            value={afterTimeInput}
                            onChange={e => applyAfter(afterYmd, e.target.value)}
                            disabled={!afterYmd}
                            className="w-[7.5rem] px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg disabled:opacity-50"
                        />
                    </div>
                </div>

                <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <label className="text-xs font-medium text-mw-text-secondary">Before (optional, exclusive)</label>
                        {beforeYmd && (
                            <button
                                type="button"
                                onClick={() => onBeforeChange(null)}
                                className="text-[10px] text-mw-primary hover:underline"
                            >
                                Clear
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <input
                            type="date"
                            value={beforeYmd}
                            onChange={e => applyBefore(e.target.value, beforeTimeInput || '00:00')}
                            className="min-w-0 flex-1 px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                        />
                        <input
                            type="time"
                            step={60}
                            value={beforeTimeInput}
                            onChange={e => applyBefore(beforeYmd, e.target.value)}
                            disabled={!beforeYmd}
                            className="w-[7.5rem] px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg disabled:opacity-50"
                        />
                    </div>
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
                <div className="space-y-2 pl-1 border-l-2 border-mw-border">
                    <div>
                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">After (RFC3339)</label>
                        <input
                            value={String(afterValue ?? '')}
                            onChange={e => {
                                const v = e.target.value;
                                onAfterChange(v === '' ? null : v);
                            }}
                            placeholder="e.g. 2026-03-01T15:00:00Z"
                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg font-mono text-mw-text-primary"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">Before (RFC3339)</label>
                        <input
                            value={String(beforeValue ?? '')}
                            onChange={e => {
                                const v = e.target.value;
                                onBeforeChange(v === '' ? null : v);
                            }}
                            placeholder="e.g. 2026-03-10T17:00:00Z"
                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg font-mono text-mw-text-primary"
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
