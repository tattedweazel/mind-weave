/**
 * GUI-oriented summary for node run output (`details.output_explorer`).
 */

import { useState } from 'react';
import { AlertCircle, Box, Braces, Calendar, Copy, Hash, List, Mail, ToggleLeft, Type } from 'lucide-react';
import type { OutputExplorerItem, OutputExplorerV1 } from '../../api/types';
import { useCopyWithFeedback } from '../../contexts/ClipboardFeedbackContext';
import {
    formatListOrDictionaryForClipboard,
    formatValueForPrimitiveClipboard,
} from '../../domain/formatValueForPrimitiveClipboard';
import type { OutputExplorerExpandNoRowsDetail } from '../../domain/clientOutputExplorerForInputField';
import { formatCalendarEventRangeForZone } from '../../domain/gmailRfc3339Date';
import { OutputExplorerDetailModal } from './OutputExplorerDetailModal';

export interface OutputExplorerProps {
    explorer: OutputExplorerV1;
    /** Serialized node output (`NodeOutputUnion` shape) from the same run row. */
    nodeOutput: unknown;
    /**
     * IANA zone from **My Profile → Workflow time zone** (resolved). Used for calendar list rows + modal.
     */
    calendarDisplayTimeZone?: string;
    /**
     * When list/dict container copy is absent (e.g. scalar primitive explorers), optional header **Copy** text.
     */
    headerClipboardText?: string;
    /** `aria-label` for {@link headerClipboardText} copy control. */
    headerClipboardAriaLabel?: string;
    /**
     * When set, makes the header (title + detail lines) open the detail modal with this payload and title/subtitle
     * overrides (e.g. Inputs scalars; Last Run **Output** full `nodeOutput` when rows exist — row clicks stay per-item).
     */
    expandNoRowsDetail?: OutputExplorerExpandNoRowsDetail;
}

function asRecord(v: unknown): Record<string, unknown> | null {
    return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function rowPayload(explorer: OutputExplorerV1, nodeOutput: unknown, item: OutputExplorerItem): unknown {
    const kind = explorer.kind;
    const root = asRecord(nodeOutput);
    const data = root?.data;

    if (kind === 'gmail_list_messages') {
        if (root?.kind === 'list' && Array.isArray(data)) {
            return data[item.index] ?? null;
        }
        if (data && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as Record<string, unknown>).messages)) {
            const messages = (data as Record<string, unknown>).messages as unknown[];
            return messages[item.index] ?? null;
        }
        return null;
    }
    if (kind === 'calendar_list_events') {
        if (data && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as Record<string, unknown>).events)) {
            const events = (data as Record<string, unknown>).events as unknown[];
            return events[item.index] ?? null;
        }
        return null;
    }
    if (kind === 'list_primitive') {
        if (Array.isArray(data)) {
            return data[item.index] ?? null;
        }
        return null;
    }
    if (kind === 'dictionary_primitive') {
        if (data && typeof data === 'object' && !Array.isArray(data)) {
            return (data as Record<string, unknown>)[item.primary_line];
        }
        return null;
    }
    if (kind === 'start_outputs') {
        const outs = root?.outputs;
        if (outs && typeof outs === 'object' && !Array.isArray(outs)) {
            return (outs as Record<string, unknown>)[item.primary_line];
        }
        return null;
    }
    return null;
}

function formattedCalendarSecondary(
    nodeOutput: unknown,
    item: OutputExplorerItem,
    timeZone: string | undefined,
): string | undefined {
    const tz = timeZone?.trim();
    if (!tz) {
        return undefined;
    }
    const root = asRecord(nodeOutput)?.data;
    if (!root || typeof root !== 'object' || Array.isArray(root)) {
        return undefined;
    }
    const events = (root as Record<string, unknown>).events;
    if (!Array.isArray(events)) {
        return undefined;
    }
    const ev = events[item.index];
    if (!ev || typeof ev !== 'object') {
        return undefined;
    }
    const o = ev as Record<string, unknown>;
    const start = String(o.start ?? '').trim();
    const end = String(o.end ?? '').trim();
    if (!start && !end) {
        return undefined;
    }
    const line = formatCalendarEventRangeForZone(start, end, tz);
    return line || undefined;
}

function iconForKind(kind: string) {
    switch (kind) {
        case 'gmail_list_messages':
            return Mail;
        case 'calendar_list_events':
            return Calendar;
        case 'list_primitive':
            return List;
        case 'dictionary_primitive':
            return Braces;
        case 'string_primitive':
            return Type;
        case 'int_primitive':
            return Hash;
        case 'boolean_primitive':
            return ToggleLeft;
        case 'start_outputs':
            return Braces;
        default:
            return Box;
    }
}

