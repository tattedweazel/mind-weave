import React, { useEffect, useId, useState } from 'react';
import { Info, X } from 'lucide-react';

export interface ContextHelpModalProps {
    title: string;
    /** Visible label for the icon-only trigger (accessibility). */
    triggerLabel?: string;
    children: React.ReactNode;
}

/**
 * Inline info icon that opens a compact modal for contextual help (inspector fields, syntax primers).
 * Prefer short copy and links to canonical docs—not a second full-screen manager.
 */
export function ContextHelpModal({ title, triggerLabel = 'More information', children }: ContextHelpModalProps) {
    const [open, setOpen] = useState(false);
    const titleId = useId();

    useEffect(() => {
        if (!open) return;
        const onDocKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', onDocKey);
        return () => document.removeEventListener('keydown', onDocKey);
    }, [open]);

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label={triggerLabel}
                aria-expanded={open}
                aria-haspopup="dialog"
                className="inline-flex p-0.5 rounded text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card-alt transition-colors shrink-0"
            >
                <Info size={14} strokeWidth={2} />
            </button>
            {open && (
                <div
                    data-testid="context-help-backdrop"
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
                    onClick={() => setOpen(false)}
                    role="presentation"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby={titleId}
                        className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden"
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-mw-border shrink-0">
                            <h2 id={titleId} className="text-sm font-semibold text-mw-text-primary leading-snug pr-2">
                                {title}
                            </h2>
                            <button
                                type="button"
                                onClick={() => setOpen(false)}
                                aria-label="Close"
                                className="p-1.5 text-mw-text-secondary hover:text-mw-text-primary rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="px-4 py-3 text-xs text-mw-text-primary overflow-y-auto min-h-0">{children}</div>
                    </div>
                </div>
            )}
        </>
    );
}
