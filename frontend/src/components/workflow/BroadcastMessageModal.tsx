import React, { useCallback, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Megaphone } from 'lucide-react';

import {
    type BroadcastSegment,
    normalizeBroadcastSeverity,
    severityAccentClass,
} from '../../domain/broadcastMessage';

export interface BroadcastMessageModalProps {
    segments: BroadcastSegment[];
    onContinue: () => void;
    /** When true, show a lightweight loading state on Continue (Build ack in flight). */
    continuing?: boolean;
}

const previewProseClass =
    'prose prose-sm dark:prose-invert max-w-none ' +
    'prose-headings:text-mw-text-primary prose-headings:mb-2 prose-headings:mt-0 ' +
    'prose-p:text-mw-text-primary prose-p:my-2 ' +
    'prose-a:text-mw-primary prose-a:no-underline hover:prose-a:underline ' +
    'prose-strong:text-mw-text-primary prose-code:text-mw-text-primary ' +
    'prose-li:marker:text-mw-text-secondary prose-pre:bg-mw-card-alt prose-pre:border prose-pre:border-mw-border';

function SegmentBody({ segment }: { segment: BroadcastSegment }) {
    if (segment.render_markdown) {
        return (
            <div className={previewProseClass}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{segment.body}</ReactMarkdown>
            </div>
        );
    }
    return <p className="whitespace-pre-wrap text-sm leading-relaxed text-mw-text-primary">{segment.body}</p>;
}

export const BroadcastMessageModal: React.FC<BroadcastMessageModalProps> = ({
    segments,
    onContinue,
    continuing = false,
}) => {
    const continueRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        continueRef.current?.focus();
    }, []);

    const handleKeyDown = useCallback(
        (event: React.KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                onContinue();
            }
        },
        [onContinue],
    );

    if (!segments.length) return null;

    const multi = segments.length > 1;

    return (
        <div
            className="fixed inset-0 z-[120] flex items-center justify-center p-4"
            role="presentation"
            onKeyDown={handleKeyDown}
        >
            <div
                className="absolute inset-0 bg-black/45 backdrop-blur-[2px]"
                aria-hidden
                onClick={onContinue}
            />
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="broadcast-message-title"
                className="relative z-10 flex max-h-[min(88vh,40rem)] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-mw-border bg-mw-card shadow-2xl"
            >
                <div className="flex items-center gap-2 border-b border-mw-border bg-mw-page/80 px-5 py-4">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-mw-primary-muted text-mw-primary">
                        <Megaphone className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                        <h2
                            id="broadcast-message-title"
                            className="text-base font-semibold text-mw-text-primary"
                        >
                            {multi ? 'Broadcast messages' : segments[0].title?.trim() || 'Broadcast message'}
                        </h2>
                        <p className="text-xs text-mw-text-secondary">
                            {multi
                                ? `${segments.length} messages from this run`
                                : 'Review the message below, then continue.'}
                        </p>
                    </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 space-y-4">
                    {segments.map((segment, index) => {
                        const severity = normalizeBroadcastSeverity(segment.severity);
                        return (
                            <section
                                key={`${segment.node_id}-${index}`}
                                className={`rounded-xl border border-mw-border border-t-[3px] px-4 py-3 ${severityAccentClass(severity)}`}
                            >
                                <div className="mb-2 space-y-1.5">
                                    {segment.source ? (
                                        <span className="inline-flex max-w-full rounded-full bg-mw-card-alt px-2 py-0.5 text-[10px] font-medium text-mw-text-secondary">
                                            {segment.source}
                                        </span>
                                    ) : null}
                                    {segment.title || multi ? (
                                        <div className="flex flex-wrap items-center gap-2">
                                            {multi ? (
                                                <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-mw-card-alt px-1.5 text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary">
                                                    {index + 1}
                                                </span>
                                            ) : null}
                                            {segment.title ? (
                                                <h3 className="text-sm font-semibold text-mw-text-primary">{segment.title}</h3>
                                            ) : multi ? (
                                                <h3 className="text-sm font-medium text-mw-text-secondary">Message {index + 1}</h3>
                                            ) : null}
                                        </div>
                                    ) : null}
                                </div>
                                <SegmentBody segment={segment} />
                            </section>
                        );
                    })}
                </div>

                <div className="flex justify-end border-t border-mw-border bg-mw-page/60 px-5 py-4">
                    <button
                        ref={continueRef}
                        type="button"
                        disabled={continuing}
                        onClick={onContinue}
                        className="inline-flex min-w-[7rem] items-center justify-center rounded-lg bg-mw-primary px-4 py-2 text-sm font-medium text-white transition hover:bg-mw-primary-hover disabled:opacity-60"
                    >
                        {continuing ? 'Continuing…' : 'Continue'}
                    </button>
                </div>
            </div>
        </div>
    );
};