function showRowCopy(kind: string): boolean {
    return (
        kind === 'list_primitive' ||
        kind === 'dictionary_primitive' ||
        kind === 'start_outputs'
    );
}

function listOrDictionaryContainerData(
    kind: string,
    nodeOutput: unknown,
): { mode: 'list' | 'dictionary'; data: unknown } | null {
    const root = asRecord(nodeOutput);
    const data = root?.data;
    if (kind === 'list_primitive' && Array.isArray(data)) {
        return { mode: 'list', data };
    }
    if (kind === 'dictionary_primitive' && data !== null && typeof data === 'object' && !Array.isArray(data)) {
        return { mode: 'dictionary', data };
    }
    if (kind === 'start_outputs') {
        const outs = root?.outputs;
        if (outs !== null && typeof outs === 'object' && !Array.isArray(outs)) {
            return { mode: 'dictionary', data: outs };
        }
    }
    return null;
}

type ExplorerModalState =
    | { source: 'row'; item: OutputExplorerItem }
    | { source: 'header'; item: OutputExplorerItem; payload: unknown };

function syntheticItemForExpandHeader(d: OutputExplorerExpandNoRowsDetail): OutputExplorerItem {
    const sub = d.subtitle.trim();
    return {
        index: 0,
        row_state: 'ok',
        primary_line: d.title,
        secondary_line: sub,
        teaser: '',
        badges: [],
        inferred_primitive: sub,
    };
}

