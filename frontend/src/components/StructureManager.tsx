import React, { useEffect, useState } from 'react';
import { ApiClient } from '../api/client';
import { Structure, StructureCreate, StructureUpdate } from '../api/types';
import { Edit2, Plus, Trash2 } from 'lucide-react';
import { ManagerModal } from './ManagerModal';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

const EMPTY_FORM = { name: '', description: '', json_schema: '{\n  "type": "object",\n  "properties": {},\n  "required": []\n}' };

export const StructureManager: React.FC<Props> = ({ isOpen, onClose }) => {
    const [structures, setStructures] = useState<Structure[]>([]);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [form, setForm] = useState(EMPTY_FORM);

    const load = async () => {
        setIsLoading(true);
        try {
            const res = await ApiClient.getStructures();
            setStructures(res);
        } catch {
            setError('Failed to load structures.');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) { load(); setForm(EMPTY_FORM); setIsCreating(false); setEditingId(null); }
    }, [isOpen]);

    if (!isOpen) return null;

    const field = (key: keyof typeof EMPTY_FORM, v: string) => setForm(f => ({ ...f, [key]: v }));

    const handleEdit = (s: Structure) => {
        setIsCreating(false);
        setEditingId(s.id);
        setForm({ name: s.name, description: s.description ?? '', json_schema: s.json_schema });
    };

    const handleSave = async () => {
        if (!form.name.trim() || !form.json_schema.trim()) { setError('Name and JSON Schema are required.'); return; }
        try {
            JSON.parse(form.json_schema);
        } catch {
            setError('JSON Schema must be valid JSON.');
            return;
        }
        setError(null);
        try {
            if (editingId) {
                const upd: StructureUpdate = { name: form.name, description: form.description || undefined, json_schema: form.json_schema };
                await ApiClient.updateStructure(editingId, upd);
            } else {
                const crt: StructureCreate = { name: form.name, description: form.description || undefined, json_schema: form.json_schema };
                await ApiClient.createStructure(crt);
            }
            await load();
            setEditingId(null); setIsCreating(false); setForm(EMPTY_FORM);
        } catch (e: any) {
            setError(e.message ?? 'Failed to save.');
        }
    };

    const handleDelete = async (id: string) => {
        try { await ApiClient.deleteStructure(id); setDeletingId(null); setEditingId(null); setIsCreating(false); setForm(EMPTY_FORM); await load(); }
        catch { setError('Failed to delete structure.'); }
    };

    const inputCls = MANAGER_INPUT_CLS;
    const labelCls = MANAGER_LABEL_CLS;

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Manage Structures" maxWidth="4xl">
            <div className="flex flex-1 overflow-hidden">
                    <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                        <div className="p-3 border-b border-mw-border">
                            <button onClick={() => { setIsCreating(true); setEditingId(null); setForm(EMPTY_FORM); }}
                                className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors">
                                <Plus size={15} /> New Structure
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {isLoading && <div className="text-sm text-center text-mw-text-secondary p-4">Loading…</div>}
                            {structures.map(s => (
                                <div key={s.id}
                                    className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${editingId === s.id ? 'bg-mw-primary-muted border border-mw-primary' : 'hover:bg-mw-card border border-transparent'}`}
                                    onClick={() => handleEdit(s)}>
                                    <div className="truncate pr-2 min-w-0">
                                        <div className="text-sm font-medium text-mw-text-primary truncate">{s.name}</div>
                                        <div className="text-xs text-mw-text-secondary truncate">{s.description || 'JSON Schema for structured outputs'}</div>
                                    </div>
                                    <div className={`flex gap-1 shrink-0 ${deletingId === s.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                                        {deletingId !== s.id && (
                                            <button onClick={e => { e.stopPropagation(); setDeletingId(s.id); }} className="p-1 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded" title="Delete">
                                                <Trash2 size={14} />
                                            </button>
                                        )}
                                        {deletingId === s.id && (
                                            <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                                <button onClick={() => handleDelete(s.id)} className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium">Delete</button>
                                                <button onClick={() => setDeletingId(null)} className="px-2 py-0.5 text-xs bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium">Cancel</button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                        {(editingId || isCreating) ? (
                            <div className="space-y-4 max-w-xl">
                                <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                    {isCreating ? 'Create Structure' : 'Edit Structure'}
                                </h3>
                                {error && <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg">{error}</div>}

                                <div>
                                    <label className={labelCls}>Name *</label>
                                    <input value={form.name} onChange={e => field('name', e.target.value)} className={inputCls} placeholder="e.g. Joke Response" />
                                </div>
                                <div>
                                    <label className={labelCls}>Description</label>
                                    <input value={form.description} onChange={e => field('description', e.target.value)} className={inputCls} placeholder="Short summary of this structure" />
                                </div>
                                <div>
                                    <label className={labelCls}>JSON Schema *</label>
                                    <textarea value={form.json_schema} onChange={e => field('json_schema', e.target.value)} rows={12} className={`${inputCls} font-mono text-xs resize-none`} placeholder='{"type":"object","properties":{...},"required":[...]}' />
                                    <p className="text-[10px] text-mw-text-secondary mt-1">
                                        Must be valid JSON. Use a JSON Schema document to describe the expected output shape.
                                    </p>
                                </div>

                                <div className="pt-2 flex justify-end gap-2">
                                    <button onClick={() => { setIsCreating(false); setEditingId(null); setError(null); }} className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors">Cancel</button>
                                    <button onClick={handleSave} className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors">Save Structure</button>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary">
                                <Edit2 size={48} className="mb-4 text-mw-text-secondary opacity-50" />
                                <p>Select a structure or create a new one.</p>
                                <p className="text-xs mt-2">Structures store JSON Schema definitions for typed, structured outputs.</p>
                            </div>
                        )}
                    </div>
                </div>
        </ManagerModal>
    );
};
