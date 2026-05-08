import React, { useCallback, useId, useState } from 'react';
import { FileUp, X } from 'lucide-react';
import type { WorkflowDefinitionCreate } from '../../api/types';
import {
    parseWorkflowImport,
    readWorkflowImportFile,
    WorkflowImportError,
} from '../../domain/workflowImportExport';

export interface WorkflowImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    /** Called with create payload; parent applies palette validation and API create. */
    onImport: (payload: WorkflowDefinitionCreate) => Promise<void>;
}

export function WorkflowImportModal({ isOpen, onClose, onImport }: WorkflowImportModalProps) {
    const [text, setText] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const fileInputId = useId();

    const reset = useCallback(() => {
        setText('');
        setError(null);
        setBusy(false);
    }, []);

    const handleClose = useCallback(() => {
        reset();
        onClose();
    }, [onClose, reset]);

    const handleFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        setError(null);
        try {
            const t = await readWorkflowImportFile(file);
            setText(t);
        } catch {
            setError('Could not read file.');
        }
    }, []);

    const handleSubmit = useCallback(async () => {
        setError(null);
        setBusy(true);
        try {
            const payload = parseWorkflowImport(text.trim() === '' ? '{}' : text);
            await onImport(payload);
            reset();
            onClose();
        } catch (e) {
            if (e instanceof WorkflowImportError && e.message === 'Import cancelled.') {
                setBusy(false);
                return;
            }
            setError(e instanceof WorkflowImportError ? e.message : e instanceof Error ? e.message : 'Import failed.');
        } finally {
            setBusy(false);
        }
    }, [text, onImport, onClose, reset]);

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workflow-import-title"
        >
            <div className="bg-mw-card border border-mw-border rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between px-4 py-3 border-b border-mw-border shrink-0">
                    <h2 id="workflow-import-title" className="text-sm font-semibold text-mw-text-primary">
                        Import workflow JSON
                    </h2>
                    <button
                        type="button"
                        onClick={handleClose}
                        className="p-1.5 rounded-lg text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-page"
                        aria-label="Close"
                    >
                        <X size={18} />
                    </button>
                </div>
                <div className="p-4 space-y-3 overflow-y-auto flex-1 min-h-0">
                    <p className="text-xs text-mw-text-secondary leading-relaxed">
                        Paste a workflow export JSON or choose a <code className="text-[11px]">.json</code> file. A{' '}
                        <strong>new</strong> workflow is created; nested <strong>Workflow</strong> node references may need
                        to be re-linked if IDs do not exist in this environment.
                    </p>
                    <div className="flex flex-wrap gap-2">
                        <label
                            htmlFor={fileInputId}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-mw-border rounded-lg cursor-pointer hover:bg-mw-page text-mw-text-primary"
                        >
                            <FileUp size={14} /> Choose file
                        </label>
                        <input id={fileInputId} type="file" accept=".json,application/json" className="sr-only" onChange={handleFile} />
                    </div>
                    <textarea
                        value={text}
                        onChange={e => setText(e.target.value)}
                        placeholder='{"kind":"mind_weave_workflow_export",...}'
                        rows={14}
                        className="w-full font-mono text-[11px] px-3 py-2 border border-mw-border bg-mw-page rounded-lg text-mw-text-primary resize-y min-h-[12rem]"
                        spellCheck={false}
                    />
                    {error ? (
                        <p className="text-xs text-red-600 dark:text-red-400" role="alert">
                            {error}
                        </p>
                    ) : null}
                </div>
                <div className="flex justify-end gap-2 px-4 py-3 border-t border-mw-border shrink-0">
                    <button
                        type="button"
                        onClick={handleClose}
                        className="px-3 py-1.5 text-xs font-medium text-mw-text-primary border border-mw-border rounded-lg hover:bg-mw-page"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleSubmit()}
                        disabled={busy || text.trim() === ''}
                        className="px-3 py-1.5 text-xs font-medium text-white bg-mw-primary hover:opacity-90 rounded-lg disabled:opacity-50"
                    >
                        {busy ? 'Importing…' : 'Import'}
                    </button>
                </div>
            </div>
        </div>
    );
}
