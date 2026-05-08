/**
 * Edit Companion identity, persona link, and workflow allow-list for the active Workspace.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { ApiClient } from '../api/client';
import type { Companion, CompanionUpdate, PersonaListItem, WorkflowDefinitionListItem } from '../api/types';
import { ManagerModal } from './ManagerModal';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';

export interface CompanionSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    companion: Companion;
    /** Workflow IDs enabled on the current Workspace; Companion can only toggle among these. */
    workspaceEnabledWorkflowIds: string[];
    onSaved: (c: Companion) => void;
}

export const CompanionSettingsModal: React.FC<CompanionSettingsModalProps> = ({
    isOpen,
    onClose,
    companion,
    workspaceEnabledWorkflowIds,
    onSaved,
}) => {
    const [personas, setPersonas] = useState<PersonaListItem[]>([]);
    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [personaId, setPersonaId] = useState<string>('');
    const [defaultMode, setDefaultMode] = useState('');
    const [availableModesStr, setAvailableModesStr] = useState('');
    const [voiceStyle, setVoiceStyle] = useState('');
    const [boundaries, setBoundaries] = useState('');
    const [enabledWorkflowIds, setEnabledWorkflowIds] = useState<Set<string>>(new Set());
    const [memoryApprovalRequired, setMemoryApprovalRequired] = useState(true);

    const workspaceSet = useMemo(
        () => new Set(workspaceEnabledWorkflowIds ?? []),
        [workspaceEnabledWorkflowIds],
    );

    const { regularWorkflows, customSkills } = useMemo(() => {
        const regular: WorkflowDefinitionListItem[] = [];
        const skills: WorkflowDefinitionListItem[] = [];
        for (const w of workflows) {
            if (w.expose_as_custom_skill) {
                skills.push(w);
            } else {
                regular.push(w);
            }
        }
        return { regularWorkflows: regular, customSkills: skills };
    }, [workflows]);

    useEffect(() => {
        if (!isOpen) {
            return;
        }
        setName(companion.name);
        setDescription(companion.description);
        setPersonaId(companion.persona_id ?? '');
        setDefaultMode(companion.default_mode);
        setAvailableModesStr((companion.available_modes ?? []).join(', '));
        const ip = companion.identity_profile ?? {};
        setVoiceStyle(typeof ip.voice_style === 'string' ? ip.voice_style : '');
        setBoundaries(typeof ip.boundaries === 'string' ? ip.boundaries : '');
        setEnabledWorkflowIds(new Set(companion.enabled_workflow_ids ?? []));
        setMemoryApprovalRequired(
            (companion.memory_policy?.approval_required as boolean | undefined) !== false,
        );
        setError(null);
        setLoading(true);
        void Promise.all([
            ApiClient.getPersonas().catch(() => [] as PersonaListItem[]),
            ApiClient.getWorkflows().catch(() => [] as WorkflowDefinitionListItem[]),
        ])
            .then(([p, w]) => {
                setPersonas(p);
                setWorkflows(w);
            })
            .finally(() => setLoading(false));
    }, [isOpen, companion]);

    const toggleWorkflow = (id: string, canToggle: boolean) => {
        if (!canToggle) {
            return;
        }
        setEnabledWorkflowIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const handleSave = async () => {
        if (!name.trim()) {
            setError('Name is required.');
            return;
        }
        setError(null);
        setSaving(true);
        try {
            const patch: CompanionUpdate = {};
            if (name.trim() !== companion.name) {
                patch.name = name.trim();
            }
            if (description !== companion.description) {
                patch.description = description;
            }
            const prevPid = companion.persona_id ?? '';
            const nextPid = personaId || null;
            if (nextPid !== prevPid) {
                patch.persona_id = nextPid;
            }
            if (defaultMode.trim() !== companion.default_mode) {
                patch.default_mode = defaultMode.trim() || 'default';
            }
            const modes = availableModesStr
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);
            if (JSON.stringify(modes) !== JSON.stringify(companion.available_modes)) {
                patch.available_modes = modes.length ? modes : ['default'];
            }
            const nextProfile: Record<string, unknown> = { ...companion.identity_profile };
            if (voiceStyle.trim()) {
                nextProfile.voice_style = voiceStyle.trim();
            } else {
                delete nextProfile.voice_style;
            }
            if (boundaries.trim()) {
                nextProfile.boundaries = boundaries.trim();
            } else {
                delete nextProfile.boundaries;
            }
            if (JSON.stringify(nextProfile) !== JSON.stringify(companion.identity_profile)) {
                patch.identity_profile = nextProfile;
            }
            const nextEnabled = Array.from(enabledWorkflowIds).sort();
            if (
                JSON.stringify(nextEnabled) !==
                JSON.stringify([...(companion.enabled_workflow_ids ?? [])].sort())
            ) {
                patch.enabled_workflow_ids = nextEnabled;
            }
            const prevMem = (companion.memory_policy?.approval_required as boolean | undefined) !== false;
            if (memoryApprovalRequired !== prevMem) {
                patch.memory_policy = {
                    ...companion.memory_policy,
                    approval_required: memoryApprovalRequired,
                };
            }
            if (Object.keys(patch).length === 0) {
                onClose();
                return;
            }
            const updated = await ApiClient.updateCompanion(patch);
            onSaved(updated);
            onClose();
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to save.');
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen) {
        return null;
    }

    const inputCls = MANAGER_INPUT_CLS;
    const labelCls = MANAGER_LABEL_CLS;

    const renderWorkflowSection = (title: string, items: WorkflowDefinitionListItem[]) => {
        if (items.length === 0) {
            return null;
        }
        return (
            <div>
                <span className={labelCls}>{title}</span>
                <p className="text-xs text-mw-text-secondary mb-2">
                    Only workflows enabled for this Workspace can be turned on here. Enable more under{' '}
                    <strong className="text-mw-text-primary">Workspace</strong> first.
                </p>
                <ul className="space-y-2 border border-mw-border rounded-lg p-3 bg-mw-page">
                    {items.map(wf => {
                        const canToggle = workspaceSet.has(wf.id);
                        const checked = enabledWorkflowIds.has(wf.id);
                        return (
                            <li key={wf.id} className="flex items-start gap-2">
                                <input
                                    id={`cc-wf-${wf.id}`}
                                    type="checkbox"
                                    className="rounded border-mw-border mt-0.5"
                                    checked={checked}
                                    disabled={!canToggle}
                                    onChange={() => toggleWorkflow(wf.id, canToggle)}
                                />
                                <label
                                    htmlFor={`cc-wf-${wf.id}`}
                                    className={canToggle ? 'cursor-pointer flex-1 min-w-0' : 'flex-1 min-w-0 opacity-60'}
                                >
                                    <span className="text-sm text-mw-text-primary font-medium">{wf.name}</span>
                                    {!canToggle && (
                                        <span className="block text-[10px] text-mw-text-secondary">
                                            Enable this workflow for the Workspace first
                                        </span>
                                    )}
                                </label>
                            </li>
                        );
                    })}
                </ul>
            </div>
        );
    };

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Companion settings" maxWidth="2xl">
            <div className="flex flex-col h-full min-h-0 overflow-hidden">
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 text-sm text-mw-text-primary">
                    <p className="text-mw-text-secondary text-xs">
                        The Companion is your persistent voice in Workspace chat. Link a{' '}
                        <strong className="text-mw-text-primary">Persona</strong> for system prompt and chat model
                        (under <strong>Configure → Personas</strong>: set <strong>Default model</strong> to an id LM
                        Studio lists, or leave server defaults to pick the first available model).
                    </p>
                    {loading && (
                        <div className="flex items-center gap-2 text-mw-text-secondary">
                            <Loader2 className="animate-spin" size={18} />
                            Loading…
                        </div>
                    )}
                    {error && (
                        <div className="rounded-lg border border-mw-error bg-mw-error-muted px-3 py-2 text-mw-error text-xs">
                            {error}
                        </div>
                    )}
                    <div>
                        <label className={labelCls} htmlFor="companion-name">
                            Display name
                        </label>
                        <input
                            id="companion-name"
                            className={inputCls}
                            value={name}
                            onChange={e => setName(e.target.value)}
                            autoComplete="off"
                        />
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-desc">
                            Short description
                        </label>
                        <textarea
                            id="companion-desc"
                            className={`${inputCls} min-h-[72px]`}
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            rows={3}
                        />
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-persona">
                            Persona (model + system prompt)
                        </label>
                        <select
                            id="companion-persona"
                            className={inputCls}
                            value={personaId}
                            onChange={e => setPersonaId(e.target.value)}
                        >
                            <option value="">None</option>
                            {personas.map(p => (
                                <option key={p.id} value={p.id}>
                                    {p.name}
                                    {p.type === 'system' ? ' (system)' : ''}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-mode">
                            Default mode
                        </label>
                        <input
                            id="companion-mode"
                            className={inputCls}
                            value={defaultMode}
                            onChange={e => setDefaultMode(e.target.value)}
                            placeholder="default"
                        />
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-modes">
                            Available modes (comma-separated)
                        </label>
                        <input
                            id="companion-modes"
                            className={inputCls}
                            value={availableModesStr}
                            onChange={e => setAvailableModesStr(e.target.value)}
                            placeholder="default, concise_execution"
                        />
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-voice">
                            Voice / style (optional)
                        </label>
                        <textarea
                            id="companion-voice"
                            className={`${inputCls} min-h-[60px]`}
                            value={voiceStyle}
                            onChange={e => setVoiceStyle(e.target.value)}
                            placeholder="How the Companion should sound in replies…"
                            rows={2}
                        />
                    </div>
                    <div>
                        <label className={labelCls} htmlFor="companion-bounds">
                            Behavioral boundaries (optional)
                        </label>
                        <textarea
                            id="companion-bounds"
                            className={`${inputCls} min-h-[60px]`}
                            value={boundaries}
                            onChange={e => setBoundaries(e.target.value)}
                            placeholder="Topics or tones to avoid…"
                            rows={2}
                        />
                    </div>
                    {!loading && workflows.length > 0 && (
                        <>
                            {renderWorkflowSection('Workflows', regularWorkflows)}
                            {renderWorkflowSection('Custom Skills', customSkills)}
                        </>
                    )}
                    <div className="flex items-center gap-2">
                        <input
                            id="memory-approval"
                            type="checkbox"
                            className="rounded border-mw-border"
                            checked={memoryApprovalRequired}
                            onChange={e => setMemoryApprovalRequired(e.target.checked)}
                        />
                        <label htmlFor="memory-approval" className="text-xs cursor-pointer">
                            Require my approval before saving long-term memories
                        </label>
                    </div>
                </div>
                <div className="shrink-0 border-t border-mw-border px-6 py-4 flex justify-end gap-2 bg-mw-card">
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-sm border border-mw-border text-mw-text-primary hover:bg-mw-card-alt"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleSave()}
                        disabled={saving}
                        className="px-4 py-2 rounded-lg text-sm bg-mw-primary text-white hover:opacity-90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="animate-spin" size={16} />}
                        Save
                    </button>
                </div>
            </div>
        </ManagerModal>
    );
};
