import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ApiClient } from '../api/client';
import { DocumentCreate, DocumentListItem, DocumentMetadata, DocumentUpdate } from '../api/types';
import { Edit2, FileText, Plus, Trash2 } from 'lucide-react';
import { ManagerModal } from './ManagerModal';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';
import { MarkdownRawPreview, type MarkdownMetadataSlot } from './MarkdownRawPreview';
import { DocumentMetadataPanel, DocumentMetadataPanelSkeleton } from './DocumentMetadataPanel';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

const EMPTY_FORM = { name: '', description: '', body: '' };

function toggleIdInSet(prev: Set<string>, id: string): Set<string> {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
}

export const DocumentManager: React.FC<Props> = ({ isOpen, onClose }) => {
    const [documents, setDocuments] = useState<DocumentListItem[]>([]);
    const [focusId, setFocusId] = useState<string | null>(null);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [bulkDeleteConfirming, setBulkDeleteConfirming] = useState(false);
    const [isCreating, setIsCreating] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [isLoadingBody, setIsLoadingBody] = useState(false);
    // Body is intentionally omitted from the list payload (`DocumentListItem`); fetch the full row
    // on focus and ignore stale responses if the user picks another row mid-flight.
    const focusTokenRef = useRef(0);

    // Metadata tab state. Lazy-loaded the first time the user opens the tab for a
    // saved document; cached per-id so re-clicking is free; invalidated on save.
    const [metadata, setMetadata] = useState<DocumentMetadata | null>(null);
    const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);
    const [metadataError, setMetadataError] = useState<string | null>(null);
    const metadataTokenRef = useRef(0);
    const metadataFetchedForIdRef = useRef<string | null>(null);

    const hydrateFocusBody = async (id: string) => {
        const myToken = ++focusTokenRef.current;
        setIsLoadingBody(true);
        try {
            const full = await ApiClient.getDocument(id);
            if (focusTokenRef.current !== myToken) return;
            setForm(f => ({ ...f, body: full.body ?? '' }));
        } catch {
            if (focusTokenRef.current !== myToken) return;
        } finally {
            if (focusTokenRef.current === myToken) {
                setIsLoadingBody(false);
            }
        }
    };

    const resetMetadataState = () => {
        metadataTokenRef.current += 1;
        metadataFetchedForIdRef.current = null;
        setMetadata(null);
        setIsLoadingMetadata(false);
        setMetadataError(null);
    };

    const loadMetadata = async (id: string) => {
        if (metadataFetchedForIdRef.current === id) return;
        metadataFetchedForIdRef.current = id;
        const myToken = ++metadataTokenRef.current;
        setIsLoadingMetadata(true);
        setMetadataError(null);
        try {
            const m = await ApiClient.getDocumentMetadata(id);
            if (metadataTokenRef.current !== myToken) return;
            setMetadata(m);
        } catch {
            if (metadataTokenRef.current !== myToken) return;
            metadataFetchedForIdRef.current = null;
            setMetadataError('Failed to load metadata.');
        } finally {
            if (metadataTokenRef.current === myToken) {
                setIsLoadingMetadata(false);
            }
        }
    };

    const load = async () => {
        setIsLoading(true);
        try {
            const res = await ApiClient.getDocuments();
            setDocuments(res);
        } catch {
            setError('Failed to load documents.');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            load();
            setForm(EMPTY_FORM);
            setIsCreating(false);
            setFocusId(null);
            setSelectedIds(new Set());
            setDeletingId(null);
            setBulkDeleteConfirming(false);
            setError(null);
            setIsLoadingBody(false);
            focusTokenRef.current += 1;
            resetMetadataState();
        }
    }, [isOpen]);

    const metadataSlot: MarkdownMetadataSlot = useMemo(() => {
        if (!focusId || isCreating) {
            return {
                content: (
                    <div className="text-sm text-mw-text-secondary">
                        Save the document to see token count and other metadata.
                    </div>
                ),
            };
        }
        if (metadataError) {
            return {
                content: (
                    <div className="text-sm text-mw-error">{metadataError}</div>
                ),
            };
        }
        if (!metadata) {
            // Pulsing skeleton mirrors the eventual panel layout; gives an
            // immediate visual cue that the fetch is in flight rather than
            // appearing to hang on a static "Loading…" line.
            return { content: <DocumentMetadataPanelSkeleton /> };
        }
        return { content: <DocumentMetadataPanel metadata={metadata} />, isLoading: isLoadingMetadata };
    }, [focusId, isCreating, metadata, metadataError, isLoadingMetadata]);

    if (!isOpen) return null;

    const field = (key: keyof typeof EMPTY_FORM, v: string) => setForm(f => ({ ...f, [key]: v }));

    const applyFocusDoc = (d: DocumentListItem) => {
        setIsCreating(false);
        setFocusId(d.id);
        setForm({ name: d.name, description: d.description ?? '', body: '' });
        resetMetadataState();
        void hydrateFocusBody(d.id);
    };

    const handleRowContentClick = (d: DocumentListItem, e: React.MouseEvent) => {
        if (e.metaKey || e.ctrlKey) {
            setSelectedIds(prev => toggleIdInSet(prev, d.id));
            applyFocusDoc(d);
            setDeletingId(null);
            setBulkDeleteConfirming(false);
            return;
        }
        setSelectedIds(new Set([d.id]));
        applyFocusDoc(d);
        setDeletingId(null);
        setBulkDeleteConfirming(false);
    };

    const handleCheckboxChange = (d: DocumentListItem, checked: boolean) => {
        setDeletingId(null);
        setBulkDeleteConfirming(false);
        setIsCreating(false);

        const nextSel = new Set(selectedIds);
        if (checked) nextSel.add(d.id);
        else nextSel.delete(d.id);
        setSelectedIds(nextSel);

        if (checked) {
            setFocusId(d.id);
            setForm({ name: d.name, description: d.description ?? '', body: '' });
            resetMetadataState();
            void hydrateFocusBody(d.id);
            return;
        }

        if (focusId === d.id) {
            const remaining = documents.filter(x => nextSel.has(x.id));
            const first = remaining[0];
            if (first) {
                setFocusId(first.id);
                setForm({ name: first.name, description: first.description ?? '', body: '' });
                resetMetadataState();
                void hydrateFocusBody(first.id);
            } else {
                setFocusId(null);
                setForm(EMPTY_FORM);
                setIsLoadingBody(false);
                focusTokenRef.current += 1;
                resetMetadataState();
            }
        }
    };

    const handleSave = async () => {
        if (!form.name.trim()) {
            setError('Name is required.');
            return;
        }
        setError(null);
        try {
            if (isCreating) {
                const crt: DocumentCreate = {
                    name: form.name,
                    description: form.description || undefined,
                    body: form.body,
                };
                await ApiClient.createDocument(crt);
            } else if (focusId) {
                const upd: DocumentUpdate = {
                    name: form.name,
                    description: form.description || undefined,
                    body: form.body,
                };
                await ApiClient.updateDocument(focusId, upd);
            }
            await load();
            setFocusId(null);
            setIsCreating(false);
            setSelectedIds(new Set());
            setForm(EMPTY_FORM);
            setIsLoadingBody(false);
            focusTokenRef.current += 1;
            resetMetadataState();
        } catch (e: unknown) {
            const err = e as { message?: string };
            setError(err.message ?? 'Failed to save.');
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await ApiClient.deleteDocument(id);
            setDeletingId(null);
            setIsCreating(false);
            setSelectedIds(prev => {
                const next = new Set(prev);
                next.delete(id);
                return next;
            });
            if (focusId === id) {
                setFocusId(null);
                setForm(EMPTY_FORM);
                setIsLoadingBody(false);
                focusTokenRef.current += 1;
                resetMetadataState();
            }
            await load();
        } catch {
            setError('Failed to delete document.');
        }
    };

    const handleBulkDelete = async () => {
        const ids = [...selectedIds];
        setError(null);
        const failures: string[] = [];
        for (const id of ids) {
            try {
                await ApiClient.deleteDocument(id);
            } catch {
                failures.push(id);
            }
        }
        setBulkDeleteConfirming(false);
        setDeletingId(null);
        setSelectedIds(new Set());
        setFocusId(null);
        setIsCreating(false);
        setForm(EMPTY_FORM);
        setIsLoadingBody(false);
        focusTokenRef.current += 1;
        resetMetadataState();
        await load();
        if (failures.length > 0) {
            setError(`Failed to delete ${failures.length} document(s).`);
        }
    };

    const inputCls = MANAGER_INPUT_CLS;
    const labelCls = MANAGER_LABEL_CLS;
    const multiSelect = selectedIds.size > 1;
    const showRowTrash = !multiSelect;

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Manage Documents" maxWidth="4xl">
            <div className="flex flex-1 overflow-hidden">
                <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                    <div className="p-3 border-b border-mw-border">
                        <button
                            type="button"
                            onClick={() => {
                                setIsCreating(true);
                                setFocusId(null);
                                setSelectedIds(new Set());
                                setForm(EMPTY_FORM);
                                setDeletingId(null);
                                setBulkDeleteConfirming(false);
                                setError(null);
                            }}
                            className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={15} /> New Document
                        </button>
                    </div>
                    {multiSelect && (
                        <div className="px-3 py-2 border-b border-mw-border bg-mw-card-alt/80 space-y-2">
                            <div className="text-sm font-medium text-mw-text-primary">
                                {selectedIds.size} selected
                            </div>
                            {!bulkDeleteConfirming ? (
                                <button
                                    type="button"
                                    onClick={() => setBulkDeleteConfirming(true)}
                                    className="w-full py-1.5 text-sm font-medium rounded-lg bg-red-500/15 text-red-600 dark:text-red-400 hover:bg-red-500/25 transition-colors"
                                >
                                    Delete selected
                                </button>
                            ) : (
                                <div className="space-y-2">
                                    <p className="text-xs text-mw-text-secondary">
                                        Delete {selectedIds.size} documents? This cannot be undone.
                                    </p>
                                    <div className="flex gap-2">
                                        <button
                                            type="button"
                                            onClick={() => setBulkDeleteConfirming(false)}
                                            className="flex-1 py-1.5 text-xs font-medium rounded-lg bg-mw-card text-mw-text-primary border border-mw-border hover:opacity-90"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => void handleBulkDelete()}
                                            className="flex-1 py-1.5 text-xs font-medium rounded-lg bg-red-500 text-white hover:bg-red-600"
                                        >
                                            Delete all
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {isLoading && (
                            <div className="text-sm text-center text-mw-text-secondary p-4">Loading…</div>
                        )}
                        {documents.map(d => {
                            const isFocused = focusId === d.id;
                            const isSelected = selectedIds.has(d.id);
                            const rowSurface =
                                isFocused
                                    ? 'bg-mw-primary-muted border border-mw-primary'
                                    : isSelected && multiSelect ? 'bg-mw-card-alt border border-mw-border'
                                      : 'hover:bg-mw-card border border-transparent';
                            return (
                                <div
                                    key={d.id}
                                    className={`group flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${rowSurface}`}
                                >
                                    <input
                                        type="checkbox"
                                        checked={isSelected}
                                        onChange={e => handleCheckboxChange(d, e.target.checked)}
                                        onClick={e => e.stopPropagation()}
                                        className="rounded border-mw-border text-mw-primary shrink-0"
                                        aria-label={`Select ${d.name}`}
                                    />
                                    <div
                                        className="flex-1 min-w-0 flex items-center justify-between gap-2"
                                        onClick={e => handleRowContentClick(d, e)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                const synthetic = {
                                                    metaKey: e.getModifierState('Meta'),
                                                    ctrlKey: e.getModifierState('Control'),
                                                } as React.MouseEvent;
                                                handleRowContentClick(d, synthetic);
                                            }
                                        }}
                                        role="button"
                                        tabIndex={0}
                                    >
                                        <div className="truncate pr-2 min-w-0">
                                            <div className="text-sm font-medium text-mw-text-primary truncate">
                                                {d.name}
                                            </div>
                                            <div className="text-xs text-mw-text-secondary truncate">
                                                {d.description || 'Markdown for workflows and prompts'}
                                            </div>
                                        </div>
                                        {showRowTrash && (
                                            <div
                                                className={`flex gap-1 shrink-0 ${
                                                    deletingId === d.id
                                                        ? 'opacity-100'
                                                        : 'opacity-0 group-hover:opacity-100'
                                                }`}
                                            >
                                                {deletingId !== d.id && (
                                                    <button
                                                        type="button"
                                                        onClick={e => {
                                                            e.stopPropagation();
                                                            setDeletingId(d.id);
                                                        }}
                                                        className="p-1 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                                                        title="Delete"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                )}
                                                {deletingId === d.id && (
                                                    <div
                                                        className="flex gap-1"
                                                        onClick={e => e.stopPropagation()}
                                                    >
                                                        <button
                                                            type="button"
                                                            onClick={() => void handleDelete(d.id)}
                                                            className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium"
                                                        >
                                                            Delete
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => setDeletingId(null)}
                                                            className="px-2 py-0.5 text-xs bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                    {isCreating || focusId ? (
                        <div className="space-y-4 max-w-3xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2 flex items-center gap-2">
                                <FileText size={18} />
                                {isCreating ? 'Create Document' : 'Edit Document'}
                            </h3>
                            {error && (
                                <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg">
                                    {error}
                                </div>
                            )}

                            <div>
                                <label className={labelCls}>Name *</label>
                                <input
                                    value={form.name}
                                    onChange={e => field('name', e.target.value)}
                                    className={inputCls}
                                    placeholder="e.g. Workflow authoring guide"
                                />
                            </div>
                            <div>
                                <label className={labelCls}>Description</label>
                                <input
                                    value={form.description}
                                    onChange={e => field('description', e.target.value)}
                                    className={inputCls}
                                    placeholder="Short summary"
                                />
                            </div>
                            <div>
                                <label className={labelCls}>
                                    Body
                                    {isLoadingBody && (
                                        <span
                                            className="ml-2 text-xs text-mw-text-secondary"
                                            aria-live="polite"
                                        >
                                            Loading body…
                                        </span>
                                    )}
                                </label>
                                <MarkdownRawPreview
                                    // Remount per-document so switching focus resets the inner
                                    // tab state to the default ("Raw") instead of stranding the
                                    // user on a tab that was meaningful for the previous doc.
                                    key={focusId ?? 'creating'}
                                    value={form.body}
                                    onChange={v => field('body', v)}
                                    rows={16}
                                    metadataSlot={metadataSlot}
                                    onModeChange={mode => {
                                        if (mode === 'metadata' && focusId && !isCreating) {
                                            void loadMetadata(focusId);
                                        }
                                    }}
                                />
                            </div>

                            <div className="pt-2 flex justify-end gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsCreating(false);
                                        setFocusId(null);
                                        setSelectedIds(new Set());
                                        setError(null);
                                        setForm(EMPTY_FORM);
                                        setIsLoadingBody(false);
                                        focusTokenRef.current += 1;
                                        resetMetadataState();
                                    }}
                                    className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => void handleSave()}
                                    className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors"
                                >
                                    Save Document
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary">
                            <Edit2 size={48} className="mb-4 text-mw-text-secondary opacity-50" />
                            <p>Select a document or create a new one.</p>
                            <p className="text-xs mt-2">
                                Documents store text for workflows (Markdown, JSON, or other); use Raw / Preview /
                                Metadata when editing.
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </ManagerModal>
    );
};
