import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ApiClient } from '../api/client';
import { AuthClient } from '../api/authClient';
import { Palette, PaletteCreate, PaletteUpdate, SystemPalette, SystemPaletteCreate, SystemPaletteUpdate } from '../api/types';
import { Palette as PaletteIcon, Plus, Trash2, Brush, Settings, Download, Upload, CheckCircle2 } from 'lucide-react';
import { ManagerModal } from './ManagerModal';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import {
    SYSTEM_COLOR_TOKENS,
    DEFAULT_SYSTEM_COLORS_LIGHT,
    DEFAULT_SYSTEM_COLORS_DARK,
    type SystemColorToken,
    type SystemColorsMode,
} from '../theme/defaults';
import {
    normalizeWorkflowPaletteColors,
    resolveWorkflowPaletteColor,
    sortWorkflowPalettesForDisplay,
    type WorkflowPaletteFamily,
} from '../domain/paletteDefaults';
import {
    PaletteImportError,
    readPaletteImportFile,
    serializePaletteExport,
    slugifyPaletteExportBasename,
} from '../domain/paletteImportExport';
import { sortSystemPalettesForDisplay } from '../domain/systemPaletteDisplay';
import {
    SystemPaletteImportError,
    readSystemPaletteImportFile,
    serializeSystemPaletteExport,
    slugifySystemPaletteExportBasename,
} from '../domain/systemPaletteImportExport';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';

function hasDraftPaletteContent(form: { name: string; colors: Record<string, string> }): boolean {
    if (form.name.trim() !== '') return true;
    return Object.values(form.colors).some(v => v != null && String(v).trim() !== '');
}

function fullModesFromApiColors(
    colors: SystemPalette['colors'] | undefined,
): { light: SystemColorsMode; dark: SystemColorsMode } {
    const lightObj = colors?.light ?? {};
    const darkObj = colors?.dark ?? {};
    return {
        light: { ...DEFAULT_SYSTEM_COLORS_LIGHT, ...lightObj } as SystemColorsMode,
        dark: { ...DEFAULT_SYSTEM_COLORS_DARK, ...darkObj } as SystemColorsMode,
    };
}

function hasDraftSystemThemeContent(form: { name: string; light: SystemColorsMode; dark: SystemColorsMode }): boolean {
    if (form.name.trim() !== '') return true;
    return SYSTEM_COLOR_TOKENS.some(
        ({ key }) =>
            form.light[key] !== DEFAULT_SYSTEM_COLORS_LIGHT[key] ||
            form.dark[key] !== DEFAULT_SYSTEM_COLORS_DARK[key],
    );
}

