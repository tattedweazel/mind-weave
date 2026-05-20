/**
 * Workspace: workflows and interpretation model.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { ApiClient } from '../api/client';
import type {
    ModelsResponse,
    WorkflowDefinitionListItem,
    Workspace,
    WorkspaceUpdate,
} from '../api/types';
import { ManagerModal } from './ManagerModal';
import { MANAGER_LABEL_CLS } from './managerShellStyles';

export interface WorkspaceSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    workspace: Workspace;
    onSaved: (w: Workspace) => void;
}

export const WorkspaceSettingsModal: React.FC<WorkspaceSettingsModalProps> = ({
    isOpen,
    onClose,
    workspace,
    onSaved,
}) => {
    const [workflows, setWorkflows] = useState<WorkflowDefinitionListItem[]>([]);
    const [models, setModels] = useState<ModelsResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [enabledIds, setEnabledIds] = useState<Set<string>>(new Set());
    const [interpretationModel, setInterpretationModel] = useState('');

    useEffect(() => {
        if (!isOpen) {
            return;
        }
        setEnabledIds(new Set(workspace.enabled_workflow_ids ?? []));
        setInterpretationModel((workspace.interpretation_model ?? '').trim());
        setError(null);
        setLoading(true);
        Promise.all([
            ApiClient.getWorkflows(),
            ApiClient.getModels().catch(() => ({ local: [] as string[], external: [] as string[] }) as ModelsResponse),
        ])
            .then(([wfs, mdl]) => {
                setWorkflows(wfs);
                setModels(mdl);
                if (mdl.lm_studio_list_error) {
                    setError(mdl.lm_studio_list_error);
                }
            })
            .catch(() => {
                setWorkflows([]);
                setError('Could not load workflows.');
            })
            .finally(() => {
                setLoading(false);
            });
    }, [isOpen, workspace]);

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

    const toggleId = (id: string) => {
        setEnabledIds(prev => {
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
        setError(null);
        const patch: WorkspaceUpdate = {};
        const nextList = Array.from(enabledIds).sort();
        const prevList = [...(workspace.enabled_workflow_ids ?? [])].sort();
        if (JSON.stringify(nextList) !== JSON.stringify(prevList)) {
            patch.enabled_workflow_ids = nextList;
        }
        const imNext = interpretationModel.trim();
        const imPrev = (workspace.interpretation_model ?? '').trim();
        if (imNext !== imPrev) {
            patch.interpretation_model = imNext || null;
        }
        if (Object.keys(patch).length === 0) {
            onClose();
            return;
        }
        setSaving(true);
        try {
            const updated = await ApiClient.updateWorkspace(workspace.id, patch);
            onSaved(updated);
            onClose();
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to save.');
        } finally {
            setSaving(false);
        }
    };

    const inputCls =
        'w-full px-3 py-2 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary/30';
    const labelCls = MANAGER_LABEL_CLS;

    const renderSection = (title: string, items: WorkflowDefinitionListItem[]) => {
        if (items.length === 0) return null;
        return (
            <div className="space-y-2">
                <p className={labelCls}>{title}</p>
                <ul className="space-y-1 max-h-48 overflow-y-auto border border-mw-border rounded-lg p-2 bg-mw-page">
                    {items.map(w => (
                        <li key={w.id}>
                            <label className="flex items-center gap-2 cursor-pointer text-sm text-mw-text-primary py-1">
                                <input
                                    type="checkbox"
                                    checked={enabledIds.has(w.id)}
                                    onChange={() => toggleId(w.id)}
                                    className="rounded border-mw-border"
                                />
                                <span className="truncate">{w.name}</span>
                            </label>
                        </li>
                    ))}
                </ul>
            </div>
        );
    };

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Workspace settings" maxWidth="2xl">
            <div className="flex flex-col max-h-[min(85vh,720px)]">
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
                    <p className="text-xs text-mw-text-secondary">
                        Choose which workflows the Companion can invoke in this workspace. Gmail, Calendar, and Google
                        Docs skills use the Google account linked under My Settings → Google Account → Google for
                        workflows.
                    </p>
                    <div className="rounded-lg border border-mw-border bg-mw-page p-3 space-y-2">
                        <p className={labelCls}>Interpretation model</p>
                        <p className="text-xs text-mw-text-secondary">
                            LM Studio model for routing / structured capability selection. Leave blank to use the
                            Companion Persona default.
                        </p>
                        <select
                            id="ws-interpretation-model"
                            className={inputCls}
                            value={interpretationModel}
                            onChange={e => setInterpretationModel(e.target.value)}
                            aria-label="Interpretation model"
                        >
                            <option value="">Default (Persona / env)</option>
                            {models?.local && models.local.length > 0 && (
                                <optgroup label="Local models">
                                    {models.local.map(m => (
                                        <option key={m} value={m}>
                                            {m}
                                        </option>
                                    ))}
                                </optgroup>
                            )}
                            {models?.external && models.external.length > 0 && (
                                <optgroup label="External models">
                                    {models.external.map(m => (
                                        <option key={m} value={m}>
                                            {m}
                                        </option>
                                    ))}
                                </optgroup>
                            )}
                        </select>
                    </div>
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
                    {!loading && workflows.length === 0 && !error && (
                        <p className="text-xs text-mw-text-secondary">
                            No workflow definitions yet. Create workflows under <strong>Build → Workflows</strong>.
                        </p>
                    )}
                    {renderSection('Workflows', regularWorkflows)}
                    {renderSection('Custom Skills', customSkills)}
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
                        disabled={saving || loading}
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
