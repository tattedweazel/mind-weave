/**
 * Per-node rows for Workflow Editor Run Logs and Sandbox “Last brain run” — parity with
 * recorded outputs, inputs, sub-workflow steps, and skill diagnostics.
 */
import React from 'react';
import { CheckCircle2, ChevronRight, XCircle } from 'lucide-react';

import type { NodeRunResult } from '../../api/types';
import { JsonTreeView } from './JsonTreeView';
import { lastRunInputsPayload } from './lastRunInputsPayload';
import { RunInputsExplorer } from './RunInputsExplorer';
import { WorkflowNodeRunOutputBody } from './WorkflowNodeRunOutputBody';

export interface WorkflowRunLogsNodeResultsListProps {
    node_results: NodeRunResult[];
    getNodeLabel: (nodeId: string) => string;
    userSettings?: Record<string, unknown>;
}

export function WorkflowRunLogsNodeResultsList({
    node_results,
    getNodeLabel,
    userSettings,
}: WorkflowRunLogsNodeResultsListProps) {
    return (
        <div className="space-y-3">
            {[...node_results].sort((a, b) => (a.step_number ?? 1e9) - (b.step_number ?? 1e9)).map((r, idx) => {
                const label = getNodeLabel(r.node_id);

                let outputBody: React.ReactNode = null;
                if (r.output) {
                    outputBody = (
                        <WorkflowNodeRunOutputBody
                            nodeId={r.node_id}
                            output={r.output}
                            details={r.details as Record<string, unknown> | undefined}
                            userSettings={userSettings}
                            markdownRows={10}
                        />
                    );
                }

                const inputsPayload = lastRunInputsPayload(r.details as Record<string, unknown> | undefined);
                const hasDetails =
                    !!inputsPayload ||
                    !!r.details?.sub_workflow_node_results ||
                    !!(r.details as Record<string, unknown> | undefined)?.skill_diagnostics;
                const showInputsFirst =
                    !!inputsPayload && (r.status !== 'ok' || (r.error != null && r.error !== ''));

                const inputsSection = inputsPayload ? (
                    <div>
                        <span className="font-semibold text-mw-text-secondary uppercase tracking-widest text-[10px] mb-1 block">
                            Inputs
                        </span>
                        <RunInputsExplorer payload={inputsPayload} />
                    </div>
                ) : null;

                const outputSection =
                    (outputBody || r.error) && (
                        <div>
                            <span className="font-semibold text-mw-text-secondary uppercase tracking-widest text-[10px] mb-1 block">
                                Output
                            </span>
                            {outputBody}
                            {r.error && (
                                <div className="bg-red-50 dark:bg-red-900/10 text-red-600 dark:text-red-400 rounded p-2 whitespace-pre-wrap mt-2">
                                    {r.error}
                                </div>
                            )}
                        </div>
                    );

                return (
                    <details
                        key={`${r.node_id}-${r.step_number ?? idx}`}
                        className="bg-mw-card rounded-lg border border-mw-border overflow-hidden group"
                    >
                        <summary className="flex items-center gap-2 p-3 cursor-pointer hover:bg-mw-card-alt/70 transition-colors list-none select-none">
                            {r.status === 'ok' ? (
                                <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                            ) : (
                                <XCircle size={14} className="text-red-500 shrink-0" />
                            )}
                            <span className="text-sm font-medium text-mw-text-primary truncate">{label}</span>
                            {r.step_number != null && (
                                <span className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary shrink-0">
                                    Step {r.step_number}
                                </span>
                            )}
                            {r.latency_ms !== undefined && r.latency_ms !== null && (
                                <span className="text-xs text-mw-text-secondary ml-auto">{r.latency_ms.toFixed(1)}ms</span>
                            )}
                        </summary>

                        <div className="p-3 pt-0 text-xs border-t border-mw-border mt-1 space-y-3">
                            {showInputsFirst ? inputsSection : outputSection}
                            {showInputsFirst ? outputSection : inputsSection}
                            {(r.details as Record<string, unknown> | undefined)?.skill_diagnostics != null && (
                                <details className="mt-3 group/logdiag">
                                    <summary className="cursor-pointer font-semibold text-mw-text-secondary uppercase tracking-widest text-[10px] mb-1 select-none list-none flex items-center gap-1">
                                        <ChevronRight
                                            size={12}
                                            className="group-open/logdiag:rotate-90 transition-transform shrink-0"
                                        />
                                        Skill diagnostics
                                    </summary>
                                    <JsonTreeView
                                        data={(r.details as Record<string, unknown>).skill_diagnostics as Record<string, unknown>}
                                        defaultExpandedDepth={2}
                                    />
                                </details>
                            )}
                            {r.details?.sub_workflow_node_results && (
                                <div className="mt-3">
                                    <span className="font-semibold text-mw-text-secondary uppercase tracking-widest text-[10px] mb-1.5 block">
                                        Sub-workflow: {r.details.sub_workflow_name ?? 'Sub-workflow'}
                                    </span>
                                    <div className="space-y-1.5">
                                        {(r.details.sub_workflow_node_results as { node_id: string; status: string; latency_ms?: number; error?: string }[]).map(sr => {
                                            const srId = sr.node_id;
                                            const stepLabel =
                                                (r.details?.sub_workflow_node_labels as Record<string, string> | undefined)?.[
                                                    srId
                                                ] ?? srId;
                                            return (
                                                <div
                                                    key={srId}
                                                    className="flex items-start gap-2 text-xs bg-mw-card-alt rounded p-2 border border-mw-border"
                                                >
                                                    {sr.status === 'ok' ? (
                                                        <CheckCircle2
                                                            size={12}
                                                            className="text-emerald-500 shrink-0 mt-0.5"
                                                        />
                                                    ) : (
                                                        <XCircle size={12} className="text-red-500 shrink-0 mt-0.5" />
                                                    )}
                                                    <div className="flex-1 min-w-0">
                                                        <span className="font-medium text-mw-text-primary">{stepLabel}</span>
                                                        {sr.latency_ms != null && (
                                                            <span className="text-mw-text-secondary ml-1">
                                                                {Number(sr.latency_ms).toFixed(0)}ms
                                                            </span>
                                                        )}
                                                        {sr.error ? (
                                                            <div className="text-red-600 dark:text-red-400 mt-1 text-[11px] whitespace-pre-wrap break-all">
                                                                {sr.error}
                                                            </div>
                                                        ) : null}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                            {!outputBody &&
                                !r.error &&
                                !hasDetails &&
                                !r.details?.sub_workflow_node_results &&
                                !(r.details as Record<string, unknown> | undefined)?.skill_diagnostics && (
                                    <div className="text-mw-text-secondary italic">No output recorded.</div>
                                )}
                        </div>
                    </details>
                );
            })}
        </div>
    );
}
