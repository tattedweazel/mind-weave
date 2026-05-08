/**
 * Human-oriented preview for explorer row payloads (contrast with JsonTreeView on **View raw**).
 */

export function safeJsonStringify(value: unknown, space: number): string {
    try {
        return JSON.stringify(value, null, space);
    } catch {
        return String(value);
    }
}

const preBoxClass =
    'text-xs font-mono bg-mw-card-alt border border-mw-border rounded-lg p-3 whitespace-pre-wrap break-words max-h-[min(50vh,28rem)] overflow-y-auto text-mw-text-primary leading-relaxed';

export function PrimitiveValuePreview({
    payload,
    typeHint,
}: {
    payload: unknown;
    /** e.g. inferred primitive / secondary line from the explorer row */
    typeHint?: string;
}) {
    const hint = typeHint?.trim();

    if (payload === undefined) {
        return <p className="text-xs text-mw-text-secondary italic">No value for this row.</p>;
    }
    if (payload === null) {
        return (
            <div className="space-y-2">
                {hint ? <TypeHint label={hint} /> : null}
                <p className="text-sm text-mw-text-secondary italic">null</p>
            </div>
        );
    }

    if (typeof payload === 'string') {
        const display = payload.trim() === '' ? '—' : payload;
        return (
            <div className="space-y-2">
                {hint ? <TypeHint label={hint} /> : null}
                <p className="text-[11px] text-mw-text-secondary">
                    Text value — <strong>View raw</strong> shows the same string in the JSON tree.
                </p>
                <div className="text-sm text-mw-text-primary whitespace-pre-wrap break-words border border-mw-border rounded-lg p-3 bg-mw-page/80 dark:bg-mw-card-alt/40 max-h-[min(50vh,28rem)] overflow-y-auto leading-relaxed">
                    {display}
                </div>
            </div>
        );
    }

    if (typeof payload === 'number' || typeof payload === 'boolean') {
        return (
            <div className="space-y-2">
                {hint ? <TypeHint label={hint} /> : null}
                <p className="text-[11px] text-mw-text-secondary">
                    Scalar — <strong>View raw</strong> uses the expandable JSON tree.
                </p>
                <div className="text-xl font-semibold text-mw-text-primary font-mono tabular-nums">{String(payload)}</div>
            </div>
        );
    }

    if (Array.isArray(payload)) {
        const json = safeJsonStringify(payload, 2);
        return (
            <div className="space-y-2">
                {hint ? <TypeHint label={hint} /> : null}
                <p className="text-[11px] text-mw-text-secondary">
                    {payload.length} element(s). <strong>Preview</strong> is pretty-printed JSON; <strong>View raw</strong> is the collapsible tree navigator.
                </p>
                <pre className={preBoxClass}>{json}</pre>
            </div>
        );
    }

    if (typeof payload === 'object') {
        const keys = Object.keys(payload as object);
        const json = safeJsonStringify(payload, 2);
        return (
            <div className="space-y-2">
                {hint ? <TypeHint label={hint} /> : null}
                <p className="text-[11px] text-mw-text-secondary">
                    Object with {keys.length} top-level key{keys.length === 1 ? '' : 's'}. <strong>Preview</strong> is pretty-printed JSON;{' '}
                    <strong>View raw</strong> is the collapsible tree.
                </p>
                <pre className={preBoxClass}>{json}</pre>
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {hint ? <TypeHint label={hint} /> : null}
            <pre className={preBoxClass}>{str(payload)}</pre>
        </div>
    );
}

function TypeHint({ label }: { label: string }) {
    return (
        <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary">
            Inferred type: <span className="text-mw-text-primary normal-case font-medium">{label}</span>
        </div>
    );
}

function str(v: unknown): string {
    if (v == null) return '';
    return String(v).trim() || '—';
}
