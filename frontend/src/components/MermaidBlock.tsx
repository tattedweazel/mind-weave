import React, { useEffect, useId, useRef, useState } from 'react';
import { useTheme } from '../contexts/ThemeContext';

interface MermaidBlockProps {
    source: string;
}

/**
 * Renders a fenced ```mermaid block by dynamically loading mermaid and calling render().
 * Theme follows app dark mode; failures show the source for debugging.
 */
export const MermaidBlock: React.FC<MermaidBlockProps> = ({ source }) => {
    const { isDarkMode } = useTheme();
    const containerRef = useRef<HTMLDivElement>(null);
    const [error, setError] = useState<string | null>(null);
    const baseId = useId().replace(/:/g, '');

    useEffect(() => {
        let cancelled = false;
        const container = containerRef.current;
        if (!container) return;

        const trimmed = source.trim();
        if (!trimmed) {
            container.innerHTML = '';
            setError(null);
            return;
        }

        setError(null);
        container.innerHTML = '';

        import('mermaid')
            .then((mod) => {
                const mermaid = mod.default;
                mermaid.initialize({
                    startOnLoad: false,
                    theme: isDarkMode ? 'dark' : 'default',
                    securityLevel: 'strict',
                });
                const renderId = `m-${baseId}-${Math.random().toString(36).slice(2, 11)}`;
                return mermaid.render(renderId, trimmed);
            })
            .then((result) => {
                if (cancelled || !containerRef.current) return;
                containerRef.current.innerHTML = result.svg;
            })
            .catch((e: unknown) => {
                if (!cancelled) {
                    const msg = e instanceof Error ? e.message : String(e);
                    setError(msg || 'Mermaid render failed');
                }
            });

        return () => {
            cancelled = true;
        };
    }, [source, isDarkMode, baseId]);

    if (error) {
        return (
            <div className="my-4 rounded-md border border-mw-error/40 bg-mw-error-muted/30 p-3 text-xs text-mw-error not-prose">
                <div className="font-medium">Mermaid</div>
                <p className="mt-1 text-mw-text-secondary">{error}</p>
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded border border-mw-border bg-mw-sidebar p-2 font-mono text-[11px] text-mw-text-primary">
                    {source}
                </pre>
            </div>
        );
    }

    return (
        <div
            className="my-4 overflow-x-auto not-prose [&_svg]:max-w-none"
            ref={containerRef}
            data-testid="mermaid-block"
        />
    );
};
