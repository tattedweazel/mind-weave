import { Copy } from 'lucide-react';

import type { WorkflowDefinition } from '../../api/types';
import { useCopyWithFeedback } from '../../contexts/ClipboardFeedbackContext';
import { InspectorSection } from './InspectorSection';

export interface WorkflowExplorerWorkflowMetadataProps {
    workflow: WorkflowDefinition;
    nodeCount: number;
    edgeCount: number;
    lastRunId: string | null;
    /** When set, shows Expose / Remove actions; persisted via API. */
    onExposeAsCustomSkillChange?: (value: boolean) => void;
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
