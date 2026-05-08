/**
 * Workspace Companion pipeline: per-stage prompts/models and post-compose steps.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';

import { ApiClient } from '../api/client';
import type {
    CompanionPipelineStored,
    ProcessStepKind,
    Workspace,
    WorkspacePipelinePreviewResponse,
} from '../api/types';
import type { WorkspaceStreamStageEvent } from '../api/workspaceStream';

const PROCESS_KINDS: ProcessStepKind[] = ['review', 'critique', 'summarize', 'investigate', 'analyze'];

const COMPANION_PIPELINE_KEY = 'companion_pipeline';

function defaultPipeline(): CompanionPipelineStored {
    return {
        version: 1,
        stages: {
            interpret: { enabled: true, model_override: '', system_prompt_base: '', system_instructions_append: '' },
            compose: { enabled: true, model_override: '', voice_override: '', instructions_append: '' },
            session_summary: { enabled: true, model_override: '', instructions_append: '' },
        },
        process: [],
        post_compose: [],
    };
}

function readPipelineFromWorkspace(workspace: Workspace): CompanionPipelineStored {
    const rc = workspace.runtime_configuration;
    const raw =
        rc && typeof rc === 'object' && !Array.isArray(rc)
            ? (rc as Record<string, unknown>)[COMPANION_PIPELINE_KEY]
            : undefined;
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        return defaultPipeline();
    }
    const d = defaultPipeline();
    try {
        const o = raw as Record<string, unknown>;
        if (typeof o.version === 'number') {
            d.version = o.version;
        }
        const st = o.stages as Record<string, unknown> | undefined;
        if (st && typeof st === 'object') {
            const interp = st.interpret as Record<string, unknown> | undefined;
            if (interp && typeof interp === 'object') {
                d.stages.interpret = {
                    enabled: interp.enabled !== false,
                    model_override: String(interp.model_override ?? '').trim() || '',
                    system_prompt_base: String(interp.system_prompt_base ?? '') || '',
                    system_instructions_append: String(interp.system_instructions_append ?? '') || '',
                };
            }
            const comp = st.compose as Record<string, unknown> | undefined;
            if (comp && typeof comp === 'object') {
                d.stages.compose = {
                    enabled: comp.enabled !== false,
                    model_override: String(comp.model_override ?? '').trim() || '',
                    voice_override: String(comp.voice_override ?? '') || '',
                    instructions_append: String(comp.instructions_append ?? '') || '',
                };
            }
            const ss = st.session_summary as Record<string, unknown> | undefined;
            if (ss && typeof ss === 'object') {
                d.stages.session_summary = {
                    enabled: ss.enabled !== false,
                    model_override: String(ss.model_override ?? '').trim() || '',
                    instructions_append: String(ss.instructions_append ?? '') || '',
                };
            }
        }
        const proc = o.process;
        if (Array.isArray(proc)) {
            d.process = proc
                .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x))
                .map((x, i) => ({
                    id: String(x.id ?? `proc_${i}`),
                    kind: (PROCESS_KINDS.includes(x.kind as ProcessStepKind) ? x.kind : 'summarize') as ProcessStepKind,
                    enabled: x.enabled !== false,
                    name: String(x.name ?? ''),
                    model: String(x.model ?? '').trim() || '',
                    description: String(x.description ?? ''),
                    max_iterations: typeof x.max_iterations === 'number' ? x.max_iterations : 3,
                    questions: Array.isArray(x.questions) ? x.questions.map(String) : [],
                    expose_in_traces: x.expose_in_traces !== false,
                }));
        }
        const pc = o.post_compose;
        if (Array.isArray(pc)) {
            d.post_compose = pc
                .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x))
                .map((x, i) => ({
                    id: String(x.id ?? `step_${i}`),
                    enabled: x.enabled !== false,
                    name: String(x.name ?? ''),
                    model: String(x.model ?? '').trim() || '',
                    system_prompt: String(x.system_prompt ?? ''),
                    replace_streamed_reply: !!x.replace_streamed_reply,
                    expose_in_traces: x.expose_in_traces !== false,
                    output_key: String(x.output_key ?? 'text'),
                }));
        }
    } catch {
        return defaultPipeline();
    }
    return d;
}

function serializePipeline(form: CompanionPipelineStored): Record<string, unknown> {
    const strip = (s: string) => s.trim();
    const optModel = (s: string) => {
        const t = strip(s);
        return t || null;
    };
    return {
        version: form.version || 1,
        stages: {
            interpret: {
                enabled: form.stages.interpret.enabled,
                model_override: optModel(form.stages.interpret.model_override ?? ''),
                system_instructions_append: (form.stages.interpret.system_instructions_append ?? '').trim() || null,
            },
            compose: {
                enabled: form.stages.compose.enabled,
                model_override: optModel(form.stages.compose.model_override ?? ''),
                voice_override: (form.stages.compose.voice_override ?? '').trim() || null,
                instructions_append: (form.stages.compose.instructions_append ?? '').trim() || null,
            },
            session_summary: {
                enabled: form.stages.session_summary.enabled,
                model_override: optModel(form.stages.session_summary.model_override ?? ''),
                instructions_append: (form.stages.session_summary.instructions_append ?? '').trim() || null,
            },
        },
        process: form.process.map(s => ({
            id: strip(s.id) || 'proc',
            kind: s.kind,
            enabled: s.enabled,
            name: (s.name ?? '').trim(),
            model: optModel(s.model ?? ''),
            description: s.description ?? '',
            max_iterations: s.max_iterations || 3,
            questions: s.questions.filter(q => q.trim()),
            expose_in_traces: s.expose_in_traces,
        })),
        post_compose: form.post_compose.map(s => ({
            id: strip(s.id) || 'step',
            enabled: s.enabled,
            name: (s.name ?? '').trim(),
            model: optModel(s.model ?? ''),
            system_prompt: s.system_prompt ?? '',
            replace_streamed_reply: s.replace_streamed_reply,
            expose_in_traces: s.expose_in_traces,
            output_key: strip(s.output_key) || 'text',
        })),
    };
}

export interface WorkspacePipelinePanelProps {
    workspace: Workspace;
    onClose: () => void;
    onSaved: (w: Workspace) => void;
    runStages: WorkspaceStreamStageEvent[];
}

export const WorkspacePipelinePanel: React.FC<WorkspacePipelinePanelProps> = ({
    workspace,
    onClose,
    onSaved,
    runStages,
}) => {
    const [draft, setDraft] = useState<CompanionPipelineStored>(() => readPipelineFromWorkspace(workspace));
    const [preview, setPreview] = useState<WorkspacePipelinePreviewResponse | null>(null);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewError, setPreviewError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    useEffect(() => {
        setDraft(readPipelineFromWorkspace(workspace));
        setPreview(null);
        setPreviewError(null);
        setSaveError(null);
    }, [workspace]);

    const loadPreview = useCallback(async () => {
        setPreviewLoading(true);
        setPreviewError(null);
        try {
            const p = await ApiClient.getWorkspacePipelinePreview(workspace.id);
            setPreview(p);
        } catch (e) {
            setPreview(null);
            setPreviewError(e instanceof Error ? e.message : 'Preview failed');
        } finally {
            setPreviewLoading(false);
        }
    }, [workspace.id]);

    const save = useCallback(async () => {
        setSaving(true);
        setSaveError(null);
        try {
            const rc = { ...workspace.runtime_configuration, companion_pipeline: serializePipeline(draft) };
            const w = await ApiClient.updateWorkspace(workspace.id, { runtime_configuration: rc });
            onSaved(w);
        } catch (e) {
            setSaveError(e instanceof Error ? e.message : 'Save failed');
        } finally {
            setSaving(false);
        }
    }, [draft, workspace.id, workspace.runtime_configuration, onSaved]);

    const addProcessStep = (kind: ProcessStepKind) => {
        const id =
            typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID().slice(0, 8)
                : `pr${Date.now()}`;
        setDraft(prev => ({
            ...prev,
            process: [
                ...prev.process,
                {
                    id,
                    kind,
                    enabled: true,
                    name: '',
                    model: '',
                    description: '',
                    max_iterations: 3,
                    questions: [],
                    expose_in_traces: true,
                },
            ],
        }));
    };

    const removeProcessStep = (idx: number) => {
        setDraft(prev => ({
            ...prev,
            process: prev.process.filter((_, i) => i !== idx),
        }));
    };

    const addPostStep = () => {
        const id =
            typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID().slice(0, 8)
                : `p${Date.now()}`;
        setDraft(prev => ({
            ...prev,
            post_compose: [
                ...prev.post_compose,
                {
                    id,
                    enabled: true,
                    name: '',
                    model: '',
                    system_prompt:
                        'Rewrite the assistant reply below as a single spoken paragraph for text-to-speech: no markdown headings, bullets, or list markers; keep every fact; natural conversational tone.\n\n{{reply_text}}',
                    replace_streamed_reply: false,
                    expose_in_traces: true,
                    output_key: 'tts_plaintext',
                },
            ],
        }));
    };

    const removePostStep = (idx: number) => {
        setDraft(prev => ({
            ...prev,
            post_compose: prev.post_compose.filter((_, i) => i !== idx),
        }));
    };

    return (
        <aside
            className="w-[min(100%,22rem)] shrink-0 flex flex-col border-l border-mw-border bg-mw-card min-h-0 overflow-hidden"
            aria-label="Companion pipeline"
        >
            <div className="shrink-0 flex items-center justify-between gap-2 px-3 py-2 border-b border-mw-border">
                <h3 className="text-xs font-semibold text-mw-text-primary">Pipeline</h3>
                <button
                    type="button"
                    onClick={onClose}
                    className="p-1 rounded-lg text-mw-text-secondary hover:bg-mw-page hover:text-mw-text-primary"
                    title="Close"
                >
                    <X size={16} aria-hidden />
                </button>
            </div>

            {runStages.length > 0 && (
                <div className="shrink-0 border-b border-mw-border px-3 py-2 max-h-32 overflow-y-auto">
                    <p className="text-[10px] font-semibold text-mw-text-secondary uppercase tracking-wide mb-1">
                        Live run
                    </p>
                    <ul className="text-[10px] font-mono text-mw-text-primary space-y-0.5">
                        {runStages.map((s, i) => (
                            <li key={`${i}-${s.stage}-${s.status}`}>
                                <span>
                                    {s.stage} · {s.status}
                                    {typeof s.ms === 'number' ? ` · ${s.ms.toFixed(0)}ms` : ''}
                                </span>
                                {s.stage === 'execute' &&
                                    s.status === 'completed' &&
                                    s.detail &&
                                    Array.isArray((s.detail as Record<string, unknown>).capability_results) && (
                                        <ul className="ml-3 mt-0.5 space-y-0.5 text-mw-text-secondary">
                                            {(
                                                (s.detail as Record<string, unknown>).capability_results as Array<{
                                                    capability_key?: string;
                                                    status?: string;
                                                    error?: string | null;
                                                }>
                                            ).map((cr, j) => (
                                                <li key={j}>
                                                    {cr.capability_key ?? '?'} · {cr.status ?? '?'}
                                                    {cr.error ? ` · ${cr.error}` : ''}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4 text-xs">
                <section className="space-y-2">
                    <p className="font-semibold text-mw-text-primary">Interpret</p>
                    <label className="flex items-center gap-2 text-mw-text-secondary">
                        <input
                            type="checkbox"
                            checked={draft.stages.interpret.enabled}
                            onChange={e =>
                                setDraft(p => ({
                                    ...p,
                                    stages: {
                                        ...p.stages,
                                        interpret: { ...p.stages.interpret, enabled: e.target.checked },
                                    },
                                }))
                            }
                        />
                        Apply custom instructions / model
                    </label>
                    <input
                        type="text"
                        placeholder="Model override (optional)"
                        value={draft.stages.interpret.model_override ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    interpret: { ...p.stages.interpret, model_override: e.target.value },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary"
                    />
                    <div className="space-y-1">
                        <div className="flex items-center justify-between">
                            <span className="text-[11px] text-mw-text-secondary">Base classifier prompt</span>
                            {(draft.stages.interpret.system_prompt_base ?? '').trim() !== '' && (
                                <button
                                    type="button"
                                    onClick={() =>
                                        setDraft(p => ({
                                            ...p,
                                            stages: {
                                                ...p.stages,
                                                interpret: { ...p.stages.interpret, system_prompt_base: '' },
                                            },
                                        }))
                                    }
                                    className="text-[10px] text-mw-text-secondary hover:text-mw-text-primary underline"
                                >
                                    Reset to default
                                </button>
                            )}
                        </div>
                        <textarea
                            placeholder="Base classifier prompt (leave empty for built-in default)"
                            rows={5}
                            value={draft.stages.interpret.system_prompt_base ?? ''}
                            onChange={e =>
                                setDraft(p => ({
                                    ...p,
                                    stages: {
                                        ...p.stages,
                                        interpret: { ...p.stages.interpret, system_prompt_base: e.target.value },
                                    },
                                }))
                            }
                            className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary resize-y min-h-[5rem] text-[11px]"
                        />
                    </div>
                    <textarea
                        placeholder="Additional classifier instructions (prepended before capability list)"
                        rows={3}
                        value={draft.stages.interpret.system_instructions_append ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    interpret: { ...p.stages.interpret, system_instructions_append: e.target.value },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary resize-y min-h-[4rem]"
                    />
                </section>

                <section className="space-y-2">
                    <p className="font-semibold text-mw-text-primary">Compose</p>
                    <label className="flex items-center gap-2 text-mw-text-secondary">
                        <input
                            type="checkbox"
                            checked={draft.stages.compose.enabled}
                            onChange={e =>
                                setDraft(p => ({
                                    ...p,
                                    stages: {
                                        ...p.stages,
                                        compose: { ...p.stages.compose, enabled: e.target.checked },
                                    },
                                }))
                            }
                        />
                        Apply custom voice / instructions / model
                    </label>
                    <input
                        type="text"
                        placeholder="Model override (optional)"
                        value={draft.stages.compose.model_override ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    compose: { ...p.stages.compose, model_override: e.target.value },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary"
                    />
                    <textarea
                        placeholder="Voice override (replaces Persona system prompt when set)"
                        rows={2}
                        value={draft.stages.compose.voice_override ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    compose: { ...p.stages.compose, voice_override: e.target.value },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary resize-y"
                    />
                    <textarea
                        placeholder="Additional compose instructions (appended)"
                        rows={2}
                        value={draft.stages.compose.instructions_append ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    compose: { ...p.stages.compose, instructions_append: e.target.value },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary resize-y"
                    />
                </section>

                <section className="space-y-2">
                    <p className="font-semibold text-mw-text-primary">Session summary</p>
                    <label className="flex items-center gap-2 text-mw-text-secondary">
                        <input
                            type="checkbox"
                            checked={draft.stages.session_summary.enabled}
                            onChange={e =>
                                setDraft(p => ({
                                    ...p,
                                    stages: {
                                        ...p.stages,
                                        session_summary: {
                                            ...p.stages.session_summary,
                                            enabled: e.target.checked,
                                        },
                                    },
                                }))
                            }
                        />
                        Apply custom model / instructions
                    </label>
                    <input
                        type="text"
                        placeholder="Model override (optional)"
                        value={draft.stages.session_summary.model_override ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    session_summary: {
                                        ...p.stages.session_summary,
                                        model_override: e.target.value,
                                    },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary"
                    />
                    <textarea
                        placeholder="Additional session-summary instructions"
                        rows={2}
                        value={draft.stages.session_summary.instructions_append ?? ''}
                        onChange={e =>
                            setDraft(p => ({
                                ...p,
                                stages: {
                                    ...p.stages,
                                    session_summary: {
                                        ...p.stages.session_summary,
                                        instructions_append: e.target.value,
                                    },
                                },
                            }))
                        }
                        className="w-full rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-mw-text-primary resize-y"
                    />
                </section>

                <section className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-mw-text-primary">Process</p>
                        <div className="flex items-center gap-1">
                            <select
                                id="process-kind-select"
                                className="text-[10px] rounded border border-mw-border bg-mw-page px-1 py-0.5 text-mw-text-primary"
                                defaultValue="summarize"
                            >
                                {PROCESS_KINDS.map(k => (
                                    <option key={k} value={k}>{k}</option>
                                ))}
                            </select>
                            <button
                                type="button"
                                onClick={() => {
                                    const el = document.getElementById('process-kind-select') as HTMLSelectElement | null;
                                    const kind = (el?.value ?? 'summarize') as ProcessStepKind;
                                    addProcessStep(kind);
                                }}
                                className="text-[11px] font-medium text-mw-primary hover:underline"
                            >
                                + Add
                            </button>
                        </div>
                    </div>
                    <p className="text-[10px] text-mw-text-secondary">
                        Process steps run between execute and compose. Each step analyzes execution output.
                    </p>
                    {draft.process.map((step, idx) => (
                        <div key={step.id + idx} className="rounded-lg border border-mw-border p-2 space-y-2 bg-mw-page">
                            <div className="flex items-center justify-between gap-1">
                                <div className="flex items-center gap-2">
                                    <label className="flex items-center gap-1 text-mw-text-secondary">
                                        <input
                                            type="checkbox"
                                            checked={step.enabled}
                                            onChange={e => {
                                                const on = e.target.checked;
                                                setDraft(p => {
                                                    const pr = [...p.process];
                                                    pr[idx] = { ...pr[idx], enabled: on };
                                                    return { ...p, process: pr };
                                                });
                                            }}
                                        />
                                        On
                                    </label>
                                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-mw-card-alt text-mw-text-secondary">
                                        {step.kind}
                                    </span>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => removeProcessStep(idx)}
                                    className="text-[10px] text-mw-error hover:underline"
                                >
                                    Remove
                                </button>
                            </div>
                            <input
                                type="text"
                                placeholder="id"
                                value={step.id}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pr = [...p.process];
                                        pr[idx] = { ...pr[idx], id: v };
                                        return { ...p, process: pr };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 font-mono text-[11px]"
                            />
                            <input
                                type="text"
                                placeholder="Name (optional)"
                                value={step.name}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pr = [...p.process];
                                        pr[idx] = { ...pr[idx], name: v };
                                        return { ...p, process: pr };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px]"
                            />
                            <input
                                type="text"
                                placeholder="Model override (optional)"
                                value={step.model ?? ''}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pr = [...p.process];
                                        pr[idx] = { ...pr[idx], model: v };
                                        return { ...p, process: pr };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px]"
                            />
                            <textarea
                                rows={3}
                                placeholder="Description of desired output"
                                value={step.description}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pr = [...p.process];
                                        pr[idx] = { ...pr[idx], description: v };
                                        return { ...p, process: pr };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px] resize-y"
                            />
                            {step.kind === 'review' && (
                                <label className="flex items-center gap-2 text-mw-text-secondary">
                                    <span className="text-[10px]">Max iterations:</span>
                                    <input
                                        type="number"
                                        min={1}
                                        max={10}
                                        value={step.max_iterations}
                                        onChange={e => {
                                            const v = Math.max(1, Math.min(10, Number(e.target.value) || 3));
                                            setDraft(p => {
                                                const pr = [...p.process];
                                                pr[idx] = { ...pr[idx], max_iterations: v };
                                                return { ...p, process: pr };
                                            });
                                        }}
                                        className="w-16 rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px]"
                                    />
                                </label>
                            )}
                            {step.kind === 'investigate' && (
                                <div className="space-y-1">
                                    <p className="text-[10px] text-mw-text-secondary">Questions (one per line):</p>
                                    <textarea
                                        rows={3}
                                        placeholder="Enter questions, one per line"
                                        value={step.questions.join('\n')}
                                        onChange={e => {
                                            const qs = e.target.value.split('\n');
                                            setDraft(p => {
                                                const pr = [...p.process];
                                                pr[idx] = { ...pr[idx], questions: qs };
                                                return { ...p, process: pr };
                                            });
                                        }}
                                        className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px] resize-y font-mono"
                                    />
                                </div>
                            )}
                        </div>
                    ))}
                </section>

                <section className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-mw-text-primary">Post-compose</p>
                        <button
                            type="button"
                            onClick={addPostStep}
                            className="text-[11px] font-medium text-mw-primary hover:underline"
                        >
                            + Add step
                        </button>
                    </div>
                    <p className="text-[10px] text-mw-text-secondary">
                        Templates: {'{{reply_text}}'}, {'{{composed_reply}}'}, {'{{user_message}}'},{' '}
                        {'{{execution_summary}}'}, {'{{stream_text}}'}, {'{{last_output}}'}.
                    </p>
                    {draft.post_compose.map((step, idx) => (
                        <div key={step.id + idx} className="rounded-lg border border-mw-border p-2 space-y-2 bg-mw-page">
                            <div className="flex items-center justify-between gap-1">
                                <label className="flex items-center gap-1 text-mw-text-secondary">
                                    <input
                                        type="checkbox"
                                        checked={step.enabled}
                                        onChange={e => {
                                            const on = e.target.checked;
                                            setDraft(p => {
                                                const pc = [...p.post_compose];
                                                pc[idx] = { ...pc[idx], enabled: on };
                                                return { ...p, post_compose: pc };
                                            });
                                        }}
                                    />
                                    On
                                </label>
                                <button
                                    type="button"
                                    onClick={() => removePostStep(idx)}
                                    className="text-[10px] text-mw-error hover:underline"
                                >
                                    Remove
                                </button>
                            </div>
                            <input
                                type="text"
                                placeholder="id"
                                value={step.id}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pc = [...p.post_compose];
                                        pc[idx] = { ...pc[idx], id: v };
                                        return { ...p, post_compose: pc };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 font-mono text-[11px]"
                            />
                            <input
                                type="text"
                                placeholder="Output metadata key (e.g. tts_plaintext)"
                                value={step.output_key}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pc = [...p.post_compose];
                                        pc[idx] = { ...pc[idx], output_key: v };
                                        return { ...p, post_compose: pc };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px]"
                            />
                            <input
                                type="text"
                                placeholder="Model override (optional)"
                                value={step.model ?? ''}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pc = [...p.post_compose];
                                        pc[idx] = { ...pc[idx], model: v };
                                        return { ...p, post_compose: pc };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px]"
                            />
                            <label className="flex items-center gap-2 text-mw-text-secondary">
                                <input
                                    type="checkbox"
                                    checked={step.replace_streamed_reply}
                                    onChange={e => {
                                        const on = e.target.checked;
                                        setDraft(p => {
                                            const pc = [...p.post_compose];
                                            pc[idx] = { ...pc[idx], replace_streamed_reply: on };
                                            return { ...p, post_compose: pc };
                                        });
                                    }}
                                />
                                Replace streamed chat text with this output
                            </label>
                            <textarea
                                rows={4}
                                value={step.system_prompt}
                                onChange={e => {
                                    const v = e.target.value;
                                    setDraft(p => {
                                        const pc = [...p.post_compose];
                                        pc[idx] = { ...pc[idx], system_prompt: v };
                                        return { ...p, post_compose: pc };
                                    });
                                }}
                                className="w-full rounded border border-mw-border bg-mw-card px-2 py-1 text-[11px] resize-y font-mono"
                            />
                        </div>
                    ))}
                </section>

                <div className="flex flex-wrap gap-2 pt-1">
                    <button
                        type="button"
                        onClick={() => void loadPreview()}
                        disabled={previewLoading}
                        className="rounded-lg border border-mw-border bg-mw-page px-3 py-1.5 font-medium text-mw-text-primary hover:bg-mw-card-alt disabled:opacity-50 flex items-center gap-1"
                    >
                        {previewLoading ? <Loader2 className="animate-spin" size={14} /> : null}
                        Preview effective prompts
                    </button>
                </div>
                {previewError && <p className="text-mw-error text-[11px]">{previewError}</p>}
                {preview && (
                    <div className="rounded-lg border border-mw-border bg-mw-page p-2 space-y-2 text-[10px] font-mono max-h-64 overflow-y-auto whitespace-pre-wrap break-words">
                        <p className="font-sans font-semibold text-mw-text-primary text-xs">Models</p>
                        <pre>{JSON.stringify(preview.models, null, 2)}</pre>
                        <p className="font-sans font-semibold text-mw-text-primary text-xs">Interpret system</p>
                        <pre>{preview.interpret_system}</pre>
                        <p className="font-sans font-semibold text-mw-text-primary text-xs">Compose system</p>
                        <pre>{preview.compose_system}</pre>
                        <p className="font-sans font-semibold text-mw-text-primary text-xs">Session summary system</p>
                        <pre>{preview.session_summary_system}</pre>
                        {preview.process && preview.process.length > 0 ? (
                            <>
                                <p className="font-sans font-semibold text-mw-text-primary text-xs">Process</p>
                                <pre>{JSON.stringify(preview.process, null, 2)}</pre>
                            </>
                        ) : null}
                        {preview.post_compose.length > 0 ? (
                            <>
                                <p className="font-sans font-semibold text-mw-text-primary text-xs">Post-compose</p>
                                <pre>{JSON.stringify(preview.post_compose, null, 2)}</pre>
                            </>
                        ) : null}
                    </div>
                )}

                {saveError && <p className="text-mw-error text-[11px]">{saveError}</p>}
                <button
                    type="button"
                    onClick={() => void save()}
                    disabled={saving}
                    className="w-full rounded-xl bg-mw-primary text-white py-2 font-medium text-xs disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {saving ? <Loader2 className="animate-spin" size={16} /> : null}
                    Save pipeline
                </button>
            </div>
        </aside>
    );
};
