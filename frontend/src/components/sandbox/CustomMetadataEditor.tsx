import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

export type CustomMetadataRow = {
    id: string;
    key: string;
    valueText: string;
};

export function metadataToRows(metadata: Record<string, unknown>): CustomMetadataRow[] {
    return Object.entries(metadata).map(([key, value]) => ({
        id: `${key}-${JSON.stringify(value)}`,
        key,
        valueText: JSON.stringify(value),
    }));
}

export function rowsToMetadata(rows: CustomMetadataRow[]): { metadata: Record<string, unknown>; error: string | null } {
    const out: Record<string, unknown> = {};
    for (const row of rows) {
        const key = row.key.trim();
        if (!key) continue;
        if (Object.prototype.hasOwnProperty.call(out, key)) {
            return { metadata: {}, error: `Duplicate key "${key}"` };
        }
        const raw = row.valueText.trim();
        if (!raw) {
            return { metadata: {}, error: `Value required for key "${key}"` };
        }
        try {
            out[key] = JSON.parse(raw);
        } catch {
            return { metadata: {}, error: `Invalid JSON value for key "${key}"` };
        }
    }
    return { metadata: out, error: null };
}

export interface CustomMetadataEditorProps {
    value: Record<string, unknown>;
    onChange: (metadata: Record<string, unknown>) => void;
    disabled?: boolean;
}

const MANAGER_LABEL_CLS = 'text-xs font-medium text-mw-text-secondary block mb-1';

export const CustomMetadataEditor: React.FC<CustomMetadataEditorProps> = ({
    value,
    onChange,
    disabled = false,
}) => {
    const [rows, setRows] = useState<CustomMetadataRow[]>(() => metadataToRows(value));
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setRows(metadataToRows(value));
        setError(null);
    }, [value]);

    const commitRows = useCallback(
        (nextRows: CustomMetadataRow[]) => {
            setRows(nextRows);
            const { metadata, error: parseError } = rowsToMetadata(nextRows);
            setError(parseError);
            if (!parseError) {
                onChange(metadata);
            }
        },
        [onChange],
    );

    const addRow = () => {
        commitRows([...rows, { id: crypto.randomUUID(), key: '', valueText: '' }]);
    };

    const removeRow = (id: string) => {
        commitRows(rows.filter(r => r.id !== id));
    };

    const updateRow = (id: string, patch: Partial<Pick<CustomMetadataRow, 'key' | 'valueText'>>) => {
        commitRows(rows.map(r => (r.id === id ? { ...r, ...patch } : r)));
    };

    const hint = useMemo(
        () => 'Values are JSON (e.g. 25, "text", ["a","b"]). Metadata is opaque — workflows read keys explicitly.',
        [],
    );

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
                <span className={MANAGER_LABEL_CLS}>Custom metadata</span>
                {!disabled ? (
                    <button
                        type="button"
                        onClick={addRow}
                        className="inline-flex items-center gap-1 text-xs text-mw-primary hover:underline"
                    >
                        <Plus size={14} />
                        Add entry
                    </button>
                ) : null}
            </div>
            <p className="text-[11px] text-mw-text-secondary">{hint}</p>
            {rows.length === 0 ? (
                <p className="text-xs text-mw-text-secondary italic">No metadata entries.</p>
            ) : (
                <ul className="space-y-2">
                    {rows.map(row => (
                        <li key={row.id} className="flex gap-2 items-start">
                            <input
                                value={row.key}
                                disabled={disabled}
                                onChange={e => updateRow(row.id, { key: e.target.value })}
                                placeholder="key"
                                className="w-28 shrink-0 px-2 py-1.5 text-sm border border-mw-border bg-mw-card rounded-lg font-mono"
                            />
                            <textarea
                                value={row.valueText}
                                disabled={disabled}
                                onChange={e => updateRow(row.id, { valueText: e.target.value })}
                                placeholder='JSON value'
                                rows={2}
                                className="flex-1 min-w-0 px-2 py-1.5 text-sm border border-mw-border bg-mw-card rounded-lg font-mono resize-y"
                            />
                            {!disabled ? (
                                <button
                                    type="button"
                                    aria-label="Remove entry"
                                    onClick={() => removeRow(row.id)}
                                    className="shrink-0 p-1.5 text-mw-text-secondary hover:text-red-600"
                                >
                                    <Trash2 size={16} />
                                </button>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
            {error ? <p className="text-xs text-red-600">{error}</p> : null}
        </div>
    );
};

export function validateCustomMetadata(metadata: Record<string, unknown>): string | null {
    const { error } = rowsToMetadata(metadataToRows(metadata));
    return error;
}
