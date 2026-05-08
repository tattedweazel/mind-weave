import React, { useCallback, useEffect, useId, useState } from 'react';
import { ExternalLink as ExternalLinkIcon, X } from 'lucide-react';

function crossOriginHttpUrl(href: string): boolean {
    try {
        const base = typeof window !== 'undefined' ? window.location.href : 'https://placeholder.local/';
        const u = new URL(href, base);
        if (u.protocol !== 'http:' && u.protocol !== 'https:') {
            return false;
        }
        if (typeof window === 'undefined') {
            return true;
        }
        return u.origin !== window.location.origin;
    } catch {
        return false;
    }
}

export interface ExternalLinkProps extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'target' | 'rel'> {
    href: string;
    children: React.ReactNode;
    /**
     * When true, skip the "leave this site" confirmation for cross-origin http(s) links.
     * Use for low-friction cases (e.g. repeated docs the user already chose to open).
     * Default false: first-party UX shows confirm for outbound navigations.
     */
    skipLeaveConfirmation?: boolean;
}

/**
 * External URL opened in a new tab: shows an outbound icon and (by default) confirms before navigating.
 */
export function ExternalLink({
    href,
    children,
    className = '',
    skipLeaveConfirmation = false,
    onClick,
    ...rest
}: ExternalLinkProps) {
    const [confirmOpen, setConfirmOpen] = useState(false);
    const titleId = useId();
    const needsConfirm = crossOriginHttpUrl(href) && !skipLeaveConfirmation;
    const showOutboundIcon = href.startsWith('http://') || href.startsWith('https://');

    const proceed = useCallback(() => {
        window.open(href, '_blank', 'noopener,noreferrer');
    }, [href]);

    useEffect(() => {
        if (!confirmOpen) {
            return;
        }
        const onDocKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setConfirmOpen(false);
            }
        };
        document.addEventListener('keydown', onDocKey);
        return () => document.removeEventListener('keydown', onDocKey);
    }, [confirmOpen]);

    const handleClick = useCallback(
        (e: React.MouseEvent<HTMLAnchorElement>) => {
            onClick?.(e);
            if (e.defaultPrevented) {
                return;
            }
            if (!needsConfirm) {
                return;
            }
            e.preventDefault();
            setConfirmOpen(true);
        },
        [needsConfirm, onClick],
    );

    return (
        <>
            <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-1 ${className}`.trim()}
                onClick={handleClick}
                {...rest}
            >
                <span className="inline-flex items-center gap-1">
                    {children}
                    {showOutboundIcon && (
                        <ExternalLinkIcon className="shrink-0 text-mw-text-secondary opacity-90" size={12} aria-hidden />
                    )}
                </span>
                <span className="sr-only"> (opens in new tab)</span>
            </a>
            {confirmOpen && (
                <div
                    data-testid="external-link-confirm-backdrop"
                    className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
                    onClick={() => setConfirmOpen(false)}
                    role="presentation"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby={titleId}
                        className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-md flex flex-col overflow-hidden"
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-mw-border">
                            <h2 id={titleId} className="text-sm font-semibold text-mw-text-primary leading-snug">
                                Open external site?
                            </h2>
                            <button
                                type="button"
                                onClick={() => setConfirmOpen(false)}
                                aria-label="Close"
                                className="p-1.5 text-mw-text-secondary hover:text-mw-text-primary rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="px-4 py-3 text-xs text-mw-text-secondary space-y-2">
                            <p>You are about to visit a site outside Mind Weave.</p>
                            <p className="font-mono text-[11px] break-all text-mw-text-primary">{href}</p>
                        </div>
                        <div className="flex justify-end gap-2 px-4 py-3 border-t border-mw-border bg-mw-card-alt/50">
                            <button
                                type="button"
                                onClick={() => setConfirmOpen(false)}
                                className="px-3 py-1.5 text-xs font-medium text-mw-text-primary rounded-lg hover:bg-mw-card transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setConfirmOpen(false);
                                    proceed();
                                }}
                                className="px-3 py-1.5 text-xs font-medium text-white bg-mw-primary hover:opacity-90 rounded-lg transition-colors"
                            >
                                Continue
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
