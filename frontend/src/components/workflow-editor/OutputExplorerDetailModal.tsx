/**
 * Modal detail view for Output explorer rows: native preview + raw JSON.
 */

import { useEffect, useId, useState } from 'react';
import { ExternalLink as ExternalLinkIcon, X } from 'lucide-react';
import type { OutputExplorerItem, OutputExplorerKind } from '../../api/types';
import { formatCalendarEventRangeForZone } from '../../domain/gmailRfc3339Date';
import { ExternalLink } from '../ExternalLink';
import { JsonTreeView } from './JsonTreeView';
import { PrimitiveValuePreview } from './OutputExplorerPrimitivePreview';

export type OutputExplorerModalView = 'preview' | 'raw';

export interface OutputExplorerDetailModalProps {
    open: boolean;
    onClose: () => void;
    kind: OutputExplorerKind | string;
    item: OutputExplorerItem | null;
    payload: unknown;
    /** IANA zone for Calendar list; formats **When** in preview (raw JSON unchanged). */
    calendarDisplayTimeZone?: string;
    /**
     * When set (non-empty after trim), used as the dialog title instead of `dialogTitleFor(kind, item)`.
     * The line under the title uses `subtitleOverride` (or is omitted when empty).
     */
    titleOverride?: string;
    /** Subtitle under the title when `titleOverride` is used (e.g. input field type). */
    subtitleOverride?: string;
}

