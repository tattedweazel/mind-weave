import { useEffect, useRef, useState } from 'react';

function formatTtsOptions(obj: unknown): string {
    if (obj != null && typeof obj === 'object' && !Array.isArray(obj)) {
        return JSON.stringify(obj, null, 2);
    }
    return '{}';
}

function normJsonString(raw: string): string | null {
    const t = raw.trim();
    if (t === '') return '{}';
    try {
        return JSON.stringify(JSON.parse(t));
    } catch {
        return null;
    }
}

function normProp(ttsOptions: unknown): string {
    return JSON.stringify(
        ttsOptions != null && typeof ttsOptions === 'object' && !Array.isArray(ttsOptions) ? ttsOptions : {},
    );
}

export type TtsBridgeOptionsTextareaProps = {
    ttsOptions: unknown;
    onFocus: () => void;
    onCommit: (opts: Record<string, unknown>) => void;
};

/**
 * Free-form JSON for TTS bridge options. Keeps a local draft while typing so invalid
 * intermediate JSON does not snap the control back to the last parsed value.
 * Parent should set `key={node.id}` so the draft resets when switching nodes.
 */
export function TtsBridgeOptionsTextarea({ ttsOptions, onFocus, onCommit }: TtsBridgeOptionsTextareaProps) {
    const [draft, setDraft] = useState(() => formatTtsOptions(ttsOptions));
    const lastPropNorm = useRef(normProp(ttsOptions));

    useEffect(() => {
        const nextNorm = normProp(ttsOptions);
        if (nextNorm === lastPropNorm.current) return;
        lastPropNorm.current = nextNorm;
        setDraft(prev => {
            const curNorm = normJsonString(prev);
            if (curNorm !== null && curNorm === nextNorm) return prev;
            return formatTtsOptions(JSON.parse(nextNorm));
        });
    }, [ttsOptions]);

    return (
        <>
            <textarea
                value={draft}
                spellCheck={false}
                onFocus={onFocus}
                onChange={e => {
                    const next = e.target.value;
                    setDraft(next);
                    const raw = next.trim();
                    if (raw === '') {
                        lastPropNorm.current = '{}';
                        onCommit({});
                        return;
                    }
                    try {
                        const parsed = JSON.parse(raw) as unknown;
                        if (parsed != null && typeof parsed === 'object' && !Array.isArray(parsed)) {
                            lastPropNorm.current = JSON.stringify(parsed);
                            onCommit(parsed as Record<string, unknown>);
                        }
                    } catch {
                        /* invalid JSON — keep draft only */
                    }
                }}
                onBlur={() => {
                    const raw = draft.trim();
                    if (raw === '') return;
                    try {
                        const parsed = JSON.parse(raw) as unknown;
                        if (parsed != null && typeof parsed === 'object' && !Array.isArray(parsed)) {
                            const pretty = JSON.stringify(parsed, null, 2);
                            setDraft(pretty);
                            lastPropNorm.current = JSON.stringify(parsed);
                            onCommit(parsed as Record<string, unknown>);
                        }
                    } catch {
                        /* leave draft as-is so user can fix */
                    }
                }}
                rows={6}
                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
            />
            <p className="text-[10px] text-mw-text-secondary mt-1">
                Opaque per-engine options; interpreted only by the TTS bridge.
            </p>
        </>
    );
}
