import React from 'react';

/** Shared shell for Explorer panel wells (use for custom layouts e.g. Last Run). */
export const INSPECTOR_SURFACE_CLASS =
    'rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 p-3 space-y-2';

export interface InspectorSectionProps {
    /** Short uppercase-style heading (Explorer panel) */
    title: string;
    /** Optional control next to the title (e.g. ContextHelpModal). */
    titleAside?: React.ReactNode;
    /** Optional muted intro under the title */
    description?: React.ReactNode;
    children?: React.ReactNode;
    className?: string;
}

/**
 * Consistent bordered group for the workflow Explorer (node inspector) right panel.
 */
export const InspectorSection: React.FC<InspectorSectionProps> = ({
    title,
    titleAside,
    description,
    children,
    className = '',
}) => (
    <section className={`${INSPECTOR_SURFACE_CLASS} ${className}`}>
        <div className="flex items-center gap-1">
            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary">{title}</h3>
            {titleAside}
        </div>
        {description != null && description !== '' ? (
            <div className="text-[11px] text-mw-text-secondary leading-snug">{description}</div>
        ) : null}
        {children != null && children !== false ? <div className="space-y-2">{children}</div> : null}
    </section>
);