function asRecord(v: unknown): Record<string, unknown> | null {
    return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function str(v: unknown): string {
    if (v == null) return '';
    return String(v).trim();
}

function GmailPreview({ msg }: { msg: Record<string, unknown> }) {
    const subject = str(msg.subject) || '(No subject)';
    const from = str(msg.from);
    const to = str(msg.to);
    const date = str(msg.date) || str(msg.internalDate);
    const snippet = str(msg.snippet);
    const body = str(msg.body_text);
    const truncated = msg.body_truncated === true;
    const id = str(msg.id);
    const threadId = str(msg.threadId);
    const err = str(msg.fetch_error);
    const labels = msg.labelIds;

    if (err) {
        return (
            <div className="space-y-3">
                <div className="text-amber-800 dark:text-amber-200/90 text-sm font-medium">Could not load this message</div>
                <pre className="text-xs bg-mw-card-alt border border-mw-border rounded-lg p-3 whitespace-pre-wrap break-words text-mw-text-primary max-h-[40vh] overflow-y-auto font-mono">
                    {err}
                </pre>
                {id ? (
                    <p className="text-[10px] text-mw-text-secondary">
                        Message id: <span className="font-mono text-mw-text-primary">{id}</span>
                    </p>
                ) : null}
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <header className="space-y-1 border-b border-mw-border pb-3">
                <h3 className="text-base font-semibold text-mw-text-primary leading-snug">{subject}</h3>
                <div className="text-[11px] text-mw-text-secondary space-y-0.5">
                    {from ? (
                        <div>
                            <span className="font-medium text-mw-text-primary/90">From</span> {from}
                        </div>
                    ) : null}
                    {to ? (
                        <div>
                            <span className="font-medium text-mw-text-primary/90">To</span> {to}
                        </div>
                    ) : null}
                    {date ? (
                        <div>
                            <span className="font-medium text-mw-text-primary/90">Date</span> {date}
                        </div>
                    ) : null}
                </div>
                {Array.isArray(labels) && labels.length > 0 ? (
                    <div className="flex flex-wrap gap-1 pt-1">
                        {labels.slice(0, 12).map((x) => (
                            <span
                                key={String(x)}
                                className="text-[9px] font-medium uppercase tracking-wide px-1.5 py-px rounded bg-mw-page text-mw-text-secondary border border-mw-border"
                            >
                                {String(x)}
                            </span>
                        ))}
                    </div>
                ) : null}
                {id || threadId ? (
                    <p className="text-[10px] text-mw-text-secondary pt-1 font-mono break-all">
                        {id ? `id: ${id}` : ''}
                        {id && threadId ? ' · ' : ''}
                        {threadId ? `thread: ${threadId}` : ''}
                    </p>
                ) : null}
            </header>
            {snippet && !body ?
                <p className="text-xs text-mw-text-secondary italic">Snippet only (body not loaded).</p>
            : null}
            {body ?
                <section>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary mb-1.5">Body</div>
                    <div
                        className="text-sm text-mw-text-primary whitespace-pre-wrap break-words bg-mw-page/80 dark:bg-mw-card-alt/40 border border-mw-border rounded-lg p-3 max-h-[min(50vh,28rem)] overflow-y-auto leading-relaxed"
                    >
                        {body}
                    </div>
                    {truncated ?
                        <p className="text-[10px] text-amber-800 dark:text-amber-200/80 mt-1.5">
                            Body was truncated at the server limit. Use <strong>View raw</strong> for the full stored field or re-fetch with a smaller message.
                        </p>
                    : null}
                </section>
            : !snippet && !err ?
                <p className="text-xs text-mw-text-secondary italic">No body text in this record.</p>
            : null}
        </div>
    );
}

function CalendarPreview({ ev, displayTimeZone }: { ev: Record<string, unknown>; displayTimeZone?: string }) {
    const title = str(ev.summary) || '(No title)';
    const start = str(ev.start);
    const end = str(ev.end);
    const loc = str(ev.location);
    const status = str(ev.status);
    const htmlLink = str(ev.htmlLink);
    const organizer = asRecord(ev.organizer);
    const tz = displayTimeZone?.trim();
    const whenLine =
        start || end ?
            tz ?
                formatCalendarEventRangeForZone(start, end, tz) || [start, end].filter(Boolean).join(start && end ? ' → ' : '')
            :   [start, end].filter(Boolean).join(start && end ? ' → ' : '')
        :   '';

    return (
        <div className="space-y-4">
            <header className="space-y-2 border-b border-mw-border pb-3">
                <h3 className="text-base font-semibold text-mw-text-primary leading-snug">{title}</h3>
                <div className="text-[11px] text-mw-text-secondary space-y-1">
                    {whenLine ?
                        <div>
                            <span className="font-medium text-mw-text-primary/90">When</span> {whenLine}
                        </div>
                    :   null}
                    {tz ?
                        <p className="text-[10px] text-mw-text-secondary/90">Shown in {tz} (same as Time & limits in the inspector).</p>
                    :   null}
                    {loc ? (
                        <div>
                            <span className="font-medium text-mw-text-primary/90">Where</span> {loc}
                        </div>
                    ) : null}
                    {status ? (
                        <div>
                            <span className="font-medium text-mw-text-primary/90">Status</span> {status}
                        </div>
                    ) : null}
                    {organizer && (str(organizer.email) || str(organizer.displayName)) ?
                        <div>
                            <span className="font-medium text-mw-text-primary/90">Organizer</span>{' '}
                            {[str(organizer.displayName), str(organizer.email)].filter(Boolean).join(' · ')}
                        </div>
                    : null}
                </div>
                {htmlLink ?
                    <ExternalLink
                        href={htmlLink}
                        className="inline-flex items-center gap-1 text-xs text-mw-primary hover:underline"
                    >
                        <ExternalLinkIcon size={12} /> Open in Google Calendar
                    </ExternalLink>
                : null}
            </header>
            <p className="text-[10px] text-mw-text-secondary">
                Recurrence and full metadata are available under <strong>View raw</strong>.
            </p>
        </div>
    );
}

function dialogTitleFor(kind: string, item: OutputExplorerItem): string {
    if (kind === 'gmail_list_messages') {
        return item.row_state === 'error' ? 'Message error' : 'Email';
    }
    if (kind === 'calendar_list_events') {
        return 'Calendar event';
    }
    if (kind === 'list_primitive') {
        return 'List item';
    }
    if (kind === 'dictionary_primitive') {
        return 'Dictionary value';
    }
    if (kind === 'start_outputs') {
        return 'Start output';
    }
    return 'Value';
}

function PreviewBody({
    kind,
    item,
    payload,
    calendarDisplayTimeZone,
}: {
    kind: string;
    item: OutputExplorerItem;
    payload: unknown;
    calendarDisplayTimeZone?: string;
}) {
    const rec = asRecord(payload);
    if (kind === 'gmail_list_messages' && rec) {
        return <GmailPreview msg={rec} />;
    }
    if (kind === 'calendar_list_events' && rec) {
        return <CalendarPreview ev={rec} displayTimeZone={calendarDisplayTimeZone} />;
    }
    const typeHint = item.inferred_primitive?.trim() || item.secondary_line?.trim() || undefined;
    return <PrimitiveValuePreview payload={payload} typeHint={typeHint} />;
}

export function OutputExplorerDetailModal({
    open,
    onClose,
    kind,
    item,
    payload,
    calendarDisplayTimeZone,
    titleOverride,
    subtitleOverride,
}: OutputExplorerDetailModalProps) {
    const titleId = useId();
    const [view, setView] = useState<OutputExplorerModalView>('preview');

    const trimmedOverride = titleOverride?.trim() ?? '';
    const useCustomHeader = trimmedOverride.length > 0;

    useEffect(() => {
        if (open) {
            setView('preview');
        }
    }, [open, item?.index, trimmedOverride]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    if (!open || !item) {
        return null;
    }

    const dialogTitle = useCustomHeader ? trimmedOverride : dialogTitleFor(kind, item);
    const subtitleLine = useCustomHeader ? (subtitleOverride ?? '').trim() : item.primary_line.trim();

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
            onClick={onClose}
            role="presentation"
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-mw-border shrink-0">
                    <div className="min-w-0 flex-1">
                        <h2 id={titleId} className="text-sm font-semibold text-mw-text-primary leading-snug truncate">
                            {dialogTitle}
                        </h2>
                        {subtitleLine ?
                            <p className="text-[11px] text-mw-text-secondary mt-0.5 line-clamp-2">{subtitleLine}</p>
                        :   null}
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-1.5 text-mw-text-secondary hover:text-mw-text-primary rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                    >
                        <X size={18} />
                    </button>
                </div>
                <div className="px-3 py-2 border-b border-mw-border bg-mw-card-alt/40 shrink-0 flex gap-1">
                    <button
                        type="button"
                        onClick={() => setView('preview')}
                        className={`px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide rounded-md transition-colors ${
                            view === 'preview' ?
                                'bg-mw-primary text-white'
                            :   'text-mw-text-secondary hover:bg-mw-card-alt'
                        }`}
                    >
                        Preview
                    </button>
                    <button
                        type="button"
                        onClick={() => setView('raw')}
                        className={`px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide rounded-md transition-colors ${
                            view === 'raw' ?
                                'bg-mw-primary text-white'
                            :   'text-mw-text-secondary hover:bg-mw-card-alt'
                        }`}
                    >
                        View raw
                    </button>
                </div>
                <div className="px-4 py-4 overflow-y-auto min-h-0 flex-1">
                    {view === 'raw' ?
                        payload !== undefined && payload !== null ?
                            <JsonTreeView data={payload} defaultExpandedDepth={4} />
                        :   <p className="text-xs text-mw-text-secondary italic">Nothing to show.</p>
                    :   <PreviewBody
                            kind={kind}
                            item={item}
                            payload={payload}
                            calendarDisplayTimeZone={kind === 'calendar_list_events' ? calendarDisplayTimeZone : undefined}
                        />
                    }
                </div>
            </div>
        </div>
    );
}
