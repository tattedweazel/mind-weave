import React, { useEffect, useState } from 'react';
import { Maximize2, Minimize2, X } from 'lucide-react';

export type ManagerModalMaxWidth = '2xl' | '4xl' | 'full';

export interface ManagerModalProps {
    /** Whether the modal is visible. When false, returns null. */
    isOpen: boolean;
    /** Called when the user closes the modal (close button or backdrop click). */
    onClose: () => void;
    /** Title displayed in the modal header. */
    title: string;
    /** Optional content to the left of the title (e.g. a Back control). */
    leadingSlot?: React.ReactNode;
    /** Maximum width of the modal panel. Defaults to '4xl'. */
    maxWidth?: ManagerModalMaxWidth;
    /** When true, header shows a control to expand the panel to fill the viewport (good for wide canvases). */
    enableFullscreen?: boolean;
    /** Modal body content. Receives flex-1 min-h-0 overflow-hidden for proper layout. */
    children: React.ReactNode;
}

const MAX_WIDTH_CLASSES: Record<ManagerModalMaxWidth, string> = {
    '2xl': 'max-w-2xl',
    '4xl': 'max-w-4xl',
    full: 'max-w-[min(100vw,100%)] w-full',
};

/**
 * Shared modal shell for manager views (Personas, Palettes, Structures, Manage Users, My Settings).
 * Provides consistent overlay, panel, and header styling. Consumers pass their own body content.
 * Clicking the dimmed backdrop calls `onClose`; clicks inside the panel do not.
 */
export const ManagerModal: React.FC<ManagerModalProps> = ({
    isOpen,
    onClose,
    title,
    leadingSlot,
    maxWidth = '4xl',
    enableFullscreen = false,
    children,
}) => {
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        if (!isOpen) setExpanded(false);
    }, [isOpen]);

    if (!isOpen) return null;

    const maxWidthClass = MAX_WIDTH_CLASSES[maxWidth];
    const isFullSize = expanded || maxWidth === 'full';

    return (
        <div
            className={`fixed inset-0 z-50 flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm ${isFullSize ? 'p-0' : ''}`}
            onClick={onClose}
        >
            <div
                className={
                    isFullSize
                        ? 'bg-mw-card shadow-2xl border border-mw-border w-full h-full max-h-[100dvh] flex flex-col overflow-hidden rounded-none'
                        : `bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full ${maxWidthClass} max-h-[90vh] flex flex-col overflow-hidden`
                }
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-4 border-b border-mw-border shrink-0">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                        {leadingSlot}
                        <h2 className="text-xl font-bold text-mw-text-primary truncate">{title}</h2>
                    </div>
                    <div className="flex items-center gap-1">
                        {enableFullscreen && maxWidth !== 'full' && (
                            <button
                                type="button"
                                onClick={() => setExpanded(e => !e)}
                                aria-label={expanded ? 'Exit full screen' : 'Full screen'}
                                className="p-2 text-mw-text-secondary hover:text-mw-text-primary rounded-full hover:bg-mw-card-alt transition-colors"
                            >
                                {expanded ? <Minimize2 size={20} /> : <Maximize2 size={20} />}
                            </button>
                        )}
                        <button
                            onClick={onClose}
                            aria-label="Close"
                            className="p-2 text-mw-text-secondary hover:text-mw-text-primary rounded-full hover:bg-mw-card-alt transition-colors"
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>

                <div className="flex-1 min-h-0 overflow-hidden flex flex-col">{children}</div>
            </div>
        </div>
    );
};
