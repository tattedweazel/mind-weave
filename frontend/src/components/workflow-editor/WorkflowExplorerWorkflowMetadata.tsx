import { Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import type {
    WorkflowDefinition,
    WorkflowExecutionLimitsEnvelope,
    WorkflowExecutionLimitsOverrides,
} from '../../api/types';
import { useCopyWithFeedback } from '../../contexts/ClipboardFeedbackContext';
import { InspectorSection } from './InspectorSection';

export interface WorkflowExplorerWorkflowMetadataProps {
    workflow: WorkflowDefinition;
    nodeCount: number;
    edgeCount: number;
    lastRunId: string | null;
    /** When set, shows Expose / Remove actions; persisted via API. */
    onExposeAsCustomSkillChange?: (value: boolean) => void;
    /** Server ceilings + defaults (optional). */
    executionLimitsEnvelope?: WorkflowExecutionLimitsEnvelope | null;
    /** Draft graph.execution_limits persisted on Save. Null/undefined clears. */
    graphExecutionLimitsDraft?: WorkflowExecutionLimitsOverrides | null;
    /** Per-run overrides for the next streamed run only (sent in POST …/runs body). */
    runExecutionLimitsDraft?: WorkflowExecutionLimitsOverrides | null;
    /** Merge or replace workflow graph.execution_limits draft (persisted via Save). */
    onGraphExecutionLimitsChange?: (next: WorkflowExecutionLimitsOverrides | null) => void;
    /** Merge per-run overrides (omit empty object to clear). */
    onRunExecutionLimitsChange?: (next: WorkflowExecutionLimitsOverrides) => void;
}

function CopyIdRow({
    label,
    value,
    copyAnnouncement,
}: {
    label: string;
    value: string;
    copyAnnouncement: string;
}) {
    const copy = useCopyWithFeedback();
    return (
        <div>
            <div className="text-xs font-medium text-mw-text-secondary mb-1">{label}</div>
            <div className="flex items-start gap-2 min-w-0">
                <code className="flex-1 min-w-0 text-[11px] font-mono text-mw-text-primary bg-mw-card rounded px-2 py-1.5 break-all border border-mw-border/60">
                    {value}
                </code>
                <button
                    type="button"
                    onClick={() => void copy(value)}
                    className="shrink-0 mt-0.5 p-1.5 rounded-md text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card-alt border border-transparent hover:border-mw-border transition-colors"
                    aria-label={`Copy ${copyAnnouncement}`}
                >
                    <Copy size={14} aria-hidden />
                </button>
            </div>
        </div>
    );
}

function parsePositiveLimit(raw: string): number | undefined {
    const n = Number(String(raw).trim());
    if (!Number.isFinite(n)) return undefined;
    return Math.max(1, Math.floor(n));
}

function WorkflowExecutionLimitsForm({
    ceilings,
    defaults,
    graphDraft,
    runDraft,
    onGraphChange,
    onRunChange,
}: {
    ceilings: WorkflowExecutionLimitsEnvelope['ceilings'] | null | undefined;
    defaults: WorkflowExecutionLimitsEnvelope['defaults'] | null | undefined;
    graphDraft: WorkflowExecutionLimitsOverrides | null | undefined;
    runDraft: WorkflowExecutionLimitsOverrides | null | undefined;
    onGraphChange?: (next: WorkflowExecutionLimitsOverrides | null) => void;
    onRunChange?: (next: WorkflowExecutionLimitsOverrides) => void;
}) {
    const [ttlG, setTtlG] = useState('');
    const [nodeG, setNodeG] = useState('');
    const [loopG, setLoopG] = useState('');
    const [depthG, setDepthG] = useState('');
    const [ttlR, setTtlR] = useState('');
    const [nodeR, setNodeR] = useState('');
    const [loopR, setLoopR] = useState('');
    const [depthR, setDepthR] = useState('');

    useEffect(() => {
        const d = graphDraft;
        setTtlG(d?.workflow_ttl_seconds != null ? String(d.workflow_ttl_seconds) : '');
        setNodeG(d?.max_node_executions != null ? String(d.max_node_executions) : '');
        setLoopG(d?.max_loop_iterations != null ? String(d.max_loop_iterations) : '');
        setDepthG(d?.max_nested_depth != null ? String(d.max_nested_depth) : '');
    }, [
        graphDraft?.workflow_ttl_seconds,
        graphDraft?.max_node_executions,
        graphDraft?.max_loop_iterations,
        graphDraft?.max_nested_depth,
    ]);

    useEffect(() => {
        const d = runDraft;
        setTtlR(d?.workflow_ttl_seconds != null ? String(d.workflow_ttl_seconds) : '');
        setNodeR(d?.max_node_executions != null ? String(d.max_node_executions) : '');
        setLoopR(d?.max_loop_iterations != null ? String(d.max_loop_iterations) : '');
        setDepthR(d?.max_nested_depth != null ? String(d.max_nested_depth) : '');
    }, [
        runDraft?.workflow_ttl_seconds,
        runDraft?.max_node_executions,
        runDraft?.max_loop_iterations,
        runDraft?.max_nested_depth,
    ]);

    if (!onGraphChange && !onRunChange) return null;

    const ceilLine =
        ceilings != null ?
            (
                `Server max: TTL ${ceilings.workflow_ttl_seconds}s · node exec ${ceilings.max_node_executions} · loops ${ceilings.max_loop_iterations} · nested depth ${ceilings.max_nested_depth}`
            )
        :   'Ceilings loading… refine values after save if limits fail validation.';

    const defHint =
        defaults != null ?
            (
                <>
                    Deploy defaults — TTL{' '}
                    <span className="font-medium text-mw-text-primary">{defaults.workflow_ttl_seconds}s</span>, node{' '}
                    <span className="font-medium text-mw-text-primary">{defaults.max_node_executions}</span>, loops{' '}
                    <span className="font-medium text-mw-text-primary">{defaults.max_loop_iterations}</span>, depth{' '}
                    <span className="font-medium text-mw-text-primary">{defaults.max_nested_depth}</span>.
                </>
            )
        :   null;

    const mergeGraphLimits = (): WorkflowExecutionLimitsOverrides | null => {
        const draft = { ...(graphDraft ?? {}) } as WorkflowExecutionLimitsOverrides;
        const t = parsePositiveLimit(ttlG);
        const n = parsePositiveLimit(nodeG);
        const l = parsePositiveLimit(loopG);
        const d = parsePositiveLimit(depthG);
        if (t !== undefined && ceilings) draft.workflow_ttl_seconds = Math.min(t, ceilings.workflow_ttl_seconds);
        else if (t !== undefined) draft.workflow_ttl_seconds = t;
        else delete draft.workflow_ttl_seconds;
        if (n !== undefined && ceilings) draft.max_node_executions = Math.min(n, ceilings.max_node_executions);
        else if (n !== undefined) draft.max_node_executions = n;
        else delete draft.max_node_executions;
        if (l !== undefined && ceilings) draft.max_loop_iterations = Math.min(l, ceilings.max_loop_iterations);
        else if (l !== undefined) draft.max_loop_iterations = l;
        else delete draft.max_loop_iterations;
        if (d !== undefined && ceilings) draft.max_nested_depth = Math.min(d, ceilings.max_nested_depth);
        else if (d !== undefined) draft.max_nested_depth = d;
        else delete draft.max_nested_depth;
        return Object.keys(draft).length > 0 ? draft : null;
    };

    const mergeRunLimits = (): WorkflowExecutionLimitsOverrides => {
        const draft = { ...(runDraft ?? {}) } as WorkflowExecutionLimitsOverrides;
        const t = parsePositiveLimit(ttlR);
        const n = parsePositiveLimit(nodeR);
        const l = parsePositiveLimit(loopR);
        const d = parsePositiveLimit(depthR);
        if (t !== undefined && ceilings) draft.workflow_ttl_seconds = Math.min(t, ceilings.workflow_ttl_seconds);
        else if (t !== undefined) draft.workflow_ttl_seconds = t;
        else delete draft.workflow_ttl_seconds;
        if (n !== undefined && ceilings) draft.max_node_executions = Math.min(n, ceilings.max_node_executions);
        else if (n !== undefined) draft.max_node_executions = n;
        else delete draft.max_node_executions;
        if (l !== undefined && ceilings) draft.max_loop_iterations = Math.min(l, ceilings.max_loop_iterations);
        else if (l !== undefined) draft.max_loop_iterations = l;
        else delete draft.max_loop_iterations;
        if (d !== undefined && ceilings) draft.max_nested_depth = Math.min(d, ceilings.max_nested_depth);
        else if (d !== undefined) draft.max_nested_depth = d;
        else delete draft.max_nested_depth;
        return draft;
    };

    return (
        <>
            {onGraphChange ?
                <InspectorSection
                    title="Execution caps (workflow)"
                    description="Saved with this workflow JSON. Overrides must stay at or below the server ceilings; empty fields fall back to deployment defaults."
                >
                    <p className="text-[10px] text-mw-text-secondary leading-snug">{ceilLine}</p>
                    {defHint ?
                        <p className="text-[10px] text-mw-text-secondary leading-snug">{defHint}</p>
                    :   null}
                    <div className="grid grid-cols-1 gap-2">
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">workflow_ttl_seconds</label>
                            <input
                                value={ttlG}
                                onChange={e => setTtlG(e.target.value)}
                                onBlur={() => void onGraphChange(mergeGraphLimits())}
                                type="number"
                                min={1}
                                aria-label="Graph override workflow TTL seconds"
                                placeholder="deployment default"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_node_executions
                            </label>
                            <input
                                value={nodeG}
                                onChange={e => setNodeG(e.target.value)}
                                onBlur={() => void onGraphChange(mergeGraphLimits())}
                                type="number"
                                min={1}
                                aria-label="Graph override max node executions"
                                placeholder="deployment default"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_loop_iterations
                            </label>
                            <input
                                value={loopG}
                                onChange={e => setLoopG(e.target.value)}
                                onBlur={() => void onGraphChange(mergeGraphLimits())}
                                type="number"
                                min={1}
                                aria-label="Graph override max loop iterations"
                                placeholder="deployment default"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_nested_depth
                            </label>
                            <input
                                value={depthG}
                                onChange={e => setDepthG(e.target.value)}
                                onBlur={() => void onGraphChange(mergeGraphLimits())}
                                type="number"
                                min={1}
                                aria-label="Graph override max nested depth"
                                placeholder="deployment default"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                    </div>
                    <button
                        type="button"
                        className="w-full mt-2 px-3 py-1.5 text-[11px] font-medium rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-card"
                        onClick={() => {
                            setTtlG('');
                            setNodeG('');
                            setLoopG('');
                            setDepthG('');
                            onGraphChange(null);
                        }}
                    >
                        Clear workflow overrides
                    </button>
                </InspectorSection>
            :   null}
            {onRunChange ?
                <InspectorSection
                    title="Execution caps (this run)"
                    description="Optional per-run overlays only; merges over graph overrides for this run. Clear with the button below when you want server defaults plus any saved workflow caps."
                >
                    <p className="text-[10px] text-mw-text-secondary leading-snug">{ceilLine}</p>
                    <div className="grid grid-cols-1 gap-2">
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">workflow_ttl_seconds</label>
                            <input
                                value={ttlR}
                                onChange={e => setTtlR(e.target.value)}
                                onBlur={() => onRunChange(mergeRunLimits())}
                                type="number"
                                min={1}
                                aria-label="Run overlay workflow TTL seconds"
                                placeholder="no overlay"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_node_executions
                            </label>
                            <input
                                value={nodeR}
                                onChange={e => setNodeR(e.target.value)}
                                onBlur={() => onRunChange(mergeRunLimits())}
                                type="number"
                                min={1}
                                aria-label="Run overlay max node executions"
                                placeholder="no overlay"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_loop_iterations
                            </label>
                            <input
                                value={loopR}
                                onChange={e => setLoopR(e.target.value)}
                                onBlur={() => onRunChange(mergeRunLimits())}
                                type="number"
                                min={1}
                                aria-label="Run overlay max loop iterations"
                                placeholder="no overlay"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-mw-text-secondary block mb-1">
                                max_nested_depth
                            </label>
                            <input
                                value={depthR}
                                onChange={e => setDepthR(e.target.value)}
                                onBlur={() => onRunChange(mergeRunLimits())}
                                type="number"
                                min={1}
                                aria-label="Run overlay max nested depth"
                                placeholder="no overlay"
                                className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg"
                            />
                        </div>
                    </div>
                    <button
                        type="button"
                        className="w-full mt-2 px-3 py-1.5 text-[11px] font-medium rounded-lg border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-card"
                        onClick={() => {
                            setTtlR('');
                            setNodeR('');
                            setLoopR('');
                            setDepthR('');
                            onRunChange({});
                        }}
                    >
                        Clear run overlays
                    </button>
                </InspectorSection>
            :   null}
        </>
    );
}
/**
 * Shown in the Explorer tab when no node or edge is selected: identifiers and counts
 * for support / DB queries (e.g. paste workflow definition UUID into SQL or chat).
 */
export function WorkflowExplorerWorkflowMetadata({
    workflow,
    nodeCount,
    edgeCount,
    lastRunId,
    onExposeAsCustomSkillChange,
    executionLimitsEnvelope,
    graphExecutionLimitsDraft,
    runExecutionLimitsDraft,
    onGraphExecutionLimitsChange,
    onRunExecutionLimitsChange,
}: WorkflowExplorerWorkflowMetadataProps) {
    const copy = useCopyWithFeedback();
    const schemaVersion = workflow.graph?.schema_version;
    const exposed = Boolean(workflow.expose_as_custom_skill);
    const debugBundle = JSON.stringify(
        {
            workflow_definition_id: workflow.id,
            name: workflow.name,
            ...(workflow.user_id ? { user_id: workflow.user_id } : {}),
            ...(lastRunId ? { last_run_id: lastRunId } : {}),
        },
        null,
        0,
    );

    return (
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden text-sm">
            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
                <InspectorSection
                    title="Workflow"
                    description="Use these identifiers when debugging, sharing with support, or querying the database. Copy the definition ID or the full JSON line."
                >
                    <div>
                        <div className="text-xs font-medium text-mw-text-secondary mb-1">Name</div>
                        <div className="text-sm text-mw-text-primary font-medium break-words">{workflow.name}</div>
                    </div>
                    {workflow.description ? (
                        <p className="text-[11px] text-mw-text-secondary leading-snug">{workflow.description}</p>
                    ) : null}
                    <CopyIdRow
                        label="Workflow definition ID"
                        value={workflow.id}
                        copyAnnouncement="workflow definition id"
                    />
                    {workflow.user_id ? (
                        <CopyIdRow label="Owner user ID" value={workflow.user_id} copyAnnouncement="owner user id" />
                    ) : null}
                    {lastRunId ? (
                        <CopyIdRow label="Last run ID (this session)" value={lastRunId} copyAnnouncement="last run id" />
                    ) : null}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-mw-text-secondary">
                        <span>
                            Graph: <strong className="text-mw-text-primary font-medium">{nodeCount}</strong> nodes,{' '}
                            <strong className="text-mw-text-primary font-medium">{edgeCount}</strong> edges
                        </span>
                        {schemaVersion != null ? (
                            <span>
                                Schema v<strong className="text-mw-text-primary font-medium">{String(schemaVersion)}</strong>
                            </span>
                        ) : (
                            <span>Schema v1 (implicit)</span>
                        )}
                    </div>
                    <div>
                        <div className="text-xs font-medium text-mw-text-secondary mb-1">Copy debug JSON</div>
                        <div className="flex items-start gap-2 min-w-0">
                            <code className="flex-1 min-w-0 text-[10px] leading-snug font-mono text-mw-text-primary bg-mw-card rounded px-2 py-1.5 break-all border border-mw-border/60">
                                {debugBundle}
                            </code>
                            <button
                                type="button"
                                onClick={() => void copy(debugBundle)}
                                className="shrink-0 mt-0.5 p-1.5 rounded-md text-mw-text-secondary hover:text-mw-primary hover:bg-mw-card-alt border border-transparent hover:border-mw-border transition-colors"
                                aria-label="Copy debug JSON"
                            >
                                <Copy size={14} aria-hidden />
                            </button>
                        </div>
                    </div>
                </InspectorSection>
                <WorkflowExecutionLimitsForm
                    ceilings={executionLimitsEnvelope?.ceilings}
                    defaults={executionLimitsEnvelope?.defaults}
                    graphDraft={graphExecutionLimitsDraft ?? null}
                    runDraft={runExecutionLimitsDraft ?? null}
                    onGraphChange={onGraphExecutionLimitsChange}
                    onRunChange={onRunExecutionLimitsChange}
                />
            </div>
            {onExposeAsCustomSkillChange ? (
                <div className="shrink-0 border-t border-mw-border bg-mw-card/90 dark:bg-mw-page/80 px-4 py-3 space-y-2">
                    <p className="text-[11px] text-mw-text-secondary leading-snug">
                        Listed under Custom Skills in the palette for reuse as a nested workflow (same as dragging from the workflow list).
                    </p>
                    {!exposed ? (
                        <button
                            type="button"
                            onClick={() => void onExposeAsCustomSkillChange(true)}
                            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-amber-500/70 bg-amber-500/15 text-amber-950 dark:text-amber-100 hover:bg-amber-500/25 focus:outline-none focus:ring-2 focus:ring-amber-500/50 transition-colors"
                        >
                            Expose as Custom Skill
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={() => void onExposeAsCustomSkillChange(false)}
                            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-card-alt focus:outline-none focus:ring-2 focus:ring-mw-primary/40 transition-colors"
                        >
                            Remove from Custom Skills
                        </button>
                    )}
                </div>
            ) : null}
            <p className="shrink-0 text-center text-xs text-mw-text-secondary italic px-4 pb-4 pt-2">
                Select a node or connection on the canvas to configure it.
            </p>
        </div>
    );
}
