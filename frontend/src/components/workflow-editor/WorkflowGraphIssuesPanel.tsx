import type { WorkflowGraphWiringIssue } from './workflowGraphWiringIssues';
import { InspectorSection } from './InspectorSection';

export type WorkflowGraphIssuesPanelProps = {
    issues: WorkflowGraphWiringIssue[];
    visibleEdgeCount: number;
    hiddenEdgeCount: number;
    onFocusNode: (nodeId: string) => void;
    onDeleteEdge: (edgeId: string) => void;
};

export function WorkflowGraphIssuesPanel({
    issues,
    visibleEdgeCount,
    hiddenEdgeCount,
    onFocusNode,
    onDeleteEdge,
}: WorkflowGraphIssuesPanelProps) {
    if (issues.length === 0) return null;

    return (
        <InspectorSection
            title="Graph issues"
            description={
                hiddenEdgeCount > 0
                    ? `${issues.length} graph wiring issue${issues.length === 1 ? '' : 's'} — broken connections are hidden from the canvas. Review and fix below; Save and Run still work. ${visibleEdgeCount} edge${visibleEdgeCount === 1 ? '' : 's'} on canvas · ${hiddenEdgeCount} hidden (broken wiring).`
                    : `${issues.length} wiring issue${issues.length === 1 ? '' : 's'} on this graph.`
            }
        >
            <ul className="space-y-3">
                {issues.map(issue => (
                    <li
                        key={issue.edgeId}
                        className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs text-mw-text-primary"
                    >
                        <p className="leading-relaxed">{issue.message}</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                            <button
                                type="button"
                                className="rounded-md border border-mw-border bg-mw-card px-2 py-1 text-[11px] font-medium hover:bg-mw-card-alt"
                                onClick={() => onFocusNode(issue.sourceNodeId)}
                            >
                                Focus source
                            </button>
                            <button
                                type="button"
                                className="rounded-md border border-mw-border bg-mw-card px-2 py-1 text-[11px] font-medium hover:bg-mw-card-alt"
                                onClick={() => onFocusNode(issue.targetNodeId)}
                            >
                                Focus target
                            </button>
                            <button
                                type="button"
                                className="rounded-md border border-red-300/60 bg-red-50 px-2 py-1 text-[11px] font-medium text-red-800 hover:bg-red-100 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-950/60"
                                onClick={() => onDeleteEdge(issue.edgeId)}
                            >
                                Delete connection
                            </button>
                        </div>
                    </li>
                ))}
            </ul>
        </InspectorSection>
    );
}
