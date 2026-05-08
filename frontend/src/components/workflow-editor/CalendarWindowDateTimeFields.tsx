import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ContextHelpModal } from '../ContextHelpModal';
import { CalendarTimeWindowHelpContent } from './calendarTimeWindowHelpContent';
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

export interface CalendarWindowDateTimeFieldsProps {
    timeMinValue: string | null | undefined;
    timeMaxValue: string | null | undefined;
    /** IANA zone from My Profile (`resolveWorkflowTimeZone`); wall-clock pickers + RFC3339 encoding. */
    timeZone: string;
    onTimeMinChange: (v: string | null) => void;
    onTimeMaxChange: (v: string | null) => void;
}

/**
 * Native date + time for Calendar List `time_min` / `time_max` (RFC3339). Time zone comes from user profile.
 */
export function CalendarWindowDateTimeFields({
    timeMinValue,
    timeMaxValue,
    timeZone,
    onTimeMinChange,
    onTimeMaxChange,
}: CalendarWindowDateTimeFieldsProps) {
    const [showRaw, setShowRaw] = useState(false);

    const tminMs = timeMinValue?.trim() ? parseRfc3339ToUtcMs(String(timeMinValue)) : null;
    const tmaxMs = timeMaxValue?.trim() ? parseRfc3339ToUtcMs(String(timeMaxValue)) : null;

    const minLocal = tminMs != null ? ymdHmsInZone(tminMs, timeZone) : null;
    const maxLocal = tmaxMs != null ? ymdHmsInZone(tmaxMs, timeZone) : null;
    const minYmd = minLocal ? `${minLocal.y}-${pad2(minLocal.m)}-${pad2(minLocal.d)}` : '';
    const maxYmd = maxLocal ? `${maxLocal.y}-${pad2(maxLocal.m)}-${pad2(maxLocal.d)}` : '';
    const minTimeInput = minLocal ? `${pad2(minLocal.h)}:${pad2(minLocal.mi)}` : '';
    const maxTimeInput = maxLocal ? `${pad2(maxLocal.h)}:${pad2(maxLocal.mi)}` : '';

    const applyMin = (dateStr: string, timeStr: string) => {
        if (!dateStr?.trim()) {
            onTimeMinChange(null);
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
            onTimeMinChange(iso);
        }
    };

    const applyMax = (dateStr: string, timeStr: string) => {
        if (!dateStr?.trim()) {
            onTimeMaxChange(null);
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
            onTimeMaxChange(iso);
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
                <ContextHelpModal title="Calendar time window" triggerLabel="Calendar time window help">
                    <CalendarTimeWindowHelpContent timeMinValue={timeMinValue} timeMaxValue={timeMaxValue} />
                </ContextHelpModal>
            </div>

            <div className="grid gap-3 sm:grid-cols-1">
                <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <label className="text-xs font-medium text-mw-text-secondary">Start (time_min)</label>
                        {minYmd && (
                            <button
                                type="button"
                                onClick={() => onTimeMinChange(null)}
                                className="text-[10px] text-mw-primary hover:underline"
                            >
                                Clear
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <input
                            type="date"
                            value={minYmd}
                            onChange={e => applyMin(e.target.value, minTimeInput || '00:00')}
                            className="min-w-0 flex-1 px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                        />
                        <input
                            type="time"
                            step={60}
                            value={minTimeInput}
                            onChange={e => applyMin(minYmd, e.target.value)}
                            disabled={!minYmd}
                            className="w-[7.5rem] px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg disabled:opacity-50"
                        />
                    </div>
                </div>

                <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <label className="text-xs font-medium text-mw-text-secondary">End (time_max)</label>
                        {maxYmd && (
                            <button
                                type="button"
                                onClick={() => onTimeMaxChange(null)}
                                className="text-[10px] text-mw-primary hover:underline"
                            >
                                Clear
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <input
                            type="date"
                            value={maxYmd}
                            onChange={e => applyMax(e.target.value, maxTimeInput || '00:00')}
                            className="min-w-0 flex-1 px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                        />
                        <input
                            type="time"
                            step={60}
                            value={maxTimeInput}
                            onChange={e => applyMax(maxYmd, e.target.value)}
                            disabled={!maxYmd}
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
                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">time_min (RFC3339)</label>
                        <input
                            value={String(timeMinValue ?? '')}
                            onChange={e => {
                                const v = e.target.value;
                                onTimeMinChange(v === '' ? null : v);
                            }}
                            placeholder="e.g. 2026-03-01T15:00:00Z"
                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg font-mono text-mw-text-primary"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-mw-text-secondary block mb-1">time_max (RFC3339)</label>
                        <input
                            value={String(timeMaxValue ?? '')}
                            onChange={e => {
                                const v = e.target.value;
                                onTimeMaxChange(v === '' ? null : v);
                            }}
                            placeholder="e.g. 2026-03-01T17:00:00Z"
                            className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card rounded-lg font-mono text-mw-text-primary"
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
