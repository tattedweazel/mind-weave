import { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';

export interface OutputOverrideModalProps {
    isOpen: boolean;
    onClose: () => void;
    nodeLabel: string;
    /** Initial JSON-serializable value (or undefined for empty). */
    initialValue: unknown;
    onSave: (value: unknown) => void;
}

export function OutputOverrideModal({ isOpen, onClose, nodeLabel, initialValue, onSave }: OutputOverrideModalProps) {
    const [text, setText] = useState('{}');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!isOpen) return;
        setError(null);
        try {
            if (initialValue === undefined) {
                setText('{}');
            } else {
                setText(JSON.stringify(initialValue, null, 2));
            }
        } catch {
            setText(String(initialValue));
        }
    }, [isOpen, initialValue]);

    const handleClose = useCallback(() => {
        setError(null);
        onClose();
    }, [onClose]);

    const handleSave = useCallback(() => {
        setError(null);
        const trimmed = text.trim();
        if (trimmed === '') {
            setError('Enter JSON for the forced output.');
            return;
        }
        try {
            const parsed = JSON.parse(trimmed) as unknown;
            onSave(parsed);
            handleClose();
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Invalid JSON');
        }
    }, [text, onSave, handleClose]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50" role="dialog" aria-modal="true">
            <div className="bg-mw-card border border-mw-border rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] flex flex-col">
                <div className="flex items-center justify-between px-4 py-3 border-b border-mw-border">
                    <h2 className="text-sm font-semibold text-mw-text-primary">Override output</h2>
                    <button
                        type="button"
                        onClick={handleClose}
                        className="p-1 rounded-lg text-mw-text-secondary hover:bg-mw-card-alt"
                        aria-label="Close"
                    >
                        <X size={18} />
                    </button>
                </div>
                <div className="px-4 py-3 space-y-2 flex-1 min-h-0 flex flex-col">
                    <p className="text-xs text-mw-text-secondary">
                        Node <span className="font-medium text-mw-text-primary">{nodeLabel}</span> — provide a JSON value
                        matching this step&apos;s output shape. The server validates before run.
                    </p>
                    <textarea
                        value={text}
                        onChange={e => setText(e.target.value)}
                        className="flex-1 min-h-[200px] w-full text-xs font-mono bg-mw-page border border-mw-border rounded-lg p-2 text-mw-text-primary"
                        spellCheck={false}
                    />
                    {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
                </div>
                <div className="flex justify-end gap-2 px-4 py-3 border-t border-mw-border">
                    <button
                        type="button"
                        onClick={handleClose}
                        className="px-3 py-1.5 text-xs font-medium rounded-lg border border-mw-border text-mw-text-secondary hover:bg-mw-card-alt"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={handleSave}
                        className="px-3 py-1.5 text-xs font-medium rounded-lg bg-mw-primary text-white hover:opacity-90"
                    >
                        Apply override
                    </button>
                </div>
            </div>
        </div>
    );
}
