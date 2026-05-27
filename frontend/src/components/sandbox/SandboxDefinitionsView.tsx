/**
 * Sandbox Definitions tab — card gallery with category filters and slide-over CRUD editor.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
    Box,
    Layers,
    Loader2,
    MapPin,
    Plus,
    Sparkles,
    Trash2,
    Users,
    X,
    type LucideIcon,
} from 'lucide-react';

import { ApiClient } from '../../api/client';
import type {
    CreatureDefinitionRead,
    FixtureDefinitionRead,
    ItemDefinitionRead,
    RegionDefinitionRead,
    TerrainDefinitionRead,
    WorkflowDefinitionListItem,
    WorkflowProject,
} from '../../api/types';
import { DEFAULT_REGION_TRIGGER, SANDBOX_FACING_VALUES, type SandboxFacing } from '../../domain/sandbox/types';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from '../managerShellStyles';
import { SandboxColorPicker } from './SandboxColorPicker';
import { SandboxRegionInspectorSection } from './SandboxRegionInspectorSection';
import { SandboxWorkflowSelect } from './SandboxWorkflowSelect';
import { CustomMetadataEditor, validateCustomMetadata } from './CustomMetadataEditor';

export type DefinitionCategory = 'items' | 'terrain' | 'fixtures' | 'creatures' | 'regions';

const CATEGORY_META: Record<DefinitionCategory, { label: string; icon: LucideIcon }> = {
    items: { label: 'Items', icon: Box },
    terrain: { label: 'Terrain', icon: Layers },
    fixtures: { label: 'Fixtures', icon: Sparkles },
    creatures: { label: 'Creatures', icon: Users },
    regions: { label: 'Regions', icon: MapPin },
};

type AnyDefinition =
    | ItemDefinitionRead
    | TerrainDefinitionRead
    | FixtureDefinitionRead
    | CreatureDefinitionRead
    | RegionDefinitionRead;

export interface SandboxDefinitionsViewProps {
    workflows: WorkflowDefinitionListItem[];
    workflowProjects: WorkflowProject[];
    sharedProjectId: string | null;
    sandboxFavoriteColors?: string[];
    /** Notify parent to refresh shared definition lists (cell action pickers). */
    onDefinitionsChange?: () => void | Promise<void>;
}

function definitionCardColor(def: AnyDefinition): string | null {
    if ('default_color' in def && def.default_color) return def.default_color;
    if ('color' in def && def.color) return def.color;
    return null;
}

function itemDefinitionCardSubtitle(def: ItemDefinitionRead): string {
    const keyCount = Object.keys(def.custom_metadata ?? {}).length;
    const metaPart = keyCount > 0 ? `Metadata · ${keyCount} key${keyCount === 1 ? '' : 's'}` : null;
    const pickPart = def.pickable ? 'Pickable' : 'Not pickable';
    return metaPart ? `${pickPart} · ${metaPart}` : pickPart;
}

function definitionCardSubtitle(def: AnyDefinition): string {
    if ('custom_metadata' in def) {
        return itemDefinitionCardSubtitle(def as ItemDefinitionRead);
    }
    if ('workflow_id' in def && def.workflow_id) {
        return `Workflow · ${def.workflow_id.slice(0, 8)}…`;
    }
    if ('shape' in def && def.shape) return `Shape · ${def.shape}`;
    if ('pickable' in def) return def.pickable ? 'Pickable' : 'Not pickable';
    return def.label;
}

