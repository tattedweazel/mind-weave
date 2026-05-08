import { useEffect, useId } from 'react';
import { X } from 'lucide-react';
import { JsonTreeView } from './JsonTreeView';

export interface EdgePayloadDetailModalProps {
    open: boolean;
    onClose: () => void;
    title?: string;
    payload: unknown;
}

/**
 * Full-width-friendly JSON view of the value that last traveled a canvas edge.
 */
export function EdgePayloadDetailModal({ open, onClose, title = 'Edge payload', payload }: EdgePayloadDetailModalProps) {
    const titleId = useId();

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    if (!open) return null;

    const asTree = payload !== null && typeof payload === 'object';
    const asText =
        typeof payload === 'string'
            ? payload
            : payload == null
              ? 'null'
              : !asTree
                ? String(payload)
                : null;

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
                className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-mw-border shrink-0">
                    <h2 id={titleId} className="text-sm font-semibold text-mw-text-primary leading-snug pr-2">
                        {title}
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-1.5 text-mw-text-secondary hover:text-mw-text-primary rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                    >
                        <X size={18} />
                    </button>
                </div>
                <div className="px-4 py-3 text-xs text-mw-text-primary overflow-y-auto min-h-0 flex-1">
                    {asTree ?
                        <JsonTreeView data={payload} defaultExpandedDepth={4} />
                    :   <pre className="whitespace-pre-wrap break-all font-mono text-[11px] bg-mw-card-alt border border-mw-border rounded-lg p-3 max-h-[70vh] overflow-y-auto">
                            {asText}
                        </pre>
                    }
                </div>
            </div>
        </div>
    );
}