export function OutputExplorer({
    explorer,
    nodeOutput,
    calendarDisplayTimeZone,
    headerClipboardText,
    headerClipboardAriaLabel,
    expandNoRowsDetail,
}: OutputExplorerProps) {
    const copyWithFeedback = useCopyWithFeedback();
    const Icon = iconForKind(explorer.kind);
    const details = explorer.summary.detail_lines?.filter((s) => s.trim()) ?? [];
    const [modal, setModal] = useState<ExplorerModalState | null>(null);
    const headerOpensModal = expandNoRowsDetail != null;
    const containerCopy = listOrDictionaryContainerData(explorer.kind, nodeOutput);
    const containerClipboardText =
        containerCopy ? formatListOrDictionaryForClipboard(containerCopy.data, containerCopy.mode) : '';
    const scalarHeaderCopy = (headerClipboardText ?? '').trim();
    const showHeaderCopy = containerCopy !== null || scalarHeaderCopy.length > 0;
    const headerCopyText = containerCopy ? containerClipboardText : scalarHeaderCopy;
    const headerCopyAria =
        containerCopy ?
            containerCopy.mode === 'list' ?
                'Copy entire list as JSON for a List input'
            :   'Copy entire dictionary as JSON for a Dictionary input'
        :   (headerClipboardAriaLabel?.trim() || 'Copy value to clipboard');

    const modalItem = modal?.item ?? null;
    const modalPayload =
        modal?.source === 'row' ? rowPayload(explorer, nodeOutput, modal.item)
        : modal?.source === 'header' ? modal.payload
        : null;
    const modalTitleOverride = modal?.source === 'header' ? expandNoRowsDetail?.title : undefined;
    const modalSubtitleOverride = modal?.source === 'header' ? expandNoRowsDetail?.subtitle : undefined;

    return (
        <div className="rounded-lg border border-mw-border bg-mw-card-alt/80 overflow-hidden">
            <div className="group/header flex items-start gap-2 px-2.5 py-2 border-b border-mw-border bg-mw-card/60 relative">
                <Icon size={16} className="text-mw-primary shrink-0 mt-0.5" strokeWidth={2} />
                <div className="min-w-0 flex-1 pr-8">
                    {headerOpensModal && expandNoRowsDetail ?
                        <button
                            type="button"
                            onClick={() =>
                                setModal({
                                    source: 'header',
                                    item: syntheticItemForExpandHeader(expandNoRowsDetail),
                                    payload: expandNoRowsDetail.payload,
                                })
                            }
                            aria-label={`Open full value: ${explorer.summary.line}`}
                            className="w-full text-left rounded-md -mx-1 px-1 py-0.5 hover:bg-mw-card/50 transition-colors cursor-pointer bg-transparent"
                        >
                            <div className="text-xs font-medium text-mw-text-primary leading-snug">{explorer.summary.line}</div>
                            {details.length > 0 && (
                                <ul className="mt-1 text-[10px] text-mw-text-secondary space-y-0.5 list-disc list-inside">
                                    {details.map((line) => (
                                        <li key={line} className="leading-snug">
                                            {line}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </button>
                    :   <>
                            <div className="text-xs font-medium text-mw-text-primary leading-snug">{explorer.summary.line}</div>
                            {details.length > 0 && (
                                <ul className="mt-1 text-[10px] text-mw-text-secondary space-y-0.5 list-disc list-inside">
                                    {details.map((line) => (
                                        <li key={line} className="leading-snug">
                                            {line}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </>
                    }
                </div>
                {showHeaderCopy ?
                    <button
                        type="button"
                        className="absolute right-2 top-2 p-1 rounded-md text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card/80 opacity-0 group-hover/header:opacity-100 focus:opacity-100 transition-opacity shrink-0"
                        aria-label={headerCopyAria}
                        onClick={() => {
                            void copyWithFeedback(headerCopyText);
                        }}
                    >
                        <Copy size={14} strokeWidth={2} />
                    </button>
                :   null}
            </div>
            {explorer.items.length > 0 ?
                <div className="max-h-72 overflow-y-auto divide-y divide-mw-border">
                    {explorer.items.map((item) => {
                        const err = item.row_state === 'error';
                        const secondaryLine =
                            explorer.kind === 'calendar_list_events' ?
                                formattedCalendarSecondary(nodeOutput, item, calendarDisplayTimeZone) ?? item.secondary_line
                            :   item.secondary_line;
                        const payload = rowPayload(explorer, nodeOutput, item);
                        const copyKind = showRowCopy(explorer.kind);
                        const copyText =
                            copyKind ? formatValueForPrimitiveClipboard(payload, item.inferred_primitive) : '';

                        return (
                            <div key={`out-ex-row-${item.index}`} className="group relative">
                                <button
                                    type="button"
                                    onClick={() => setModal({ source: 'row', item })}
                                    aria-label={
                                        explorer.kind === 'gmail_list_messages' ?
                                            `Open email preview: ${item.primary_line}`
                                        : explorer.kind === 'calendar_list_events' ?
                                            `Open event preview: ${item.primary_line}`
                                        :   `Open details: ${item.primary_line}`
                                    }
                                    className="w-full text-left px-2.5 py-2 hover:bg-mw-card/50 transition-colors cursor-pointer bg-transparent"
                                >
                                    <div className="flex items-start gap-2 pr-7">
                                        {err ?
                                            <AlertCircle size={14} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                                        :   <span className="w-[14px] shrink-0" />}
                                        <div className="min-w-0 flex-1">
                                            <div
                                                className={`text-xs font-medium leading-snug ${err ? 'text-amber-800 dark:text-amber-200/90' : 'text-mw-text-primary'}`}
                                            >
                                                {item.primary_line}
                                            </div>
                                            {secondaryLine ?
                                                <div className="text-[10px] text-mw-text-secondary mt-0.5 leading-snug">{secondaryLine}</div>
                                            :   null}
                                            {item.teaser ?
                                                <div className="text-[10px] text-mw-text-secondary/90 mt-1 line-clamp-2 leading-snug">{item.teaser}</div>
                                            :   null}
                                            {item.badges.length > 0 && (
                                                <div className="flex flex-wrap gap-1 mt-1.5">
                                                    {item.badges.map((b) => (
                                                        <span
                                                            key={b}
                                                            className="inline-block text-[9px] font-medium uppercase tracking-wide px-1 py-px rounded bg-mw-page text-mw-text-secondary border border-mw-border"
                                                        >
                                                            {b}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </button>
                                {copyKind && copyText !== '' ?
                                    <button
                                        type="button"
                                        className="absolute right-2 top-2 p-1 rounded-md text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card/80 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
                                        aria-label="Copy value to clipboard"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            void copyWithFeedback(copyText);
                                        }}
                                    >
                                        <Copy size={14} strokeWidth={2} />
                                    </button>
                                :   null}
                            </div>
                        );
                    })}
                </div>
            :   null}
            {explorer.overflow_count != null && explorer.overflow_count > 0 && (
                <div className="px-2.5 py-1.5 text-[10px] text-mw-text-secondary border-t border-mw-border bg-mw-card/40 text-center">
                    + {explorer.overflow_count} more in raw output (capped at {explorer.items.length} rows here)
                </div>
            )}
            <OutputExplorerDetailModal
                open={modal !== null}
                onClose={() => setModal(null)}
                kind={explorer.kind}
                item={modalItem}
                payload={modalPayload}
                calendarDisplayTimeZone={explorer.kind === 'calendar_list_events' ? calendarDisplayTimeZone : undefined}
                titleOverride={modalTitleOverride}
                subtitleOverride={modalSubtitleOverride}
            />
        </div>
    );
}
