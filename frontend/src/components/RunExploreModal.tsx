import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, History, Loader2, Play, Trash2 } from 'lucide-react';
import { ApiClient } from '../api/client';
import type { DocumentListItem, MyWorkflowRunSummary, NodeRunResult, Palette, Structure, WorkflowDefinition, WorkflowDefinitionListItem } from '../api/types';
import { useAuth } from '../contexts/AuthContext';
import { resolveWorkflowTimeZone } from '../domain/gmailRfc3339Date';
import { ManagerModal } from './ManagerModal';
import { nodeRunLogsToLastRunMap } from './workflow-editor/nodeRunLogsToLastRunMap';
import { WorkflowRunReplayView } from './workflow-editor/WorkflowRunReplayView';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

function formatRunTime(iso: string): string {
    try {
        const d = new Date(iso);
        return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
        return iso;
    }
}

function toggleIdInSet(prev: Set<string>, id: string): Set<string> {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
}

const RunExploreModalImpl: React.FC<Props> = ({ isOpen, onClose }) => {
    const { user } = useAuth();
    const [runs, setRuns] = useState<MyWorkflowRunSummary[]>([]);
    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [palettes, setPalettes] = useState<Palette[]>([]);
    const [structures, setStructures] = useState<Structure[]>([]);
    const [documents, setDocuments] = useState<DocumentListItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
    const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(() => new Set());
    const [bulkDeleteConfirming, setBulkDeleteConfirming] = useState(false);
    const selectAllRef = useRef<HTMLInputElement>(null);
    const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDefinition | null>(null);
    const [lastRunMap, setLastRunMap] = useState<Record<string, NodeRunResult>>({});
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
    const [outputOverrides, setOutputOverrides] = useState<Record<string, unknown>>({});
    const [rerunBusy, setRerunBusy] = useState(false);
    const loadList = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [r, w, p, s, d] = await Promise.all([
                ApiClient.getMyWorkflowRuns(),
                ApiClient.getWorkflows(),
                ApiClient.getPalettes(),
                ApiClient.getStructures().catch(() => [] as Structure[]),
                ApiClient.getDocuments().catch(() => [] as DocumentListItem[]),
            ]);
            setRuns(r);
            setWorkflows(w);
            setPalettes(p);
            setStructures(s);
            setDocuments(d);
        } catch {
            setError('Failed to load runs.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!isOpen) return;
        setSelectedRunId(null);
        setSelectedRunIds(new Set());
        setBulkDeleteConfirming(false);
        setSelectedWorkflow(null);
        setLastRunMap({});
        setDetailError(null);
        setDeletingRunId(null);
        setOutputOverrides({});
        void loadList();
    }, [isOpen, loadList]);

    const selectRun = useCallback(
        async (row: MyWorkflowRunSummary) => {
            setSelectedRunId(row.id);
            setDetailLoading(true);
            setDetailError(null);
            setLastRunMap({});
            setSelectedWorkflow(null);
            try {
                const [wf, logs] = await Promise.all([
                    ApiClient.getWorkflow(row.workflow_id),
                    ApiClient.getWorkflowRunLogs(row.workflow_id, row.id),
                ]);
                setSelectedWorkflow(wf);
                setLastRunMap(nodeRunLogsToLastRunMap(logs));
            } catch {
                setDetailError('Could not load this run.');
            } finally {
                setDetailLoading(false);
            }
        },
        [],
    );

    const handleRowContentClick = useCallback(
        (row: MyWorkflowRunSummary, e: React.MouseEvent) => {
            if (e.metaKey || e.ctrlKey) {
                setSelectedRunIds(prev => toggleIdInSet(prev, row.id));
                setDeletingRunId(null);
                setBulkDeleteConfirming(false);
                void selectRun(row);
                return;
            }
            setSelectedRunIds(new Set([row.id]));
            setDeletingRunId(null);
            setBulkDeleteConfirming(false);
            void selectRun(row);
        },
        [selectRun],
    );

    const handleCheckboxChange = useCallback(
        (row: MyWorkflowRunSummary, checked: boolean) => {
            setDeletingRunId(null);
            setBulkDeleteConfirming(false);

            const nextSel = new Set(selectedRunIds);
            if (checked) nextSel.add(row.id);
            else nextSel.delete(row.id);
            setSelectedRunIds(nextSel);

            if (checked) {
                void selectRun(row);
                return;
            }

            if (selectedRunId === row.id) {
                const remaining = runs.filter(x => nextSel.has(x.id));
                const first = remaining[0];
                if (first) void selectRun(first);
                else {
                    setSelectedRunId(null);
                    setSelectedWorkflow(null);
                    setLastRunMap({});
                    setDetailError(null);
                }
            }
        },
        [runs, selectedRunId, selectedRunIds, selectRun],
    );

    const handleSelectAllLoadedChange = useCallback((checked: boolean) => {
        setDeletingRunId(null);
        setBulkDeleteConfirming(false);
        if (checked) {
            setSelectedRunIds(new Set(runs.map(r => r.id)));
        } else {
            setSelectedRunIds(new Set());
            setSelectedRunId(null);
            setSelectedWorkflow(null);
            setLastRunMap({});
            setDetailError(null);
        }
    }, [runs]);

    const handleDelete = useCallback(
        async (row: MyWorkflowRunSummary) => {
            try {
                await ApiClient.deleteWorkflowRun(row.workflow_id, row.id);
                setDeletingRunId(null);
                setSelectedRunIds(prev => {
                    const next = new Set(prev);
                    next.delete(row.id);
                    return next;
                });
                if (selectedRunId === row.id) {
                    setSelectedRunId(null);
                    setSelectedWorkflow(null);
                    setLastRunMap({});
                }
                await loadList();
            } catch {
                setError('Failed to delete run.');
            }
        },
        [loadList, selectedRunId],
    );

    const handleBulkDelete = useCallback(async () => {
        const ids = [...selectedRunIds];
        setError(null);
        const failures: string[] = [];
        for (const id of ids) {
            const row = runs.find(r => r.id === id);
            if (!row) continue;
            try {
                await ApiClient.deleteWorkflowRun(row.workflow_id, row.id);
            } catch {
                failures.push(id);
            }
        }
        setBulkDeleteConfirming(false);
        setDeletingRunId(null);
        setSelectedRunIds(new Set());
        if (selectedRunId !== null && ids.includes(selectedRunId)) {
            setSelectedRunId(null);
            setSelectedWorkflow(null);
            setLastRunMap({});
        }
        await loadList();
        if (failures.length > 0) {
            setError(`Failed to delete ${failures.length} run(s).`);
        }
    }, [loadList, runs, selectedRunId, selectedRunIds]);

    const handleRerun = useCallback(async () => {
        if (!selectedWorkflow) return;
        setRerunBusy(true);
        setDetailError(null);
        setLastRunMap({});
        try {
            await ApiClient.runWorkflowStream(
                selectedWorkflow.id,
                event => {
                    if (event.event === 'node_end') {
                        const nodeResult = event.result as NodeRunResult;
                        setLastRunMap(prev => {
                            const cur = prev[nodeResult.node_id];
                            const sn = nodeResult.step_number ?? 0;
                            const prevSn = cur?.step_number ?? 0;
                            if (!cur || sn >= prevSn) {
                                return { ...prev, [nodeResult.node_id]: nodeResult };
                            }
                            return prev;
                        });
                    }
                },
                {
                    ...(Object.keys(outputOverrides).length > 0 ? { output_overrides: outputOverrides } : {}),
                    execution_time_zone: resolveWorkflowTimeZone(user?.settings as Record<string, unknown> | undefined),
                },
            );
        } catch {
            setDetailError('Re-run failed.');
        } finally {
            setRerunBusy(false);
        }
    }, [selectedWorkflow, outputOverrides, user?.settings]);

    const multiSelect = selectedRunIds.size > 1;
    const showRowTrash = !multiSelect;
    const showSelectAllHeader = runs.length >= 2 && !loading && !error;
    const allLoadedSelected = showSelectAllHeader && runs.every(r => selectedRunIds.has(r.id));
    const someLoadedSelected = runs.some(r => selectedRunIds.has(r.id));

    useEffect(() => {
        const el = selectAllRef.current;
        if (!el || !showSelectAllHeader) return;
        el.indeterminate = someLoadedSelected && !allLoadedSelected;
    }, [allLoadedSelected, showSelectAllHeader, someLoadedSelected]);

    if (!isOpen) return null;

    return (
        <ManagerModal
            isOpen={isOpen}
            onClose={onClose}
            title="Replays"
            maxWidth="full"
            leadingSlot={
                <button
                    type="button"
                    onClick={onClose}
                    aria-label="Back"
                    className="flex items-center gap-0.5 text-sm font-medium text-mw-text-secondary hover:text-mw-text-primary py-1 pl-0 pr-1 -ml-1 rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                >
                    <ChevronLeft size={20} className="shrink-0" />
                    <span>Back</span>
                </button>
            }
        >
            <div className="flex flex-1 min-h-0 overflow-hidden flex-col lg:flex-row">
                <div className="w-full max-h-[min(40vh,20rem)] lg:max-h-none lg:w-[min(320px,35vw)] border-b lg:border-b-0 lg:border-r border-mw-border bg-mw-sidebar flex flex-col shrink-0 min-h-0">
                    <div className="p-3 border-b border-mw-border flex flex-wrap items-center gap-x-2 gap-y-1">
                        <History size={16} className="text-mw-text-secondary shrink-0" />
                        <span className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">Your runs</span>
                        {showSelectAllHeader && (
                            <label className="ml-auto flex items-center gap-2 cursor-pointer shrink-0">
                                <input
                                    ref={selectAllRef}
                                    type="checkbox"
                                    checked={allLoadedSelected}
                                    onChange={e => handleSelectAllLoadedChange(e.target.checked)}
                                    onClick={e => e.stopPropagation()}
                                    className="rounded border-mw-border text-mw-primary shrink-0"
                                    aria-label="Select all runs in this list"
                                />
                                <span className="text-[11px] text-mw-text-secondary font-medium normal-case tracking-normal">
                                    All loaded
                                </span>
                            </label>
                        )}
                    </div>
                    {multiSelect && (
                        <div className="px-3 py-2 border-b border-mw-border bg-mw-card-alt/80 space-y-2">
                            <div className="text-sm font-medium text-mw-text-primary">
                                {selectedRunIds.size} selected
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
                                        Delete {selectedRunIds.size} runs? This cannot be undone.
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
                        {loading && (
                            <div className="flex items-center justify-center gap-2 text-sm text-mw-text-secondary py-8">
                                <Loader2 size={16} className="animate-spin" /> Loading…
                            </div>
                        )}
                        {error && <div className="text-sm text-red-500 px-2 py-4 text-center">{error}</div>}
                        {!loading && !error && runs.length === 0 && (
                            <p className="text-sm text-mw-text-secondary text-center px-2 py-6">No saved runs yet. Run a workflow from the editor.</p>
                        )}
                        {!loading &&
                            runs.map(row => {
                                const isFocused = selectedRunId === row.id;
                                const isSelected = selectedRunIds.has(row.id);
                                const rowSurface =
                                    isFocused
                                        ? 'bg-mw-primary-muted border-mw-primary'
                                        : isSelected && multiSelect
                                          ? 'bg-mw-card-alt border-mw-border'
                                          : 'border-transparent hover:bg-mw-card border-mw-border';
                                const timeLabel = formatRunTime(row.created_at);
                                return (
                                    <div
                                        key={row.id}
                                        className={`group flex items-start gap-2 rounded-lg border p-2.5 transition-colors text-left w-full ${rowSurface}`}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={isSelected}
                                            onChange={e => handleCheckboxChange(row, e.target.checked)}
                                            onClick={e => e.stopPropagation()}
                                            className="rounded border-mw-border text-mw-primary shrink-0 mt-0.5"
                                            aria-label={`Select ${row.workflow_name} at ${timeLabel}`}
                                        />
                                        <div
                                            className="min-w-0 flex-1 flex items-start justify-between gap-2 cursor-pointer"
                                            role="button"
                                            tabIndex={0}
                                            onClick={e => handleRowContentClick(row, e)}
                                            onKeyDown={e => {
                                                if (e.key === 'Enter' || e.key === ' ') {
                                                    e.preventDefault();
                                                    const synthetic = {
                                                        metaKey: e.getModifierState('Meta'),
                                                        ctrlKey: e.getModifierState('Control'),
                                                    } as React.MouseEvent;
                                                    handleRowContentClick(row, synthetic);
                                                }
                                            }}
                                        >
                                            <div className="min-w-0 flex-1">
                                                <div className="text-sm font-medium text-mw-text-primary truncate">{row.workflow_name}</div>
                                                <div className="text-[11px] text-mw-text-secondary mt-0.5">{timeLabel}</div>
                                                <div className="mt-1">
                                                    <span
                                                        className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${
                                                            row.status === 'ok'
                                                                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                                                                : row.status === 'partial'
                                                                  ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                                                                  : row.status === 'running'
                                                                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700'
                                                                    : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                                                        }`}
                                                    >
                                                        {row.status}
                                                    </span>
                                                </div>
                                            </div>
                                            {showRowTrash && (
                                                <div
                                                    className={`flex gap-1 shrink-0 ${deletingRunId === row.id ? 'opacity-100' : 'opacity-70 group-hover:opacity-100'}`}
                                                    onClick={e => e.stopPropagation()}
                                                >
                                                    {deletingRunId !== row.id && (
                                                        <button
                                                            type="button"
                                                            title="Delete run"
                                                            onClick={e => {
                                                                e.stopPropagation();
                                                                setDeletingRunId(row.id);
                                                            }}
                                                            className="p-1.5 text-mw-text-secondary hover:text-red-500 rounded"
                                                        >
                                                            <Trash2 size={14} />
                                                        </button>
                                                    )}
                                                    {deletingRunId === row.id && (
                                                        <div className="flex gap-1">
                                                            <button
                                                                type="button"
                                                                onClick={() => void handleDelete(row)}
                                                                className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium"
                                                            >
                                                                Delete
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => setDeletingRunId(null)}
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
                <div className="flex-1 min-w-0 min-h-0 flex flex-col bg-mw-page">
                    {detailLoading && (
                        <div className="flex-1 flex items-center justify-center gap-2 text-mw-text-secondary">
                            <Loader2 size={20} className="animate-spin" /> Loading run…
                        </div>
                    )}
                    {detailError && !detailLoading && (
                        <div className="flex-1 flex items-center justify-center text-red-500 text-sm px-6 text-center">{detailError}</div>
                    )}
                    {!detailLoading && !detailError && selectedWorkflow && (
                        <>
                            <div className="shrink-0 flex flex-wrap items-center gap-2 px-3 py-2 border-b border-mw-border bg-mw-card">
                                <button
                                    type="button"
                                    onClick={() => void handleRerun()}
                                    disabled={rerunBusy}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-mw-success hover:opacity-90 disabled:opacity-50 rounded-lg"
                                >
                                    {rerunBusy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                                    {rerunBusy ? 'Running…' : 'Re-run'}
                                </button>
                                {Object.keys(outputOverrides).length > 0 && (
                                    <button
                                        type="button"
                                        onClick={() => setOutputOverrides({})}
                                        className="text-xs font-medium px-2 py-1.5 rounded-lg border border-mw-border text-mw-text-secondary hover:bg-mw-card-alt"
                                    >
                                        Clear overrides
                                    </button>
                                )}
                            </div>
                            <WorkflowRunReplayView
                                workflow={selectedWorkflow}
                                runId={selectedRunId}
                                allWorkflows={workflows}
                                palettes={palettes}
                                structures={structures}
                                documents={documents}
                                lastRunNodeData={lastRunMap}
                                outputOverrides={outputOverrides}
                                onOutputOverridesChange={setOutputOverrides}
                            />
                        </>
                    )}
                    {!detailLoading && !detailError && !selectedWorkflow && selectedRunId === null && (
                        <div className="flex-1 flex items-center justify-center text-mw-text-secondary text-sm px-6 text-center">
                            Select a run to inspect inputs and outputs on the graph.
                        </div>
                    )}
                </div>
            </div>
        </ManagerModal>
    );
};

export const RunExploreModal = RunExploreModalImpl;
export default RunExploreModalImpl;
