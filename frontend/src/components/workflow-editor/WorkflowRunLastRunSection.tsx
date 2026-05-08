/**
 * Recorded node execution (outputs, inputs, diagnostics) — shared by the editor “Last Run”
 * and Explore past runs (read-only).
 */
import { CheckCircle2, ChevronRight, XCircle } from 'lucide-react';
import type { NodeRunResult } from '../../api/types';
import { INSPECTOR_SURFACE_CLASS } from './InspectorSection';
import { JsonTreeView } from './JsonTreeView';
import { lastRunInputsPayload } from './lastRunInputsPayload';
import { RunInputsExplorer } from './RunInputsExplorer';
import { WorkflowNodeRunOutputBody } from './WorkflowNodeRunOutputBody';

export interface WorkflowRunLastRunSectionProps {
    nodeLog: NodeRunResult | undefined;
    userSettings?: Record<string, unknown>;
}

export function WorkflowRunLastRunSection({ nodeLog, userSettings }: WorkflowRunLastRunSectionProps) {
    if (!nodeLog) {
        return (
            <div className={`${INSPECTOR_SURFACE_CLASS} mt-1`}>
                <p className="text-xs text-mw-text-secondary italic">No recorded data for this node.</p>
            </div>
        );
    }

    const inputsPayload = lastRunInputsPayload(nodeLog.details as Record<string, unknown> | undefined);
    const showInputsFirst =
        !!inputsPayload && (nodeLog.status !== 'ok' || (nodeLog.error != null && nodeLog.error !== ''));
    const inputsPanel = inputsPayload ? (
        <div className="mt-2">
            <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1">Inputs</div>
            <RunInputsExplorer payload={inputsPayload} />
        </div>
    ) : null;

    return (
        <div className={`${INSPECTOR_SURFACE_CLASS} mt-1`}>
            <div className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide mb-2">Recorded run</div>
            <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                    {nodeLog.status === 'ok' ? (
                        <CheckCircle2 size={12} className="text-emerald-500" />
                    ) : (
                        <XCircle size={12} className="text-red-500" />
                    )}
                    <span
                        className={`text-xs font-medium ${
                            nodeLog.status === 'ok'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'
                        }`}
                    >
                        {nodeLog.status === 'ok' ? 'Completed' : 'Failed'}
                        {nodeLog.latency_ms != null && ` · ${nodeLog.latency_ms.toFixed(0)}ms`}
                    </span>
                    {nodeLog.details?.forced_output ? (
                        <span className="text-[10px] font-semibold uppercase text-amber-700 dark:text-amber-300 ml-1">
                            Overridden
                        </span>
                    ) : null}
                </div>
                {nodeLog.error && (
                    <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded p-2 font-mono break-all">
                        {nodeLog.error}
                    </div>
                )}
                {showInputsFirst && inputsPanel}
                {nodeLog.details?.sub_workflow_node_results && (
                    <div className="mt-2">
                        <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1.5">
                            Sub-workflow: {nodeLog.details.sub_workflow_name ?? 'Sub-workflow'}
                        </div>
                        <div className="space-y-1.5">
                            {(nodeLog.details.sub_workflow_node_results as any[]).map((sr: any) => {
                                const stepLabel =
                                    (nodeLog.details?.sub_workflow_node_labels as Record<string, string>)?.[sr.node_id] ??
                                    sr.node_id;
                                return (
                                    <div
                                        key={sr.node_id}
                                        className="flex items-start gap-2 text-xs bg-mw-card-alt rounded p-2 border border-mw-border"
                                    >
                                        {sr.status === 'ok' ? (
                                            <CheckCircle2 size={12} className="text-emerald-500 shrink-0 mt-0.5" />
                                        ) : (
                                            <XCircle size={12} className="text-red-500 shrink-0 mt-0.5" />
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <span className="font-medium text-mw-text-primary">{stepLabel}</span>
                                            {sr.latency_ms != null && (
                                                <span className="text-mw-text-secondary ml-1">{sr.latency_ms.toFixed(0)}ms</span>
                                            )}
                                            {sr.error && (
                                                <div className="text-red-600 dark:text-red-400 mt-1 text-[11px] whitespace-pre-wrap break-all">
                                                    {sr.error}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
                {nodeLog.output && (
                    <div>
                        <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide mb-1">
                            Output
                        </div>
                        <WorkflowNodeRunOutputBody
                            nodeId={nodeLog.node_id}
                            output={nodeLog.output}
                            details={nodeLog.details as Record<string, unknown> | undefined}
                            userSettings={userSettings}
                            markdownRows={12}
                        />
                    </div>
                )}
                {!showInputsFirst && inputsPanel}
                {(nodeLog.details as any)?.skill_diagnostics != null && (
                    <details className="mt-2 group/diag">
                        <summary className="cursor-pointer text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary select-none list-none flex items-center gap-1">
                            <ChevronRight size={12} className="group-open/diag:rotate-90 transition-transform shrink-0" />
                            Skill diagnostics (vendor response)
                        </summary>
                        <div className="mt-1.5">
                            <JsonTreeView data={(nodeLog.details as any).skill_diagnostics} defaultExpandedDepth={2} />
                        </div>
                    </details>
                )}
            </div>
        </div>
    );
}
