import React, { createContext, useContext, useMemo, useState } from 'react';
import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { MermaidBlock } from './MermaidBlock';

export type MarkdownViewMode = 'raw' | 'preview' | 'metadata';

const CodeInsidePreContext = createContext(false);

/**
 * Optional third tab. When provided, renders a "Metadata" button alongside
 * Raw/Preview and shows ``content`` in the body area when active. Owners of the
 * slot decide what to render (e.g. token count, timestamps, an unsaved hint).
 */
export interface MarkdownMetadataSlot {
    content: React.ReactNode;
    /** Show a small loading indicator next to the content while true. */
    isLoading?: boolean;
}

interface MarkdownRawPreviewProps {
    value: string;
    onChange?: (next: string) => void;
    /** Number of rows for the raw textarea when editable. */
    rows?: number;
    /** When false, raw field is read-only (preview-only flows). */
    editable?: boolean;
    /** Optional id for labeling. */
    id?: string;
    className?: string;
    /**
     * Opt in to a third "Metadata" tab. When omitted the component renders
     * only Raw / Preview, preserving existing call sites.
     */
    metadataSlot?: MarkdownMetadataSlot;
    /**
     * Notified whenever the user switches tabs. Useful for owners that want
     * to lazily fetch metadata only when the tab is first viewed.
     */
    onModeChange?: (mode: MarkdownViewMode) => void;
}

const previewProseClass =
    'prose prose-sm dark:prose-invert max-w-none ' +
    'prose-headings:text-mw-text-primary ' +
    'prose-a:text-mw-primary prose-a:no-underline hover:prose-a:underline ' +
    'prose-strong:text-mw-text-primary prose-code:text-mw-text-primary ' +
    'prose-li:marker:text-mw-text-secondary';

function MarkdownPre({ children }: { children?: React.ReactNode }) {
    const child = React.Children.only(children);
    if (React.isValidElement(child) && child.type === 'code') {
        const p = child.props as { className?: string; children?: React.ReactNode };
        if (typeof p.className === 'string' && p.className.includes('language-mermaid')) {
            const src = String(p.children ?? '').replace(/\n$/, '');
            return <MermaidBlock source={src} />;
        }
    }
    return (
        <CodeInsidePreContext.Provider value={true}>
            <pre className="mb-4 overflow-x-auto rounded-lg border border-mw-border bg-mw-card-alt p-3 text-sm not-prose">
                {children}
            </pre>
        </CodeInsidePreContext.Provider>
    );
}

function MarkdownCode(
    props: React.ComponentPropsWithoutRef<'code'> & { node?: unknown },
) {
    const { children, className, node: _node, ...rest } = props;
    const inPre = useContext(CodeInsidePreContext);
    if (inPre) {
        return (
            <code className={className} {...rest}>
                {children}
            </code>
        );
    }
    return (
        <code
            className="rounded bg-mw-primary-muted/70 px-1.5 py-0.5 font-mono text-[0.875em] text-mw-text-primary"
            {...rest}
        >
            {children}
        </code>
    );
}

const markdownComponents: Components = {
    pre: MarkdownPre,
    code: MarkdownCode,
};

/**
 * Shared Raw / Preview toggle for text fields (Document manager, explorers, run logs).
 * Raw shows exact bytes; Preview runs the Markdown pipeline (best when content is Markdown).
 */
export const MarkdownRawPreview: React.FC<MarkdownRawPreviewProps> = ({
    value,
    onChange,
    rows = 14,
    editable = true,
    id,
    className = '',
    metadataSlot,
    onModeChange,
}) => {
    const [mode, setMode] = useState<MarkdownViewMode>('raw');

    const switchMode = (next: MarkdownViewMode) => {
        if (next === mode) return;
        setMode(next);
        onModeChange?.(next);
    };

    const tabCls = (active: boolean) =>
        `px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            active
                ? 'bg-mw-primary-muted text-mw-primary'
                : 'text-mw-text-secondary hover:bg-mw-card-alt'
        }`;

    const remarkPlugins = useMemo(() => [remarkGfm, remarkMath], []);
    const rehypePlugins = useMemo(() => [rehypeKatex], []);

    return (
        <div className={`space-y-2 ${className}`}>
            <div className="flex gap-1">
                <button type="button" className={tabCls(mode === 'raw')} onClick={() => switchMode('raw')}>
                    Raw
                </button>
                <button
                    type="button"
                    className={tabCls(mode === 'preview')}
                    onClick={() => switchMode('preview')}
                >
                    Preview
                </button>
                {metadataSlot && (
                    <button
                        type="button"
                        className={tabCls(mode === 'metadata')}
                        onClick={() => switchMode('metadata')}
                    >
                        Metadata
                    </button>
                )}
            </div>
            {mode === 'raw' && (
                <textarea
                    id={id}
                    value={value}
                    onChange={e => onChange?.(e.target.value)}
                    readOnly={!editable || !onChange}
                    rows={rows}
                    className="w-full rounded-lg border border-mw-border bg-mw-sidebar px-3 py-2 text-sm text-mw-text-primary font-mono resize-y min-h-[120px] focus:outline-none focus:ring-2 focus:ring-mw-primary/40"
                    spellCheck={false}
                />
            )}
            {mode === 'preview' && (
                <div
                    className={`${previewProseClass} rounded-lg border border-mw-border bg-mw-sidebar px-3 py-3 text-mw-text-primary min-h-[120px] overflow-auto [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-visible`}
                    data-testid="markdown-preview"
                >
                    <ReactMarkdown
                        remarkPlugins={remarkPlugins}
                        rehypePlugins={rehypePlugins}
                        components={markdownComponents}
                    >
                        {value || '*Nothing to preview*'}
                    </ReactMarkdown>
                </div>
            )}
            {mode === 'metadata' && metadataSlot && (
                <div
                    className="rounded-lg border border-mw-border bg-mw-sidebar px-3 py-3 text-sm text-mw-text-primary min-h-[120px] overflow-auto"
                    data-testid="markdown-metadata"
                >
                    {metadataSlot.isLoading ? (
                        <div
                            className="text-xs text-mw-text-secondary"
                            aria-live="polite"
                        >
                            Loading metadata…
                        </div>
                    ) : (
                        metadataSlot.content
                    )}
                </div>
            )}
        </div>
    );
};