function downloadPaletteJsonFile(name: string, colors: Record<string, string>, slug?: string | null): void {
    const json = serializePaletteExport(name, colors, slug);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `palette-${slugifyPaletteExportBasename(name)}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function downloadSystemPaletteJsonFile(
    name: string,
    light: SystemColorsMode,
    dark: SystemColorsMode,
    slug?: string | null,
): void {
    const json = serializeSystemPaletteExport(name, light, dark, slug);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `system-theme-${slugifySystemPaletteExportBasename(name)}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

/** Optional aggregate keys; labels match workflow editor sidebar sections. */
const STEP_FAMILY_ROWS: { key: WorkflowPaletteFamily; label: string }[] = [
    { key: 'primitive', label: 'Primitives' },
    { key: 'skill', label: 'Skills' },
    { key: 'utility', label: 'Utilities' },
    { key: 'control', label: 'Controls' },
];

const PALETTE_ENTITIES = [
    { key: 'string', label: 'String' },
    { key: 'list', label: 'List' },
    { key: 'dictionary', label: 'Dictionary' },
    { key: 'structure', label: 'Structure' },
    { key: 'boolean', label: 'Boolean' },
    { key: 'int', label: 'Int' },
    { key: 'any', label: 'Any' },
    { key: 'workflow', label: 'Workflow' },
    { key: 'simple_llm_call', label: 'Simple LLM Call' },
    { key: 'list_to_string', label: 'List to String' },
    { key: 'string_to_list', label: 'String to List' },
    { key: 'prepend_text', label: 'Prepend Text' },
    { key: 'string_trunc', label: 'String Trunc' },
    { key: 'len_from_list', label: 'Len from List' },
    { key: 'random_item_from_list', label: 'Random item from list' },
    { key: 'int_to_string', label: 'Int to String' },
    { key: 'basic_conditional', label: 'Basic Conditional' },
    { key: 'is_control', label: 'Is?' },
    { key: 'gt_control', label: 'Gt?' },
    { key: 'lt_control', label: 'Lt?' },
    { key: 'gte_control', label: 'Gte?' },
    { key: 'lte_control', label: 'Lte?' },
    { key: 'and_control', label: 'And' },
    { key: 'or_control', label: 'Or' },
    { key: 'xor_control', label: 'Xor' },
    { key: 'list_item_by_index', label: 'List Item by Index' },
    { key: 'dictionary_value_by_key', label: 'Dictionary Value by Key' },
    { key: 'dictionary_set_value_by_key', label: 'Dictionary Set Value by Key' },
] as const;

type TabId = 'editor' | 'system';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

export const PaletteManager: React.FC<Props> = ({ isOpen, onClose }) => {
    const { user, checkAuth } = useAuth();
    const { refreshActiveSystemPalette } = useTheme();
    const importInputRef = useRef<HTMLInputElement>(null);
    const systemImportInputRef = useRef<HTMLInputElement>(null);
    const [activeTab, setActiveTab] = useState<TabId>('editor');

    const [palettes, setPalettes] = useState<Palette[]>([]);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    /** Server-side palette import normalization notes (stripped unknown keys, etc.). */
    const [workflowImportHints, setWorkflowImportHints] = useState<string[]>([]);
    const [form, setForm] = useState<{ name: string; colors: Record<string, string> }>({ name: '', colors: {} });

    const [systemPalettes, setSystemPalettes] = useState<SystemPalette[]>([]);
    const [systemEditingId, setSystemEditingId] = useState<string | null>(null);
    const [systemDeletingId, setSystemDeletingId] = useState<string | null>(null);
    const [systemIsCreating, setSystemIsCreating] = useState(false);
    const [isLoadingSystem, setIsLoadingSystem] = useState(false);
    const [isSavingSystemPalette, setIsSavingSystemPalette] = useState(false);
    const [systemForm, setSystemForm] = useState<{
        name: string;
        light: SystemColorsMode;
        dark: SystemColorsMode;
    }>({
        name: '',
        light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
        dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
    });

    const load = async () => {
        setIsLoading(true);
        try {
            const res = await ApiClient.getPalettes();
            setPalettes(res);
        } catch {
            setError('Failed to load palettes.');
        } finally {
            setIsLoading(false);
        }
    };

    const loadSystemPalettes = async () => {
        setIsLoadingSystem(true);
        try {
            const res = await ApiClient.getSystemPalettes();
            setSystemPalettes(res);
        } catch {
            setError('Failed to load system themes.');
        } finally {
            setIsLoadingSystem(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            load();
            void loadSystemPalettes();
            setForm({ name: '', colors: {} });
            setIsCreating(false);
            setEditingId(null);
            setSystemEditingId(null);
            setSystemIsCreating(false);
            setSystemDeletingId(null);
            setWorkflowImportHints([]);
            setSystemForm({
                name: '',
                light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
                dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
            });
        }
    }, [isOpen]);

    const sortedPalettes = useMemo(() => sortWorkflowPalettesForDisplay(palettes), [palettes]);
    const sortedSystemPalettes = useMemo(() => sortSystemPalettesForDisplay(systemPalettes), [systemPalettes]);
    const activeSystemThemeId =
        typeof user?.settings?.system_palette_id === 'string' ? user.settings.system_palette_id : null;

    if (!isOpen) return null;

    const editingPalette = editingId ? palettes.find(x => x.id === editingId) : undefined;

    const handleEdit = (p: Palette) => {
        setIsCreating(false);
        setEditingId(p.id);
        setWorkflowImportHints([]);
        setForm({
            name: p.name,
            colors: normalizeWorkflowPaletteColors(p.colors),
        });
    };

    const handleSave = async () => {
        if (!form.name.trim()) {
            setError('Name is required.');
            return;
        }
        setError(null);
        const colorsToSave = normalizeWorkflowPaletteColors(form.colors);
        try {
            if (editingId) {
                const upd: PaletteUpdate = { name: form.name, colors: colorsToSave };
                await ApiClient.updatePalette(editingId, upd);
            } else {
                const crt: PaletteCreate = { name: form.name, colors: colorsToSave };
                await ApiClient.createPalette(crt);
            }
            await load();
            setEditingId(null);
            setIsCreating(false);
            setForm({ name: '', colors: {} });
        } catch (e: unknown) {
            setError((e as Error).message ?? 'Failed to save.');
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await ApiClient.deletePalette(id);
            setDeletingId(null);
            setEditingId(null);
            setIsCreating(false);
            setForm({ name: '', colors: {} });
            await load();
        } catch {
            setError('Failed to delete palette.');
        }
    };

    const setColor = (key: string, value: string) => {
        setForm(f => ({ ...f, colors: { ...f.colors, [key]: value } }));
    };

    /** Per-step hex text: empty removes override so family / defaults apply in the picker preview. */
    const clearOrSetStepHexFromText = (key: string, raw: string) => {
        const t = raw.trim();
        if (t === '') {
            setForm(f => {
                const next = { ...f.colors };
                delete next[key];
                return { ...f, colors: next };
            });
        } else {
            setColor(key, t);
        }
    };

    const setSystemThemeToken = (mode: 'light' | 'dark', token: SystemColorToken, value: string) => {
        setSystemForm(f => ({
            ...f,
            [mode]: { ...f[mode], [token]: value },
        }));
    };

    const editingSystemPalette = systemEditingId ? systemPalettes.find(x => x.id === systemEditingId) : undefined;
    /** Only built-in rows are read-only; `editingSystemPalette` is undefined while creating — do not use `?.user_id == null` alone (undefined == null is true). */
    const isEditingBuiltinSystemTheme =
        editingSystemPalette != null && editingSystemPalette.user_id == null;

    const handleEditSystemPalette = (p: SystemPalette) => {
        setSystemIsCreating(false);
        setSystemEditingId(p.id);
        const { light, dark } = fullModesFromApiColors(p.colors);
        setSystemForm({ name: p.name, light, dark });
    };

    const handleSaveSystemPalette = async () => {
        if (!systemForm.name.trim()) {
            setError('Name is required.');
            return;
        }
        setError(null);
        setIsSavingSystemPalette(true);
        const payload = {
            light: { ...systemForm.light },
            dark: { ...systemForm.dark },
        };
        try {
            let savedId: string | null = null;
            if (systemEditingId) {
                const upd: SystemPaletteUpdate = { name: systemForm.name, colors: payload };
                await ApiClient.updateSystemPalette(systemEditingId, upd);
                savedId = systemEditingId;
            } else {
                const crt: SystemPaletteCreate = { name: systemForm.name, colors: payload };
                const created = await ApiClient.createSystemPalette(crt);
                savedId = created.id;
            }
            const activePid = user?.settings?.system_palette_id;
            if (typeof activePid === 'string' && savedId != null && activePid === savedId) {
                refreshActiveSystemPalette();
            }
            await loadSystemPalettes();
            setSystemEditingId(null);
            setSystemIsCreating(false);
            setSystemForm({
                name: '',
                light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
                dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
            });
        } catch (e: unknown) {
            setError((e as Error).message ?? 'Failed to save system theme.');
        } finally {
            setIsSavingSystemPalette(false);
        }
    };

    const handleDeleteSystemPalette = async (id: string) => {
        try {
            await ApiClient.deleteSystemPalette(id);
            setSystemDeletingId(null);
            setSystemEditingId(null);
            setSystemIsCreating(false);
            setSystemForm({
                name: '',
                light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
                dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
            });
            await loadSystemPalettes();
        } catch {
            setError('Failed to delete system theme.');
        }
    };

    const handleUseSystemTheme = async (paletteId: string) => {
        setError(null);
        try {
            const current = (user?.settings ?? {}) as Record<string, unknown>;
            await AuthClient.updateMe({
                settings: { ...current, system_palette_id: paletteId },
            });
            await checkAuth({ silent: true });
            refreshActiveSystemPalette();
        } catch (e: unknown) {
            setError((e as Error).message ?? 'Failed to set active theme.');
        }
    };

    const handleClearActiveSystemTheme = async () => {
        setError(null);
        try {
            const current = (user?.settings ?? {}) as Record<string, unknown>;
            const next = { ...current, system_palette_id: null };
            await AuthClient.updateMe({ settings: next });
            await checkAuth({ silent: true });
        } catch (e: unknown) {
            setError((e as Error).message ?? 'Failed to clear active theme.');
        }
    };

    const applyImportedSystemPalette = (name: string, light: Record<string, string>, dark: Record<string, string>) => {
        setError(null);
        setSystemEditingId(null);
        setSystemIsCreating(true);
        setSystemForm({
            name,
            light: { ...DEFAULT_SYSTEM_COLORS_LIGHT, ...light } as SystemColorsMode,
            dark: { ...DEFAULT_SYSTEM_COLORS_DARK, ...dark } as SystemColorsMode,
        });
    };

    const handleSystemImportFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        try {
            const data = await readSystemPaletteImportFile(file);
            const needsConfirm =
                (systemIsCreating || systemEditingId !== null) && hasDraftSystemThemeContent(systemForm);
            if (needsConfirm && !window.confirm('Replace the current system theme editor with the imported theme?')) {
                return;
            }
            applyImportedSystemPalette(data.name, data.light, data.dark);
        } catch (err) {
            const msg =
                err instanceof SystemPaletteImportError
                    ? err.message
                    : err instanceof Error
                      ? err.message
                      : 'Import failed.';
            setError(msg);
        }
    };

    const applyImportedPalette = (
        name: string,
        colors: Record<string, string>,
        hints: readonly string[] = [],
    ) => {
        setError(null);
        setWorkflowImportHints([...hints]);
        setEditingId(null);
        setIsCreating(true);
        setForm({ name, colors: normalizeWorkflowPaletteColors(colors) });
    };

    const handlePaletteImportFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        try {
            const data = await readPaletteImportFile(file);
            const validated = await ApiClient.validateWorkflowPaletteImport(data.colors);
            const needsConfirm =
                (isCreating || editingId !== null) && hasDraftPaletteContent(form);
            if (needsConfirm && !window.confirm('Replace the current editor contents with the imported palette?')) {
                return;
            }
            applyImportedPalette(data.name, validated.colors, validated.warnings);
        } catch (err) {
            const msg =
                err instanceof PaletteImportError
                    ? err.message
                    : err instanceof Error
                      ? err.message
                      : 'Import failed.';
            setError(msg);
        }
    };

    const inputCls = MANAGER_INPUT_CLS;
    const labelCls = MANAGER_LABEL_CLS;

    const tabBtn = (id: TabId, icon: React.ReactNode, label: string) => (
        <button
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === id
                    ? 'bg-mw-primary-muted text-mw-primary'
                    : 'text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary'
            }`}
        >
            {icon}
            {label}
        </button>
    );

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Manage Palettes" maxWidth="2xl">
            <div className="flex gap-2 px-4 py-2 border-b border-mw-border bg-mw-sidebar">
                    {tabBtn('editor', <Brush size={16} />, 'Editor')}
                    {tabBtn('system', <Settings size={16} />, 'System')}
                </div>

                <div className="flex flex-1 overflow-hidden">
                    {activeTab === 'editor' && (
                        <>
                            <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                                <div className="p-3 border-b border-mw-border space-y-2">
                                    <input
                                        ref={importInputRef}
                                        type="file"
                                        accept="application/json,.json"
                                        className="hidden"
                                        aria-hidden
                                        onChange={handlePaletteImportFileChange}
                                    />
                                    <button
                                        onClick={() => {
                                            setIsCreating(true);
                                            setEditingId(null);
                                            setWorkflowImportHints([]);
                                            setForm({ name: '', colors: {} });
                                        }}
                                        className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors"
                                    >
                                        <Plus size={15} /> New Palette
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => importInputRef.current?.click()}
                                        className="w-full flex items-center justify-center gap-2 py-2 border border-mw-border text-mw-text-primary hover:bg-mw-card rounded-lg text-sm font-medium transition-colors"
                                    >
                                        <Upload size={15} /> Import JSON
                                    </button>
                                </div>
                                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                                    {isLoading && (
                                        <div className="text-sm text-center text-mw-text-secondary p-4">Loading…</div>
                                    )}
                                    {sortedPalettes.map(p => (
                                        <div
                                            key={p.id}
                                            className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                                                editingId === p.id
                                                    ? 'bg-mw-primary-muted border border-mw-primary'
                                                    : 'hover:bg-mw-card border border-transparent'
                                            }`}
                                            onClick={() => handleEdit(p)}
                                        >
                                            <div className="truncate pr-2 min-w-0">
                                                <div className="text-sm font-medium text-mw-text-primary truncate flex items-center gap-1.5">
                                                    {p.name}
                                                    {p.user_id == null && (
                                                        <span className="text-xs bg-mw-card-alt text-mw-text-secondary px-1.5 py-0.5 rounded">
                                                            System
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <div
                                                className={`flex gap-1 shrink-0 ${
                                                    deletingId === p.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                                                }`}
                                            >
                                                {deletingId !== p.id && (
                                                    <button
                                                        type="button"
                                                        onClick={e => {
                                                            e.stopPropagation();
                                                            downloadPaletteJsonFile(p.name, p.colors, p.slug);
                                                        }}
                                                        className="p-1 text-mw-text-secondary hover:bg-mw-card-alt rounded"
                                                        aria-label="Export palette as JSON file"
                                                    >
                                                        <Download size={14} />
                                                    </button>
                                                )}
                                                {p.user_id != null && deletingId !== p.id && (
                                                    <button
                                                        onClick={e => {
                                                            e.stopPropagation();
                                                            setDeletingId(p.id);
                                                        }}
                                                        className="p-1 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                                                        title="Delete"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                )}
                                                {deletingId === p.id && (
                                                    <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                                        <button
                                                            onClick={() => handleDelete(p.id)}
                                                            className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium"
                                                        >
                                                            Delete
                                                        </button>
                                                        <button
                                                            onClick={() => setDeletingId(null)}
                                                            className="px-2 py-0.5 text-xs bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                                {editingId || isCreating ? (
                                    <div className="space-y-4 max-w-md">
                                        <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                            {isCreating ? 'Create Palette' : 'Edit Palette'}
                                        </h3>
                                        {workflowImportHints.length > 0 && (
                                            <div className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-900/25 px-3 py-2 rounded-lg whitespace-pre-wrap">
                                                {workflowImportHints.join('\n')}
                                            </div>
                                        )}
                                        {error && (
                                            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">
                                                {error}
                                            </div>
                                        )}

                                        <div>
                                            <label className={labelCls}>Name *</label>
                                            <input
                                                value={form.name}
                                                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                                className={inputCls}
                                                placeholder="e.g. Default"
                                            />
                                        </div>

                                        <div>
                                            <label className={`${labelCls} mb-2`}>Step family colors (optional)</label>
                                            <p className="text-xs text-mw-text-secondary mb-2">
                                                Applies to all steps in that family when no specific color is set below.
                                            </p>
                                            <div className="space-y-3">
                                                {STEP_FAMILY_ROWS.map(({ key, label }) => {
                                                    const raw = form.colors[key];
                                                    const unset = raw == null || raw === '';
                                                    const colorPickerValue = unset ? '#808080' : raw;
                                                    return (
                                                        <div key={key} className="flex items-center gap-3">
                                                            <label className="text-sm font-medium text-mw-text-primary w-28 shrink-0">
                                                                {label}
                                                            </label>
                                                            <input
                                                                type="color"
                                                                value={colorPickerValue}
                                                                onChange={e => setColor(key, e.target.value)}
                                                                className="w-12 h-10 rounded border border-mw-border cursor-pointer bg-transparent"
                                                            />
                                                            <input
                                                                type="text"
                                                                value={raw ?? ''}
                                                                onChange={e => setColor(key, e.target.value)}
                                                                className="flex-1 px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-sidebar rounded text-mw-text-primary"
                                                                placeholder={unset ? 'optional — inherit per step' : '#hex'}
                                                            />
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        <div>
                                            <label className={`${labelCls} mb-2`}>Specific step colors</label>
                                            <div className="space-y-3">
                                                {PALETTE_ENTITIES.map(({ key, label }) => {
                                                    const stored = form.colors[key];
                                                    const resolved = resolveWorkflowPaletteColor(form.colors, key);
                                                    return (
                                                        <div key={key} className="flex items-center gap-3">
                                                            <label className="text-sm font-medium text-mw-text-primary w-28 shrink-0">
                                                                {label}
                                                            </label>
                                                            <input
                                                                type="color"
                                                                value={resolved}
                                                                onChange={e => setColor(key, e.target.value)}
                                                                className="w-12 h-10 rounded border border-mw-border cursor-pointer bg-transparent"
                                                            />
                                                            <input
                                                                type="text"
                                                                value={stored ?? ''}
                                                                onChange={e => clearOrSetStepHexFromText(key, e.target.value)}
                                                                className="flex-1 px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-sidebar rounded text-mw-text-primary"
                                                                placeholder={
                                                                    stored != null && stored !== ''
                                                                        ? '#hex'
                                                                        : 'Inherited — leave empty'
                                                                }
                                                            />
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        <div className="pt-2 flex flex-wrap items-center justify-between gap-2">
                                            <button
                                                type="button"
                                                disabled={!form.name.trim()}
                                                title={!form.name.trim() ? 'Add a name to export' : undefined}
                                                onClick={() =>
                                                    downloadPaletteJsonFile(form.name, form.colors, editingPalette?.slug)
                                                }
                                                className="px-4 py-2 text-sm font-medium text-mw-text-primary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none inline-flex items-center gap-2"
                                            >
                                                <Download size={16} /> Export JSON
                                            </button>
                                            <div className="flex gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setIsCreating(false);
                                                        setEditingId(null);
                                                        setError(null);
                                                    }}
                                                    className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={handleSave}
                                                    className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors"
                                                >
                                                    Save Palette
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary px-4">
                                        {error && (
                                            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg mb-4 max-w-md w-full">
                                                {error}
                                            </div>
                                        )}
                                        <PaletteIcon size={48} className="mb-4 text-mw-text-secondary opacity-50" />
                                        <p>Select a palette or create a new one.</p>
                                        <p className="text-xs mt-2 text-center max-w-xs">
                                            Palettes map step colors (per item or by step family) to workflow handles and edges.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </>
                    )}

                    {activeTab === 'system' && (
                        <>
                            <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                                <div className="p-3 border-b border-mw-border space-y-2">
                                    <input
                                        ref={systemImportInputRef}
                                        type="file"
                                        accept="application/json,.json"
                                        className="hidden"
                                        aria-hidden
                                        onChange={handleSystemImportFileChange}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setSystemIsCreating(true);
                                            setSystemEditingId(null);
                                            setSystemForm({
                                                name: '',
                                                light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
                                                dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
                                            });
                                        }}
                                        className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors"
                                    >
                                        <Plus size={15} /> New Theme
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => systemImportInputRef.current?.click()}
                                        className="w-full flex items-center justify-center gap-2 py-2 border border-mw-border text-mw-text-primary hover:bg-mw-card rounded-lg text-sm font-medium transition-colors"
                                    >
                                        <Upload size={15} /> Import JSON
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => void handleClearActiveSystemTheme()}
                                        className="w-full py-2 text-xs text-mw-text-secondary hover:underline"
                                    >
                                        Clear active theme preset
                                    </button>
                                </div>
                                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                                    {isLoadingSystem && (
                                        <div className="text-sm text-center text-mw-text-secondary p-4">Loading…</div>
                                    )}
                                    {sortedSystemPalettes.map(p => (
                                        <div
                                            key={p.id}
                                            className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                                                systemEditingId === p.id
                                                    ? 'bg-mw-primary-muted border border-mw-primary'
                                                    : 'hover:bg-mw-card border border-transparent'
                                            }`}
                                            onClick={() => handleEditSystemPalette(p)}
                                        >
                                            <div className="truncate pr-2 min-w-0">
                                                <div className="text-sm font-medium text-mw-text-primary truncate flex items-center gap-1.5 flex-wrap">
                                                    {p.name}
                                                    {p.user_id == null && (
                                                        <span className="text-xs bg-mw-card-alt text-mw-text-secondary px-1.5 py-0.5 rounded">
                                                            System
                                                        </span>
                                                    )}
                                                    {activeSystemThemeId === p.id && (
                                                        <span className="text-xs bg-mw-success-muted text-mw-success px-1.5 py-0.5 rounded">
                                                            Active
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <div
                                                className={`flex gap-1 shrink-0 ${
                                                    systemDeletingId === p.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                                                }`}
                                            >
                                                {systemDeletingId !== p.id && (
                                                    <>
                                                        <button
                                                            type="button"
                                                            onClick={e => {
                                                                e.stopPropagation();
                                                                void handleUseSystemTheme(p.id);
                                                            }}
                                                            disabled={activeSystemThemeId === p.id}
                                                            className="p-1 text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-success rounded disabled:opacity-40 disabled:pointer-events-none disabled:hover:text-mw-text-secondary"
                                                            title={
                                                                activeSystemThemeId === p.id
                                                                    ? 'Already your active theme'
                                                                    : 'Use as my theme'
                                                            }
                                                            aria-label="Use as my theme from list"
                                                        >
                                                            <CheckCircle2 size={14} />
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={e => {
                                                                e.stopPropagation();
                                                                const modes = fullModesFromApiColors(p.colors);
                                                                downloadSystemPaletteJsonFile(p.name, modes.light, modes.dark, p.slug);
                                                            }}
                                                            className="p-1 text-mw-text-secondary hover:bg-mw-card-alt rounded"
                                                            aria-label="Export system theme as JSON"
                                                        >
                                                            <Download size={14} />
                                                        </button>
                                                    </>
                                                )}
                                                {p.user_id != null && systemDeletingId !== p.id && (
                                                    <button
                                                        type="button"
                                                        onClick={e => {
                                                            e.stopPropagation();
                                                            setSystemDeletingId(p.id);
                                                        }}
                                                        className="p-1 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                                                        title="Delete"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                )}
                                                {systemDeletingId === p.id && (
                                                    <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                                        <button
                                                            type="button"
                                                            onClick={() => void handleDeleteSystemPalette(p.id)}
                                                            className="px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium"
                                                        >
                                                            Delete
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => setSystemDeletingId(null)}
                                                            className="px-2 py-0.5 text-xs bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                                {systemEditingId || systemIsCreating ? (
                                    <div className="space-y-6 max-w-lg">
                                        <div className="flex flex-wrap items-start justify-between gap-2">
                                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2 flex-1 min-w-[200px]">
                                                {systemIsCreating ? 'Create System Theme' : 'Edit System Theme'}
                                            </h3>
                                            {isEditingBuiltinSystemTheme && (
                                                <span className="text-xs bg-mw-card-alt text-mw-text-secondary px-2 py-1 rounded">
                                                    Built-in (read-only)
                                                </span>
                                            )}
                                        </div>
                                        {error && activeTab === 'system' && (
                                            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">
                                                {error}
                                            </div>
                                        )}
                                        <p className="text-xs text-mw-text-secondary">
                                            Sets light and dark semantic tokens for the whole app. The preset applies after
                                            you choose <strong className="font-semibold text-mw-text-primary">Use as my theme</strong> on a
                                            row or set <strong className="font-semibold text-mw-text-primary">App theme</strong> in My Settings.
                                            Optional per-token overrides in{' '}
                                            <code className="text-xs">User.settings.system_colors</code> still merge on top of the
                                            active preset.
                                        </p>

                                        <div>
                                            <label className={labelCls}>Name *</label>
                                            <input
                                                value={systemForm.name}
                                                onChange={e => setSystemForm(f => ({ ...f, name: e.target.value }))}
                                                disabled={isEditingBuiltinSystemTheme}
                                                className={
                                                    inputCls + (isEditingBuiltinSystemTheme ? ' opacity-70' : '')
                                                }
                                                placeholder="e.g. My theme"
                                            />
                                        </div>

                                        {(['light', 'dark'] as const).map(mode => (
                                            <div key={mode}>
                                                <h4 className="text-sm font-semibold text-mw-text-primary mb-2 capitalize">
                                                    {mode} mode
                                                </h4>
                                                <div className="space-y-3">
                                                    {SYSTEM_COLOR_TOKENS.map(({ key, label }) => {
                                                        const ro = isEditingBuiltinSystemTheme;
                                                        const value = systemForm[mode][key];
                                                        return (
                                                            <div key={`${mode}-${key}`} className="flex items-center gap-3">
                                                                <label className="text-sm font-medium text-mw-text-primary w-36 shrink-0">
                                                                    {label}
                                                                </label>
                                                                <input
                                                                    type="color"
                                                                    value={value}
                                                                    onChange={e => setSystemThemeToken(mode, key, e.target.value)}
                                                                    disabled={ro}
                                                                    className="w-12 h-10 rounded border border-mw-border cursor-pointer bg-transparent disabled:opacity-50"
                                                                />
                                                                <input
                                                                    type="text"
                                                                    value={value}
                                                                    onChange={e => setSystemThemeToken(mode, key, e.target.value)}
                                                                    disabled={ro}
                                                                    className="flex-1 px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-sidebar rounded text-mw-text-primary disabled:opacity-70"
                                                                    placeholder="#hex"
                                                                />
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        ))}

                                        <div className="pt-2 flex flex-wrap items-center justify-between gap-2">
                                            <button
                                                type="button"
                                                disabled={!systemForm.name.trim()}
                                                title={!systemForm.name.trim() ? 'Add a name to export' : undefined}
                                                onClick={() =>
                                                    downloadSystemPaletteJsonFile(
                                                        systemForm.name,
                                                        systemForm.light,
                                                        systemForm.dark,
                                                        editingSystemPalette?.slug,
                                                    )
                                                }
                                                className="px-4 py-2 text-sm font-medium text-mw-text-primary border border-mw-border hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none inline-flex items-center gap-2"
                                            >
                                                <Download size={16} /> Export JSON
                                            </button>
                                            <div className="flex flex-wrap gap-2 justify-end">
                                                {systemEditingId && (
                                                    <button
                                                        type="button"
                                                        onClick={() => void handleUseSystemTheme(systemEditingId)}
                                                        className="px-4 py-2 text-sm font-medium text-white bg-mw-success hover:opacity-90 rounded-lg transition-colors"
                                                    >
                                                        Use as my theme
                                                    </button>
                                                )}
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setSystemIsCreating(false);
                                                        setSystemEditingId(null);
                                                        setSystemDeletingId(null);
                                                        setSystemForm({
                                                            name: '',
                                                            light: { ...DEFAULT_SYSTEM_COLORS_LIGHT },
                                                            dark: { ...DEFAULT_SYSTEM_COLORS_DARK },
                                                        });
                                                        setError(null);
                                                    }}
                                                    className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                                {editingSystemPalette?.user_id != null || systemIsCreating ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => void handleSaveSystemPalette()}
                                                        disabled={isSavingSystemPalette}
                                                        className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50"
                                                    >
                                                        {isSavingSystemPalette ? 'Saving…' : 'Save Theme'}
                                                    </button>
                                                ) : null}
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary px-4">
                                        {error && (
                                            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg mb-4 max-w-md w-full">
                                                {error}
                                            </div>
                                        )}
                                        <Settings size={48} className="mb-4 text-mw-text-secondary opacity-50" />
                                        <p>Select a system theme or create a new one.</p>
                                        <p className="text-xs mt-2 text-center max-w-xs">
                                            Built-in themes match workflow palette names. Use “Use as my theme” to apply one,
                                            or duplicate via Export → Import.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>
        </ManagerModal>
    );
};