export const SandboxDefinitionsView: React.FC<SandboxDefinitionsViewProps> = ({
    workflows,
    workflowProjects,
    sharedProjectId,
    sandboxFavoriteColors = [],
    onDefinitionsChange,
}) => {
    const [category, setCategory] = useState<DefinitionCategory>('items');
    const [definitions, setDefinitions] = useState<AnyDefinition[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editorOpen, setEditorOpen] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const [itemForm, setItemForm] = useState({
        name: '',
        label: '',
        custom_metadata: {} as Record<string, unknown>,
        default_color: '',
        shape: 'circle' as 'circle' | 'square' | 'rect',
        pickable: true,
    });
    const [terrainForm, setTerrainForm] = useState({
        name: '',
        label: '',
        default_color: '',
        shape: 'rect' as 'circle' | 'square' | 'rect',
    });
    const [fixtureForm, setFixtureForm] = useState({
        name: '',
        label: '',
        workflow_id: '',
        color: '',
    });
    const [creatureForm, setCreatureForm] = useState({
        name: '',
        label: '',
        workflow_id: '',
        default_color: '#3B82F6',
        default_facing: 'N' as SandboxFacing,
    });
    const [regionForm, setRegionForm] = useState({
        name: '',
        label: '',
        color: '#3B82F6',
        trigger: { ...DEFAULT_REGION_TRIGGER },
    });

    const loadDefinitions = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            let rows: AnyDefinition[];
            switch (category) {
                case 'items':
                    rows = await ApiClient.listItemDefinitions();
                    break;
                case 'terrain':
                    rows = await ApiClient.listTerrainDefinitions();
                    break;
                case 'fixtures':
                    rows = await ApiClient.listFixtureDefinitions();
                    break;
                case 'creatures':
                    rows = await ApiClient.listCreatureDefinitions();
                    break;
                case 'regions':
                    rows = await ApiClient.listRegionDefinitions();
                    break;
            }
            setDefinitions([...rows].sort((a, b) => a.name.localeCompare(b.name)));
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to load definitions.');
        } finally {
            setLoading(false);
        }
    }, [category]);

    useEffect(() => {
        void loadDefinitions();
    }, [loadDefinitions]);

    const resetForms = () => {
        setItemForm({
            name: '',
            label: '',
            custom_metadata: {},
            default_color: '',
            shape: 'circle',
            pickable: true,
        });
        setTerrainForm({ name: '', label: '', default_color: '', shape: 'rect' });
        setFixtureForm({ name: '', label: '', workflow_id: '', color: '' });
        setCreatureForm({
            name: '',
            label: '',
            workflow_id: '',
            default_color: '#3B82F6',
            default_facing: 'N',
        });
        setRegionForm({ name: '', label: '', color: '#3B82F6', trigger: { ...DEFAULT_REGION_TRIGGER } });
    };

    const openCreate = () => {
        resetForms();
        setIsCreating(true);
        setEditingId(null);
        setEditorOpen(true);
        setError(null);
    };

    const openEdit = (def: AnyDefinition) => {
        setIsCreating(false);
        setEditingId(def.id);
        setEditorOpen(true);
        setError(null);
        if (category === 'items') {
            const d = def as ItemDefinitionRead;
            setItemForm({
                name: d.name,
                label: d.label,
                custom_metadata: { ...(d.custom_metadata ?? {}) },
                default_color: d.default_color ?? '',
                shape: d.shape,
                pickable: d.pickable,
            });
        } else if (category === 'terrain') {
            const d = def as TerrainDefinitionRead;
            setTerrainForm({
                name: d.name,
                label: d.label,
                default_color: d.default_color ?? '',
                shape: d.shape,
            });
        } else if (category === 'fixtures') {
            const d = def as FixtureDefinitionRead;
            setFixtureForm({
                name: d.name,
                label: d.label,
                workflow_id: d.workflow_id,
                color: d.color ?? '',
            });
        } else if (category === 'creatures') {
            const d = def as CreatureDefinitionRead;
            setCreatureForm({
                name: d.name,
                label: d.label,
                workflow_id: d.workflow_id,
                default_color: d.default_color,
                default_facing: d.default_facing,
            });
        } else {
            const d = def as RegionDefinitionRead;
            setRegionForm({
                name: d.name,
                label: d.label,
                color: d.color,
                trigger: d.trigger ?? { ...DEFAULT_REGION_TRIGGER },
            });
        }
    };

    const closeEditor = () => {
        setEditorOpen(false);
        setEditingId(null);
        setIsCreating(false);
        setDeletingId(null);
    };

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            if (category === 'items') {
                if (!itemForm.name.trim() || !itemForm.label.trim()) {
                    setError('Name and label are required.');
                    return;
                }
                const metaError = validateCustomMetadata(itemForm.custom_metadata);
                if (metaError) {
                    setError(metaError);
                    return;
                }
                const payload = {
                    name: itemForm.name.trim(),
                    label: itemForm.label.trim(),
                    custom_metadata: itemForm.custom_metadata,
                    default_color: itemForm.default_color.trim() || null,
                    shape: itemForm.shape,
                    pickable: itemForm.pickable,
                };
                if (editingId) await ApiClient.updateItemDefinition(editingId, payload);
                else await ApiClient.createItemDefinition(payload);
            } else if (category === 'terrain') {
                if (!terrainForm.name.trim() || !terrainForm.label.trim()) {
                    setError('Name and label are required.');
                    return;
                }
                const payload = {
                    name: terrainForm.name.trim(),
                    label: terrainForm.label.trim(),
                    default_color: terrainForm.default_color.trim() || null,
                    shape: terrainForm.shape,
                };
                if (editingId) await ApiClient.updateTerrainDefinition(editingId, payload);
                else await ApiClient.createTerrainDefinition(payload);
            } else if (category === 'fixtures') {
                if (!fixtureForm.name.trim() || !fixtureForm.label.trim() || !fixtureForm.workflow_id) {
                    setError('Name, label, and workflow are required.');
                    return;
                }
                const payload = {
                    name: fixtureForm.name.trim(),
                    label: fixtureForm.label.trim(),
                    workflow_id: fixtureForm.workflow_id,
                    color: fixtureForm.color.trim() || null,
                };
                if (editingId) await ApiClient.updateFixtureDefinition(editingId, payload);
                else await ApiClient.createFixtureDefinition(payload);
            } else if (category === 'creatures') {
                if (!creatureForm.name.trim() || !creatureForm.label.trim() || !creatureForm.workflow_id) {
                    setError('Name, label, and workflow are required.');
                    return;
                }
                const payload = {
                    name: creatureForm.name.trim(),
                    label: creatureForm.label.trim(),
                    workflow_id: creatureForm.workflow_id,
                    default_color: creatureForm.default_color,
                    default_facing: creatureForm.default_facing,
                    default_inventory: [],
                };
                if (editingId) await ApiClient.updateCreatureDefinition(editingId, payload);
                else await ApiClient.createCreatureDefinition(payload);
            } else {
                if (!regionForm.name.trim() || !regionForm.label.trim() || !regionForm.color.trim()) {
                    setError('Name, label, and color are required.');
                    return;
                }
                const payload = {
                    name: regionForm.name.trim(),
                    label: regionForm.label.trim(),
                    color: regionForm.color.trim(),
                    trigger: regionForm.trigger,
                };
                if (editingId) await ApiClient.updateRegionDefinition(editingId, payload);
                else await ApiClient.createRegionDefinition(payload);
            }
            await loadDefinitions();
            await onDefinitionsChange?.();
            closeEditor();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to save definition.');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: string) => {
        setError(null);
        try {
            switch (category) {
                case 'items':
                    await ApiClient.deleteItemDefinition(id);
                    break;
                case 'terrain':
                    await ApiClient.deleteTerrainDefinition(id);
                    break;
                case 'fixtures':
                    await ApiClient.deleteFixtureDefinition(id);
                    break;
                case 'creatures':
                    await ApiClient.deleteCreatureDefinition(id);
                    break;
                case 'regions':
                    await ApiClient.deleteRegionDefinition(id);
                    break;
            }
            setDeletingId(null);
            closeEditor();
            await loadDefinitions();
            await onDefinitionsChange?.();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to delete definition.');
        }
    };

    const editorTitle = isCreating
        ? `New ${CATEGORY_META[category].label.slice(0, -1)}`
        : `Edit ${CATEGORY_META[category].label.slice(0, -1)}`;

    const workflowSelect = (
        value: string,
        onChange: (id: string) => void,
        id: string,
    ) => (
        <div>
            <label htmlFor={id} className={MANAGER_LABEL_CLS}>
                Workflow *
            </label>
            <SandboxWorkflowSelect
                id={id}
                value={value}
                onChange={onChange}
                workflows={workflows}
                workflowProjects={workflowProjects}
                sharedProjectId={sharedProjectId}
                emptyOptionLabel="Select workflow…"
                className={MANAGER_INPUT_CLS}
                showEligibilityHint
            />
        </div>
    );

    const renderEditorFields = () => {
        if (category === 'items') {
            return (
                <>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Name *</label>
                        <input
                            value={itemForm.name}
                            onChange={e => setItemForm(f => ({ ...f, name: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                            placeholder="unique_key"
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Label *</label>
                        <input
                            value={itemForm.label}
                            onChange={e => setItemForm(f => ({ ...f, label: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                            placeholder="Display label"
                        />
                    </div>
                    <CustomMetadataEditor
                        value={itemForm.custom_metadata}
                        onChange={custom_metadata => setItemForm(f => ({ ...f, custom_metadata }))}
                    />
                    <div>
                        <span className={MANAGER_LABEL_CLS}>Default color</span>
                        <SandboxColorPicker
                            value={itemForm.default_color || '#3B82F6'}
                            favoriteColors={sandboxFavoriteColors}
                            onChange={c => setItemForm(f => ({ ...f, default_color: c }))}
                            onConfirm={c => setItemForm(f => ({ ...f, default_color: c }))}
                            showConfirmButton={false}
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Shape</label>
                        <select
                            value={itemForm.shape}
                            onChange={e =>
                                setItemForm(f => ({
                                    ...f,
                                    shape: e.target.value as 'circle' | 'square' | 'rect',
                                }))
                            }
                            className={MANAGER_INPUT_CLS}
                        >
                            <option value="circle">Circle</option>
                            <option value="square">Square</option>
                            <option value="rect">Rect</option>
                        </select>
                    </div>
                    <label className="flex items-center gap-2 text-sm text-mw-text-primary">
                        <input
                            type="checkbox"
                            checked={itemForm.pickable}
                            onChange={e => setItemForm(f => ({ ...f, pickable: e.target.checked }))}
                            className="rounded border-mw-border"
                        />
                        Pickable
                    </label>
                </>
            );
        }
        if (category === 'terrain') {
            return (
                <>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Name *</label>
                        <input
                            value={terrainForm.name}
                            onChange={e => setTerrainForm(f => ({ ...f, name: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Label *</label>
                        <input
                            value={terrainForm.label}
                            onChange={e => setTerrainForm(f => ({ ...f, label: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    <div>
                        <span className={MANAGER_LABEL_CLS}>Default color</span>
                        <SandboxColorPicker
                            value={terrainForm.default_color || '#64748B'}
                            favoriteColors={sandboxFavoriteColors}
                            onChange={c => setTerrainForm(f => ({ ...f, default_color: c }))}
                            onConfirm={c => setTerrainForm(f => ({ ...f, default_color: c }))}
                            showConfirmButton={false}
                        />
                    </div>
                </>
            );
        }
        if (category === 'fixtures') {
            return (
                <>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Name *</label>
                        <input
                            value={fixtureForm.name}
                            onChange={e => setFixtureForm(f => ({ ...f, name: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Label *</label>
                        <input
                            value={fixtureForm.label}
                            onChange={e => setFixtureForm(f => ({ ...f, label: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    {workflowSelect(fixtureForm.workflow_id, id => setFixtureForm(f => ({ ...f, workflow_id: id })), 'fixture-workflow')}
                    <div>
                        <span className={MANAGER_LABEL_CLS}>Color</span>
                        <SandboxColorPicker
                            value={fixtureForm.color || '#8B5CF6'}
                            favoriteColors={sandboxFavoriteColors}
                            onChange={c => setFixtureForm(f => ({ ...f, color: c }))}
                            onConfirm={c => setFixtureForm(f => ({ ...f, color: c }))}
                            showConfirmButton={false}
                        />
                    </div>
                </>
            );
        }
        if (category === 'creatures') {
            return (
                <>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Name *</label>
                        <input
                            value={creatureForm.name}
                            onChange={e => setCreatureForm(f => ({ ...f, name: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Label *</label>
                        <input
                            value={creatureForm.label}
                            onChange={e => setCreatureForm(f => ({ ...f, label: e.target.value }))}
                            className={MANAGER_INPUT_CLS}
                        />
                    </div>
                    {workflowSelect(
                        creatureForm.workflow_id,
                        id => setCreatureForm(f => ({ ...f, workflow_id: id })),
                        'creature-workflow',
                    )}
                    <div>
                        <span className={MANAGER_LABEL_CLS}>Default color *</span>
                        <SandboxColorPicker
                            value={creatureForm.default_color}
                            favoriteColors={sandboxFavoriteColors}
                            onChange={c => setCreatureForm(f => ({ ...f, default_color: c }))}
                            onConfirm={c => setCreatureForm(f => ({ ...f, default_color: c }))}
                            showConfirmButton={false}
                        />
                    </div>
                    <div>
                        <label className={MANAGER_LABEL_CLS}>Default facing</label>
                        <select
                            value={creatureForm.default_facing}
                            onChange={e =>
                                setCreatureForm(f => ({
                                    ...f,
                                    default_facing: e.target.value as SandboxFacing,
                                }))
                            }
                            className={MANAGER_INPUT_CLS}
                        >
                            {SANDBOX_FACING_VALUES.map(f => (
                                <option key={f} value={f}>
                                    {f}
                                </option>
                            ))}
                        </select>
                    </div>
                </>
            );
        }
        return (
            <>
                <div>
                    <label className={MANAGER_LABEL_CLS}>Name *</label>
                    <input
                        value={regionForm.name}
                        onChange={e => setRegionForm(f => ({ ...f, name: e.target.value }))}
                        className={MANAGER_INPUT_CLS}
                    />
                </div>
                <div>
                    <label className={MANAGER_LABEL_CLS}>Label *</label>
                    <input
                        value={regionForm.label}
                        onChange={e => setRegionForm(f => ({ ...f, label: e.target.value }))}
                        className={MANAGER_INPUT_CLS}
                    />
                </div>
                <div>
                    <span className={MANAGER_LABEL_CLS}>Color *</span>
                    <SandboxColorPicker
                        value={regionForm.color}
                        favoriteColors={sandboxFavoriteColors}
                        onChange={c => setRegionForm(f => ({ ...f, color: c }))}
                        onConfirm={c => setRegionForm(f => ({ ...f, color: c }))}
                        showConfirmButton={false}
                    />
                </div>
                <SandboxRegionInspectorSection
                    variant="definition"
                    item={{
                        id: editingId ?? 'new-region',
                        type: 'region',
                        position: { x: 0, y: 0 },
                        color: regionForm.color,
                        label: regionForm.label,
                        trigger: regionForm.trigger,
                    }}
                    readOnly={false}
                    favoriteColors={sandboxFavoriteColors}
                    workflows={workflows}
                    workflowProjects={workflowProjects}
                    sharedProjectId={sharedProjectId}
                    onItemChange={(_id, patch) => {
                        if (patch.trigger) {
                            setRegionForm(f => ({ ...f, trigger: patch.trigger! }));
                        }
                    }}
                />
            </>
        );
    };

    return (
        <div className="flex flex-col h-full min-h-0 bg-mw-page">
            <div className="shrink-0 px-4 py-3 border-b border-mw-border bg-mw-card flex flex-wrap items-center gap-3">
                <div
                    role="tablist"
                    aria-label="Definition category"
                    className="flex rounded-lg border border-mw-border bg-mw-page p-0.5 gap-0.5"
                >
                    {(Object.keys(CATEGORY_META) as DefinitionCategory[]).map(key => {
                        const Icon = CATEGORY_META[key].icon;
                        const active = category === key;
                        return (
                            <button
                                key={key}
                                type="button"
                                role="tab"
                                aria-selected={active}
                                onClick={() => {
                                    setCategory(key);
                                    closeEditor();
                                }}
                                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                    active
                                        ? 'bg-mw-primary-muted text-mw-primary'
                                        : 'text-mw-text-secondary hover:text-mw-text-primary hover:bg-mw-card'
                                }`}
                            >
                                <Icon size={14} />
                                {CATEGORY_META[key].label}
                            </button>
                        );
                    })}
                </div>
                <button
                    type="button"
                    onClick={openCreate}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-mw-primary text-white text-xs font-medium hover:opacity-90"
                >
                    <Plus size={14} />
                    New
                </button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4">
                {error && !editorOpen ? (
                    <div className="mb-4 text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg">
                        {error}
                    </div>
                ) : null}
                {loading ? (
                    <div className="flex items-center justify-center gap-2 py-16 text-mw-text-secondary">
                        <Loader2 className="animate-spin" size={20} />
                        Loading definitions…
                    </div>
                ) : definitions.length === 0 ? (
                    <div className="text-center py-16 text-mw-text-secondary text-sm">
                        No {CATEGORY_META[category].label.toLowerCase()} yet. Create one to get started.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                        {definitions.map(def => {
                            const swatch = definitionCardColor(def);
                            return (
                                <button
                                    key={def.id}
                                    type="button"
                                    onClick={() => openEdit(def)}
                                    className="group text-left mw-card rounded-xl border border-mw-border bg-mw-card p-4 hover:border-mw-primary hover:shadow-md transition-all duration-150"
                                >
                                    <div className="flex items-start gap-3">
                                        <div
                                            className="shrink-0 w-10 h-10 rounded-lg border border-mw-border shadow-inner"
                                            style={{
                                                backgroundColor: swatch ?? 'var(--mw-card-alt, #e2e8f0)',
                                            }}
                                        />
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-1.5">
                                                <span className="text-sm font-semibold text-mw-text-primary truncate">
                                                    {def.name}
                                                </span>
                                                {def.is_system ? (
                                                    <span className="shrink-0 text-[10px] uppercase tracking-wide bg-mw-card-alt text-mw-text-secondary px-1.5 py-0.5 rounded">
                                                        System
                                                    </span>
                                                ) : null}
                                            </div>
                                            <p className="text-xs text-mw-text-secondary truncate mt-0.5">{def.label}</p>
                                            <p className="text-[10px] text-mw-text-secondary mt-1 truncate">
                                                {definitionCardSubtitle(def)}
                                            </p>
                                        </div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                )}
            </div>

            {editorOpen ? (
                <>
                    <button
                        type="button"
                        className="fixed inset-0 z-[60] bg-black/40 dark:bg-black/55 backdrop-blur-sm border-0 p-0 cursor-default"
                        aria-label="Close editor"
                        onClick={closeEditor}
                    />
                    <aside
                        className="fixed inset-y-0 right-0 z-[65] w-full max-w-md flex flex-col shadow-2xl border-l border-slate-200/80 dark:border-slate-600/80 bg-white dark:bg-slate-900 overflow-hidden"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="sandbox-def-editor-title"
                    >
                        <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 px-5 py-4 text-white shrink-0">
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-widest text-indigo-300/90">
                                        {CATEGORY_META[category].label}
                                    </p>
                                    <h2 id="sandbox-def-editor-title" className="text-lg font-semibold">
                                        {editorTitle}
                                    </h2>
                                </div>
                                <button
                                    type="button"
                                    onClick={closeEditor}
                                    className="shrink-0 p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-white/10"
                                    aria-label="Close editor"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
                            {error ? (
                                <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg">
                                    {error}
                                </div>
                            ) : null}
                            {renderEditorFields()}
                        </div>

                        <div className="shrink-0 flex gap-2 px-5 py-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/50">
                            {editingId && !isCreating ? (
                                deletingId === editingId ? (
                                    <>
                                        <button
                                            type="button"
                                            className="flex-1 px-4 py-2.5 text-sm font-medium rounded-lg bg-red-600 hover:bg-red-700 text-white"
                                            onClick={() => void handleDelete(editingId)}
                                        >
                                            Confirm delete
                                        </button>
                                        <button
                                            type="button"
                                            className="px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-600"
                                            onClick={() => setDeletingId(null)}
                                        >
                                            Cancel
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        type="button"
                                        className="inline-flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium rounded-lg border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                                        onClick={() => setDeletingId(editingId)}
                                    >
                                        <Trash2 size={14} />
                                        Delete
                                    </button>
                                )
                            ) : null}
                            <button
                                type="button"
                                className="flex-1 px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
                                onClick={closeEditor}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                disabled={saving}
                                className="flex-1 px-4 py-2.5 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 shadow-lg shadow-indigo-600/25"
                                onClick={() => void handleSave()}
                            >
                                {saving ? 'Saving…' : 'Save'}
                            </button>
                        </div>
                    </aside>
                </>
            ) : null}
        </div>
    );
};
