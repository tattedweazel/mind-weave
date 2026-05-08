import React, { useEffect, useRef, useState } from 'react';
import { ApiClient } from '../api/client';
import { PersonaCreate, PersonaListItem, PersonaUpdate, ModelsResponse } from '../api/types';
import { Edit2, Plus, Trash2 } from 'lucide-react';
import { ManagerModal } from './ManagerModal';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';
import { ContextHelpModal } from './ContextHelpModal';
import { PersonaSuppressThinkingHelpContent } from './personaSuppressThinkingHelpContent';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

const EMPTY_FORM = {
    name: '',
    description: '',
    system_prompt: '',
    default_model: '',
    creativity: '0.2',
    suppress_lm_thinking: false,
};

export const PersonaManager: React.FC<Props> = ({ isOpen, onClose }) => {
    const [personas, setPersonas] = useState<PersonaListItem[]>([]);
    const [models, setModels] = useState<ModelsResponse | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [isPersonaDetailLoading, setIsPersonaDetailLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const personaDetailLoadSeq = useRef(0);

    const load = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const [pRes, mRes] = await Promise.all([
                ApiClient.getPersonas(),
                ApiClient.getModels().catch(() => null)
            ]);
            setPersonas(pRes);
            if (mRes) {
                setModels(mRes);
                if (mRes.lm_studio_list_error) {
                    setError(mRes.lm_studio_list_error);
                }
            }
        } catch {
            setError('Failed to load personas.');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            personaDetailLoadSeq.current += 1;
            load();
            setForm(EMPTY_FORM);
            setIsCreating(false);
            setEditingId(null);
            setIsPersonaDetailLoading(false);
        }
    }, [isOpen]);

    if (!isOpen) return null;

    type StringFormKey = Exclude<keyof typeof EMPTY_FORM, 'suppress_lm_thinking'>;
    const field = (key: StringFormKey, v: string) => setForm(f => ({ ...f, [key]: v }));

    const handleEdit = (p: PersonaListItem) => {
        setIsCreating(false);
        setError(null);
        personaDetailLoadSeq.current += 1;
        const seq = personaDetailLoadSeq.current;
        setEditingId(p.id);
        setIsPersonaDetailLoading(true);
        setForm({
            name: p.name,
            description: p.description,
            system_prompt: '',
            default_model: p.default_model ?? '',
            creativity: p.creativity?.toString() ?? '0.2',
            suppress_lm_thinking: p.suppress_lm_thinking ?? false,
        });
        void (async () => {
            try {
                const full = await ApiClient.getPersona(p.id);
                if (seq !== personaDetailLoadSeq.current) return;
                setForm({
                    name: full.name,
                    description: full.description,
                    system_prompt: full.system_prompt ?? '',
                    default_model: full.default_model ?? '',
                    creativity: full.creativity?.toString() ?? '0.2',
                    suppress_lm_thinking: full.suppress_lm_thinking ?? false,
                });
            } catch {
                if (seq !== personaDetailLoadSeq.current) return;
                setError('Failed to load persona.');
            } finally {
                if (seq === personaDetailLoadSeq.current) setIsPersonaDetailLoading(false);
            }
        })();
    };

    const handleSave = async () => {
        if (!form.name.trim() || !form.system_prompt.trim()) { setError('Name and System Prompt are required.'); return; }
        setError(null);
        try {
            if (editingId) {
                const upd: PersonaUpdate = {
                    name: form.name,
                    description: form.description,
                    system_prompt: form.system_prompt,
                    default_model: form.default_model || null,
                    creativity: parseFloat(form.creativity) || 0.2,
                    suppress_lm_thinking: form.suppress_lm_thinking,
                };
                await ApiClient.updatePersona(editingId, upd);
            } else {
                const crt: PersonaCreate = {
                    name: form.name,
                    description: form.description,
                    system_prompt: form.system_prompt,
                    default_model: form.default_model || null,
                    creativity: parseFloat(form.creativity) || 0.2,
                    suppress_lm_thinking: form.suppress_lm_thinking,
                };
                await ApiClient.createPersona(crt);
            }
            await load();
            personaDetailLoadSeq.current += 1;
            setEditingId(null); setIsCreating(false); setForm(EMPTY_FORM); setIsPersonaDetailLoading(false);
        } catch (e: any) {
            setError(e.message ?? 'Failed to save.');
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await ApiClient.deletePersona(id);
            personaDetailLoadSeq.current += 1;
            setDeletingId(null);
            setEditingId(null);
            setIsCreating(false);
            setForm(EMPTY_FORM);
            setIsPersonaDetailLoading(false);
            await load();
        }
        catch { setError('Failed to delete persona.'); }
    };

    const inputCls = MANAGER_INPUT_CLS;
    const labelCls = MANAGER_LABEL_CLS;

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Manage Personas" maxWidth="4xl">
            <div className="flex flex-1 overflow-hidden">
                    {/* Left list */}
                    <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                        <div className="p-3 border-b border-mw-border">
                            <button onClick={() => {
                                personaDetailLoadSeq.current += 1;
                                setIsCreating(true);
                                setEditingId(null);
                                setForm(EMPTY_FORM);
                                setIsPersonaDetailLoading(false);
                                setError(null);
                            }}
                                className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors">
                                <Plus size={15} /> New Persona
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {isLoading && <div className="text-sm text-center text-mw-text-secondary p-4">Loading…</div>}
                            {personas.map(p => (
                                <div key={p.id}
                                    className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${editingId === p.id ? 'bg-mw-primary-muted border border-mw-primary' : 'hover:bg-mw-card border border-transparent'}`}
                                    onClick={() => handleEdit(p)}>
                                    <div className="truncate pr-2 min-w-0">
                                        <div className="text-sm font-medium text-mw-text-primary truncate flex items-center gap-1.5">
                                            {p.name}
                                            {p.type === 'system' && <span className="text-xs bg-mw-card-alt text-mw-text-secondary px-1.5 py-0.5 rounded">System</span>}
                                        </div>
                                        <div className="text-xs text-mw-text-secondary truncate">{p.description}</div>
                                    </div>
                                    <div className={`flex gap-1 shrink-0 ${deletingId === p.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                                        {!p.is_default && deletingId !== p.id && (
                                            <button onClick={e => { e.stopPropagation(); setDeletingId(p.id); }} className="p-1 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded" title="Delete">
                                                <Trash2 size={14} />
                                            </button>
                                        )}
                                        {deletingId === p.id && (
                                            <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                                <button onClick={() => handleDelete(p.id)} className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium">Delete</button>
                                                <button onClick={() => setDeletingId(null)} className="px-2 py-0.5 text-xs bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium">Cancel</button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Right form */}
                    <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                        {(editingId || isCreating) ? (
                            <div className="space-y-4 max-w-xl">
                                <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                    {isCreating ? 'Create Persona' : 'Edit Persona'}
                                </h3>
                                {isPersonaDetailLoading && (
                                    <div className="text-sm text-mw-text-secondary">Loading persona…</div>
                                )}
                                {error && <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg">{error}</div>}

                                <div>
                                    <label className={labelCls}>Name *</label>
                                    <input value={form.name} onChange={e => field('name', e.target.value)} className={inputCls} placeholder="e.g. Code Reviewer" disabled={isPersonaDetailLoading} />
                                </div>
                                <div>
                                    <label className={labelCls}>Description</label>
                                    <input value={form.description} onChange={e => field('description', e.target.value)} className={inputCls} placeholder="Short summary of this persona's purpose" disabled={isPersonaDetailLoading} />
                                </div>
                                <div>
                                    <label className={labelCls}>System Prompt *</label>
                                    <textarea value={form.system_prompt} onChange={e => field('system_prompt', e.target.value)} rows={6} className={`${inputCls} resize-y min-h-[9rem]`} placeholder="You are a …" disabled={isPersonaDetailLoading} />
                                </div>
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between">
                                        <label className={labelCls}>Creativity</label>
                                        <span className="text-xs font-mono text-mw-text-secondary">{parseFloat(form.creativity).toFixed(2)}</span>
                                    </div>
                                    <input 
                                        type="range" 
                                        min="0.1" 
                                        max="1.0" 
                                        step="0.1" 
                                        value={form.creativity} 
                                        onChange={e => field('creativity', e.target.value)} 
                                        className="w-full accent-mw-primary" 
                                        disabled={isPersonaDetailLoading}
                                    />
                                    <div className="flex justify-between text-[10px] text-mw-text-secondary mt-1">
                                        <span>Precise</span>
                                        <span>Balanced</span>
                                        <span>Creative</span>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between gap-3 py-0.5">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                        <span className={`${labelCls} mb-0`}>Suppress extended thinking</span>
                                        <ContextHelpModal title="Suppress extended thinking (LM Studio)" triggerLabel="About suppressing extended thinking">
                                            <PersonaSuppressThinkingHelpContent />
                                        </ContextHelpModal>
                                    </div>
                                    <input
                                        type="checkbox"
                                        className="rounded border-mw-border shrink-0 accent-mw-primary"
                                        checked={form.suppress_lm_thinking}
                                        onChange={e => setForm(f => ({ ...f, suppress_lm_thinking: e.target.checked }))}
                                        disabled={isPersonaDetailLoading}
                                        aria-label="Suppress extended thinking for LM Studio"
                                    />
                                </div>
                                <div>
                                    <label className={labelCls}>Default Model <span className="text-mw-text-secondary opacity-80 font-normal">(optional)</span></label>
                                    <select value={form.default_model} onChange={e => field('default_model', e.target.value)} className={inputCls} disabled={isPersonaDetailLoading}>
                                        <option value="">None (Use System Default)</option>
                                        {models?.local && models.local.length > 0 && (
                                            <optgroup label="Local Models">
                                                {models.local.map(m => <option key={m} value={m}>{m}</option>)}
                                            </optgroup>
                                        )}
                                        {models?.external && models.external.length > 0 && (
                                            <optgroup label="External Models">
                                                {models.external.map(m => <option key={m} value={m}>{m}</option>)}
                                            </optgroup>
                                        )}
                                    </select>
                                </div>

                                <div className="pt-2 flex justify-end gap-2">
                                    <button onClick={() => {
                                        personaDetailLoadSeq.current += 1;
                                        setIsCreating(false);
                                        setEditingId(null);
                                        setError(null);
                                        setIsPersonaDetailLoading(false);
                                    }} className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors">Cancel</button>
                                    <button onClick={handleSave} disabled={isPersonaDetailLoading} className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none">Save Persona</button>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary">
                                <Edit2 size={48} className="mb-4 text-mw-text-secondary opacity-50" />
                                <p>Select a persona or create a new one.</p>
                            </div>
                        )}
                    </div>
                </div>
        </ManagerModal>
    );
};
