/**
 * Workspace: workflows, interpretation model, default Google connection for skills.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { ApiClient } from '../api/client';
import type {
    GoogleWorkflowConnection,
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
    const [googleConnections, setGoogleConnections] = useState<GoogleWorkflowConnection[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [enabledIds, setEnabledIds] = useState<Set<string>>(new Set());
    const [interpretationModel, setInterpretationModel] = useState('');
    const [googleConnId, setGoogleConnId] = useState('');

    useEffect(() => {
        if (!isOpen) {
            return;
        }
        setEnabledIds(new Set(workspace.enabled_workflow_ids ?? []));
        setInterpretationModel((workspace.interpretation_model ?? '').trim());
        setGoogleConnId(workspace.default_google_workflow_connection_id ?? '');
        setError(null);
        setLoading(true);
        Promise.all([
            ApiClient.getWorkflows(),
            ApiClient.getModels().catch(() => ({ local: [] as string[], external: [] as string[] }) as ModelsResponse),
            ApiClient.getGoogleWorkflowConnections().catch(() => [] as GoogleWorkflowConnection[]),
        ])
            .then(([wfs, mdl, gwc]) => {
                setWorkflows(wfs);
                setModels(mdl);
                if (mdl.lm_studio_list_error) {
                    setError(mdl.lm_studio_list_error);
                }
                setGoogleConnections(gwc);
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
        const gNext = googleConnId.trim() || null;
        const gPrev = workspace.default_google_workflow_connection_id ?? null;
        if (gNext !== gPrev) {
            patch.default_google_workflow_connection_id = gNext;
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

    if (!isOpen) {
        return null;
    }

    const labelCls = MANAGER_LABEL_CLS;
    const inputCls =
        'w-full rounded-lg border border-mw-border bg-mw-page px-3 py-2 text-sm text-mw-text-primary focus:outline-none focus:ring-2 focus:ring-mw-primary';

    const renderSection = (title: string, items: WorkflowDefinitionListItem[]) => {
        if (items.length === 0) {
            return null;
        }
        return (
            <div>
                <span className={labelCls}>{title}</span>
                <ul className="mt-2 space-y-2 border border-mw-border rounded-lg p-3 bg-mw-page">
                    {items.map(wf => (
                        <li key={wf.id} className="flex items-start gap-2">
                            <input
                                id={`ws-wf-${wf.id}`}
                                type="checkbox"
                                className="rounded border-mw-border mt-0.5"
                                checked={enabledIds.has(wf.id)}
                                onChange={() => toggleId(wf.id)}
                            />
                            <label htmlFor={`ws-wf-${wf.id}`} className="cursor-pointer flex-1 min-w-0">
                                <span className="text-mw-text-primary text-sm font-medium">{wf.name}</span>
                                {wf.description ? (
                                    <span className="block text-xs text-mw-text-secondary">{wf.description}</span>
                                ) : null}
                                <span className="block font-mono text-[10px] text-mw-text-secondary">{wf.id}</span>
                            </label>
                        </li>
                    ))}
                </ul>
            </div>
        );
    };

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Workspace settings" maxWidth="2xl">
            <div className="flex flex-col h-full min-h-0 overflow-hidden">
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 text-sm text-mw-text-primary">
                    <p className="text-mw-text-secondary text-xs">
                        Choose which <strong className="text-mw-text-primary">workflows</strong> and{' '}
                        <strong className="text-mw-text-primary">Custom Skills</strong> are available in this Workspace.
                        Your Companion can only use skills that are enabled here and also enabled under{' '}
                        <strong>Customize</strong>.
                    </p>
                    <div className="rounded-lg border border-mw-border bg-mw-page p-3 space-y-2">
                        <p className={labelCls}>Planning / routing model</p>
                        <p className="text-xs text-mw-text-secondary">
                            LM Studio model for structured interpretation (which workflows to run and Start input
                            bindings). Chat reply wording still uses the Companion Persona model.
                        </p>
                        <select
                            id="ws-interpretation-model"
                            className={inputCls}
                            value={interpretationModel}
                            onChange={e => setInterpretationModel(e.target.value)}
                            aria-label="Planning model"
                        >
                            <option value="">Default (Companion Persona)</option>
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
                    <div className="rounded-lg border border-mw-border bg-mw-page p-3 space-y-2">
                        <p className={labelCls}>Default Google connection (Gmail / Calendar skills)</p>
                        <p className="text-xs text-mw-text-secondary">
                            When a workflow&apos;s Gmail or Calendar skill node has no connection selected in Build,
                            Workspace runs use this account (must be linked under My Settings). Execution still uses
                            your user id.
                        </p>
                        <select
                            id="ws-default-google"
                            className={inputCls}
                            value={googleConnId}
                            onChange={e => setGoogleConnId(e.target.value)}
                            aria-label="Default Google workflow connection"
                        >
                            <option value="">None (use only node inspector selection)</option>
                            {googleConnections.map(c => (
                                <option key={c.id} value={c.id}>
                                    {(c.label || c.google_email || c.id).slice(0, 80)}
                                </option>
                            ))}
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
