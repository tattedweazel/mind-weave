/**
 * MySettings
 * ==========
 * User settings modal: My Profile (with avatar), View Settings, System Settings (workflow execution), Google Account, API Settings.
 * Opened from top-right header. Admin user management is in Configure > User Management.
 */

import React, { useMemo, useState, useEffect, useRef } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { AuthClient } from '../../api/authClient';
import { ApiClient } from '../../api/client';
import type { GoogleWorkflowConnection, Palette, SystemPalette, TtsModelRead } from '../../api/types';
import { sortWorkflowPalettesForDisplay } from '../../domain/paletteDefaults';
import { sortSystemPalettesForDisplay } from '../../domain/systemPaletteDisplay';
import {
    GMAIL_CATEGORY_LABELS,
    GMAIL_EXCLUDABLE_CATEGORY_SLUGS,
    normalizeGmailExcludeCategories,
    type GmailExcludableCategory,
} from '../../domain/gmailCategoryFilters';
import { getSystemTimeZone, listIanaTimeZones } from '../../domain/gmailRfc3339Date';
import type { TtsPlaybackWhen } from '../../domain/resolveAutoPlayTtsOnNodeEnd';
import { ChevronDown, Gauge, Save, Link2, Unlink, User, Mail, Key, Upload, Eye, Volume2, Trash2, RefreshCw } from 'lucide-react';
import { ContextHelpModal } from '../ContextHelpModal';
import { ManagerModal } from '../ManagerModal';
import { UserAvatar } from '../UserAvatar';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from '../managerShellStyles';

const inputCls = MANAGER_INPUT_CLS;
const labelCls = MANAGER_LABEL_CLS;

const MAX_CONCURRENT_LM_STUDIO_CALLS_MIN = 1;
const MAX_CONCURRENT_LM_STUDIO_CALLS_MAX = 32;
const MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT = 3;

function parseMaxConcurrentLmStudioCalls(raw: unknown): number {
    if (typeof raw === 'number' && Number.isInteger(raw)) {
        return Math.max(
            MAX_CONCURRENT_LM_STUDIO_CALLS_MIN,
            Math.min(MAX_CONCURRENT_LM_STUDIO_CALLS_MAX, raw),
        );
    }
    return MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT;
}

/** Docs/curl often include "Bearer "; pasting that sends double Bearer to the server and LM Studio returns 401. */
function stripBearerPrefix(s: string): string {
    let t = s.trim().replace(/^\uFEFF/, '');
    for (let i = 0; i < 4; i++) {
        const m = /^bearer\s+/i.exec(t);
        if (!m) break;
        t = t.slice(m[0].length).trim();
    }
    return t;
}

type SectionId = 'profile' | 'view' | 'system' | 'google' | 'api' | 'tts';

type ThemeModeSetting = 'light' | 'dark' | 'system';

const SECTIONS: { id: SectionId; label: string; icon: React.ReactNode }[] = [
    { id: 'profile', label: 'My Profile', icon: <User size={16} /> },
    { id: 'view', label: 'View Settings', icon: <Eye size={16} /> },
    { id: 'system', label: 'System Settings', icon: <Gauge size={16} /> },
    { id: 'google', label: 'Google Account', icon: <Mail size={16} /> },
    { id: 'api', label: 'API Settings', icon: <Key size={16} /> },
];

const TTS_ADMIN_SECTION: { id: SectionId; label: string; icon: React.ReactNode } = {
    id: 'tts',
    label: 'TTS models',
    icon: <Volume2 size={16} />,
};

export interface MySettingsProps {
    isOpen: boolean;
    onClose: () => void;
}

export const MySettings: React.FC<MySettingsProps> = ({ isOpen, onClose }) => {
    const { user, checkAuth, logout } = useAuth();
    const [isAssociating, setIsAssociating] = useState(false);
    const [isDisassociating, setIsDisassociating] = useState(false);
    /** API keys: uncontrolled + refs so Save always reads the DOM (avoids React state / effects clearing typed secrets). */
    const lmstudioApiKeyInputRef = useRef<HTMLInputElement>(null);
    const openaiApiKeyInputRef = useRef<HTMLInputElement>(null);
    const anthropicApiKeyInputRef = useRef<HTMLInputElement>(null);
    const googleApiKeyInputRef = useRef<HTMLInputElement>(null);
    const assemblyaiApiKeyInputRef = useRef<HTMLInputElement>(null);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [isSavingView, setIsSavingView] = useState(false);
    const [selectedSection, setSelectedSection] = useState<SectionId>('profile');
    const [systemPaletteOptions, setSystemPaletteOptions] = useState<SystemPalette[]>([]);
    const [workflowPaletteOptions, setWorkflowPaletteOptions] = useState<Palette[]>([]);
    const [viewPalettesLoading, setViewPalettesLoading] = useState(false);
    const [viewSystemPaletteId, setViewSystemPaletteId] = useState('');
    const [viewEditorPaletteId, setViewEditorPaletteId] = useState('');
    const [viewThemeMode, setViewThemeMode] = useState<ThemeModeSetting>('system');
    const [viewRememberWorkflowPanelWidths, setViewRememberWorkflowPanelWidths] = useState(true);
    const [viewTtsPlaybackWhen, setViewTtsPlaybackWhen] = useState<TtsPlaybackWhen>('inline');
    const [workflowGoogleConnections, setWorkflowGoogleConnections] = useState<GoogleWorkflowConnection[]>([]);
    const [workflowGoogleLoading, setWorkflowGoogleLoading] = useState(false);
    const [workflowGoogleConnecting, setWorkflowGoogleConnecting] = useState(false);
    const [gmailWorkflowInboxFocus, setGmailWorkflowInboxFocus] = useState<'off' | 'primary'>('off');
    const [gmailWorkflowExclude, setGmailWorkflowExclude] = useState<Set<string>>(() => new Set());
    const [isSavingGmailFilters, setIsSavingGmailFilters] = useState(false);
    const [profileWorkflowTimeZone, setProfileWorkflowTimeZone] = useState('system');
    const [committedProfileWorkflowTimeZone, setCommittedProfileWorkflowTimeZone] = useState('system');
    const [isSavingProfileTz, setIsSavingProfileTz] = useState(false);
    const [systemMaxConcurrentLmCalls, setSystemMaxConcurrentLmCalls] = useState(
        MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT,
    );
    const [committedSystemMaxConcurrentLmCalls, setCommittedSystemMaxConcurrentLmCalls] = useState(
        MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT,
    );
    const [isSavingSystem, setIsSavingSystem] = useState(false);
    const [ttsRegistry, setTtsRegistry] = useState<TtsModelRead[]>([]);
    const [ttsLoading, setTtsLoading] = useState(false);
    const [ttsBusyId, setTtsBusyId] = useState<string | null>(null);
    const [ttsDisplayName, setTtsDisplayName] = useState('');
    const [ttsEngine, setTtsEngine] = useState<'qwen_torch' | 'qwen_mlx'>('qwen_torch');
    const [ttsRepoId, setTtsRepoId] = useState('');
    const [ttsRevision, setTtsRevision] = useState('');
    const sidebarSections = user?.is_admin ? [...SECTIONS, TTS_ADMIN_SECTION] : SECTIONS;
    const profileTimezoneDirty = profileWorkflowTimeZone !== committedProfileWorkflowTimeZone;
    const systemConcurrentDirty = systemMaxConcurrentLmCalls !== committedSystemMaxConcurrentLmCalls;
    const ianaZoneOptions = useMemo(() => listIanaTimeZones(), []);

    useEffect(() => {
        if (!user || !isOpen) return;
        setViewSystemPaletteId(
            typeof user.settings.system_palette_id === 'string' ? user.settings.system_palette_id : '',
        );
        setViewEditorPaletteId(
            typeof user.settings.preferred_editor_palette_id === 'string'
                ? user.settings.preferred_editor_palette_id
                : '',
        );
        const tm = user.settings.theme_mode;
        setViewThemeMode(tm === 'light' || tm === 'dark' || tm === 'system' ? tm : 'system');
        const rw = user.settings.workflow_editor_remember_panel_widths;
        setViewRememberWorkflowPanelWidths(typeof rw === 'boolean' ? rw : true);
        const w = user.settings.tts_playback_when;
        if (w === 'inline' || w === 'manual' || w === 'after_workflow') {
            setViewTtsPlaybackWhen(w);
        } else {
            const ap = user.settings.auto_play_tts_on_node_end;
            setViewTtsPlaybackWhen(typeof ap === 'boolean' && !ap ? 'manual' : 'inline');
        }
    }, [user, isOpen]);

    useEffect(() => {
        if (!isOpen || selectedSection !== 'view' || !user) return;
        let cancelled = false;
        setViewPalettesLoading(true);
        void (async () => {
            try {
                const [sys, wf] = await Promise.all([
                    ApiClient.getSystemPalettes(),
                    ApiClient.getPalettes(),
                ]);
                if (!cancelled) {
                    setSystemPaletteOptions(sortSystemPalettesForDisplay(sys));
                    setWorkflowPaletteOptions(sortWorkflowPalettesForDisplay(wf));
                }
            } catch {
                if (!cancelled) {
                    setSystemPaletteOptions([]);
                    setWorkflowPaletteOptions([]);
                }
            } finally {
                if (!cancelled) setViewPalettesLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [isOpen, selectedSection, user]);

    useEffect(() => {
        if (!isOpen || selectedSection !== 'google') return;
        let cancelled = false;
        setWorkflowGoogleLoading(true);
        void (async () => {
            try {
                const rows = await ApiClient.getGoogleWorkflowConnections();
                if (!cancelled) setWorkflowGoogleConnections(rows);
            } catch {
                if (!cancelled) setWorkflowGoogleConnections([]);
            } finally {
                if (!cancelled) setWorkflowGoogleLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [isOpen, selectedSection]);

    useEffect(() => {
        if (!user || !isOpen || selectedSection !== 'profile') return;
        const raw = user.settings?.workflow_time_zone;
        const val =
            typeof raw === 'string' && raw.trim() && raw.trim().toLowerCase() !== 'system' ? raw.trim() : 'system';
        setProfileWorkflowTimeZone(val);
        setCommittedProfileWorkflowTimeZone(val);
    }, [user, isOpen, selectedSection]);

    useEffect(() => {
        if (!user?.is_admin && selectedSection === 'tts') {
            setSelectedSection('profile');
        }
    }, [user?.is_admin, selectedSection]);

    useEffect(() => {
        if (!isOpen || selectedSection !== 'tts' || !user?.is_admin) return;
        let cancelled = false;
        setTtsLoading(true);
        void (async () => {
            try {
                const rows = await ApiClient.getTtsModelsRegistry();
                if (!cancelled) setTtsRegistry(rows);
            } catch {
                if (!cancelled) setTtsRegistry([]);
            } finally {
                if (!cancelled) setTtsLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [isOpen, selectedSection, user?.is_admin]);

    useEffect(() => {
        if (!user || !isOpen || selectedSection !== 'system') return;
        const n = parseMaxConcurrentLmStudioCalls(user.settings?.max_concurrent_lm_studio_calls);
        setSystemMaxConcurrentLmCalls(n);
        setCommittedSystemMaxConcurrentLmCalls(n);
    }, [user, isOpen, selectedSection]);

    useEffect(() => {
        if (!user || !isOpen || selectedSection !== 'google') return;
        const raw = user.settings?.gmail_workflow_inbox_focus;
        setGmailWorkflowInboxFocus(raw === 'primary' ? 'primary' : 'off');
        setGmailWorkflowExclude(
            new Set(normalizeGmailExcludeCategories(user.settings?.gmail_workflow_exclude_categories)),
        );
    }, [user, isOpen, selectedSection]);

    if (!isOpen || !user) return null;

    const avatarUrl = user.settings && typeof user.settings.avatar_url === 'string'
        ? (user.settings.avatar_url as string)
        : undefined;

    const handleSaveSettings = async () => {
        setIsSaving(true);
        setError(null);
        setSuccess(null);
        try {
            const apiKeys: Record<string, string> = {};
            const take = (el: HTMLInputElement | null) => stripBearerPrefix((el?.value ?? '').trim());
            const lm = take(lmstudioApiKeyInputRef.current);
            const oa = take(openaiApiKeyInputRef.current);
            const an = take(anthropicApiKeyInputRef.current);
            const go = take(googleApiKeyInputRef.current);
            const aa = take(assemblyaiApiKeyInputRef.current);
            if (lm) apiKeys['lmstudio_api_key'] = lm;
            if (oa) apiKeys['openai'] = oa;
            if (an) apiKeys['anthropic'] = an;
            if (go) apiKeys['google'] = go;
            if (aa) apiKeys['assemblyai'] = aa;
            if (Object.keys(apiKeys).length === 0) {
                setSuccess('No new keys entered — existing keys unchanged.');
                return;
            }
            await AuthClient.updateMe({ api_keys: apiKeys });
            await checkAuth({ silent: true });
            if (lmstudioApiKeyInputRef.current) lmstudioApiKeyInputRef.current.value = '';
            if (openaiApiKeyInputRef.current) openaiApiKeyInputRef.current.value = '';
            if (anthropicApiKeyInputRef.current) anthropicApiKeyInputRef.current.value = '';
            if (googleApiKeyInputRef.current) googleApiKeyInputRef.current.value = '';
            if (assemblyaiApiKeyInputRef.current) assemblyaiApiKeyInputRef.current.value = '';
            setSuccess('Settings saved successfully.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to save settings');
        } finally {
            setIsSaving(false);
        }
    };

    const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file || !file.type.startsWith('image/')) return;
        setError(null);
        setSuccess(null);
        const reader = new FileReader();
        reader.onload = async () => {
            const dataUrl = reader.result as string;
            try {
                await AuthClient.updateMe({
                    settings: { ...user.settings, avatar_url: dataUrl }
                });
                await checkAuth({ silent: true });
                setSuccess('Avatar updated.');
            } catch (err: unknown) {
                setError(err instanceof Error ? err.message : 'Failed to update avatar');
            }
        };
        reader.readAsDataURL(file);
        e.target.value = '';
    };

    const handleSaveProfileTimezone = async () => {
        setError(null);
        setSuccess(null);
        setIsSavingProfileTz(true);
        try {
            const value = profileWorkflowTimeZone === 'system' ? 'system' : profileWorkflowTimeZone;
            await AuthClient.updateMe({
                settings: { ...user.settings, workflow_time_zone: value },
            });
            await checkAuth({ silent: true });
            const saved = profileWorkflowTimeZone === 'system' ? 'system' : profileWorkflowTimeZone;
            setCommittedProfileWorkflowTimeZone(saved);
            setSuccess('Timezone saved.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to save timezone');
        } finally {
            setIsSavingProfileTz(false);
        }
    };

    const handleAssociateGoogle = async () => {
        setError(null);
        setIsAssociating(true);
        try {
            const { redirect_url } = await AuthClient.getGoogleAuthorizeUrl();
            window.location.href = redirect_url;
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to start Google association');
            setIsAssociating(false);
        }
    };

    const handleSaveViewSettings = async () => {
        setIsSavingView(true);
        setError(null);
        setSuccess(null);
        try {
            await AuthClient.updateMe({
                settings: {
                    ...user.settings,
                    system_palette_id: viewSystemPaletteId.trim() === '' ? null : viewSystemPaletteId.trim(),
                    preferred_editor_palette_id:
                        viewEditorPaletteId.trim() === '' ? null : viewEditorPaletteId.trim(),
                    theme_mode: viewThemeMode,
                    workflow_editor_remember_panel_widths: viewRememberWorkflowPanelWidths,
                    tts_playback_when: viewTtsPlaybackWhen,
                    auto_play_tts_on_node_end: viewTtsPlaybackWhen === 'inline',
                },
            });
            await checkAuth({ silent: true });
            setSuccess('View settings saved.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to save view settings');
        } finally {
            setIsSavingView(false);
        }
    };

    const handleSaveSystemSettings = async () => {
        if (!user) return;
        setIsSavingSystem(true);
        setError(null);
        setSuccess(null);
        try {
            await AuthClient.updateMe({
                settings: {
                    ...user.settings,
                    max_concurrent_lm_studio_calls: systemMaxConcurrentLmCalls,
                },
            });
            await checkAuth({ silent: true });
            setCommittedSystemMaxConcurrentLmCalls(systemMaxConcurrentLmCalls);
            setSuccess('System settings saved.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to save system settings');
        } finally {
            setIsSavingSystem(false);
        }
    };

    const handleDisassociateGoogle = async () => {
        setError(null);
        setSuccess(null);
        setIsDisassociating(true);
        try {
            await AuthClient.disassociateGoogle();
            await checkAuth({ silent: true });
            setSuccess('Google account disassociated.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to disassociate');
        } finally {
            setIsDisassociating(false);
        }
    };

    const handleConnectWorkflowGoogle = async () => {
        setError(null);
        setSuccess(null);
        setWorkflowGoogleConnecting(true);
        try {
            const { redirect_url: url } = await ApiClient.postGoogleWorkflowAuthorize();
            window.location.href = url;
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to start Google workflow connection');
            setWorkflowGoogleConnecting(false);
        }
    };

    const handleSaveGmailWorkflowFilters = async () => {
        if (!user) return;
        setIsSavingGmailFilters(true);
        setError(null);
        setSuccess(null);
        try {
            const list = GMAIL_EXCLUDABLE_CATEGORY_SLUGS.filter(s => gmailWorkflowExclude.has(s));
            await AuthClient.updateMe({
                settings: {
                    ...user.settings,
                    gmail_workflow_inbox_focus: gmailWorkflowInboxFocus,
                    gmail_workflow_exclude_categories: list,
                },
            });
            await checkAuth({ silent: true });
            setSuccess('Gmail workflow filters saved.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to save gmail filters');
        } finally {
            setIsSavingGmailFilters(false);
        }
    };

    const handleDisconnectWorkflowGoogle = async (connectionId: string) => {
        setError(null);
        setSuccess(null);
        try {
            await ApiClient.deleteGoogleWorkflowConnection(connectionId);
            setWorkflowGoogleConnections(prev => prev.filter(c => c.id !== connectionId));
            setSuccess('Google workflow connection removed.');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to remove connection');
        }
    };

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="My Settings" maxWidth="4xl">
            <div className="flex flex-1 overflow-hidden">
                <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {sidebarSections.map(s => (
                            <div
                                key={s.id}
                                className={`flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${selectedSection === s.id ? 'bg-mw-primary-muted border border-mw-primary' : 'hover:bg-mw-card border border-transparent'}`}
                                onClick={() => setSelectedSection(s.id)}
                            >
                                <span className="text-mw-text-secondary shrink-0">{s.icon}</span>
                                <span className="text-sm font-medium text-mw-text-primary truncate">{s.label}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                    {error && <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg mb-4">{error}</div>}
                    {success && <div className="text-sm text-mw-success bg-mw-success-muted border border-mw-success px-3 py-2 rounded-lg mb-4">{success}</div>}

                    {selectedSection === 'view' && (
                        <div className="space-y-4 max-w-xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                View Settings
                            </h3>
                            <p className="text-sm text-mw-text-secondary">
                                App appearance, system theme, and default workflow palette for new workflows.
                            </p>
                            {viewPalettesLoading && (
                                <p className="text-sm text-mw-text-secondary">Loading palettes…</p>
                            )}
                            <div>
                                <label htmlFor="view-appearance" className={labelCls}>
                                    Appearance
                                </label>
                                <select
                                    id="view-appearance"
                                    value={viewThemeMode}
                                    onChange={e =>
                                        setViewThemeMode(e.target.value as ThemeModeSetting)
                                    }
                                    className={inputCls}
                                >
                                    <option value="system">System (match device)</option>
                                    <option value="light">Light</option>
                                    <option value="dark">Dark</option>
                                </select>
                            </div>
                            <div>
                                <label htmlFor="view-system-palette" className={labelCls}>
                                    System palette
                                </label>
                                <select
                                    id="view-system-palette"
                                    value={viewSystemPaletteId}
                                    onChange={e => setViewSystemPaletteId(e.target.value)}
                                    className={inputCls}
                                    disabled={viewPalettesLoading}
                                >
                                    <option value="">None (defaults + optional color overrides only)</option>
                                    {systemPaletteOptions.map(p => (
                                        <option key={p.id} value={p.id}>
                                            {p.name}
                                            {p.user_id == null ? ' (built-in)' : ''}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label htmlFor="view-editor-palette" className={labelCls}>
                                    Preferred editor palette
                                </label>
                                <p className="text-xs text-mw-text-secondary mb-1">
                                    Applied when you create a new workflow.
                                </p>
                                <select
                                    id="view-editor-palette"
                                    value={viewEditorPaletteId}
                                    onChange={e => setViewEditorPaletteId(e.target.value)}
                                    className={inputCls}
                                    disabled={viewPalettesLoading}
                                >
                                    <option value="">Default (built-in)</option>
                                    {workflowPaletteOptions.map(p => (
                                        <option key={p.id} value={p.id}>
                                            {p.name}
                                            {p.user_id == null ? ' (built-in)' : ''}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-start gap-3">
                                <input
                                    id="view-remember-workflow-panel-widths"
                                    type="checkbox"
                                    checked={viewRememberWorkflowPanelWidths}
                                    onChange={e => setViewRememberWorkflowPanelWidths(e.target.checked)}
                                    className="mt-1 h-4 w-4 rounded border-mw-border text-mw-primary focus:ring-mw-primary"
                                />
                                <div>
                                    <label
                                        htmlFor="view-remember-workflow-panel-widths"
                                        className={`${labelCls} cursor-pointer`}
                                    >
                                        Remember workflow editor panel widths for each workflow
                                    </label>
                                    <p className="text-xs text-mw-text-secondary mt-1">
                                        When off, panel sizes reset when you change workflows and are not saved in the
                                        browser.
                                    </p>
                                </div>
                            </div>
                            <div>
                                <label
                                    htmlFor="view-tts-playback-when"
                                    className={`${labelCls} block mb-1`}
                                >
                                    Text-to-Speech playback during workflow runs
                                </label>
                                <select
                                    id="view-tts-playback-when"
                                    value={viewTtsPlaybackWhen}
                                    onChange={e => setViewTtsPlaybackWhen(e.target.value as TtsPlaybackWhen)}
                                    className={`${inputCls} w-full max-w-md`}
                                >
                                    <option value="inline">When each node finishes (inline)</option>
                                    <option value="manual">Manual only (use the run log player)</option>
                                    <option value="after_workflow">After the workflow completes (queue, play in order)</option>
                                </select>
                                <p className="text-xs text-mw-text-secondary mt-1">
                                    Default for Text-to-Speech nodes that follow &quot;My Settings&quot;. You can override
                                    each node in the inspector. Run log play and download stay available for every clip.
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => void handleSaveViewSettings()}
                                disabled={isSavingView}
                                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50"
                            >
                                <Save size={16} />
                                Save view settings
                            </button>
                        </div>
                    )}

                    {selectedSection === 'system' && (
                        <div className="space-y-4 max-w-xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                System Settings
                            </h3>
                            <div className="rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 p-4 space-y-3">
                                <div>
                                    <div className="flex items-center gap-1 mb-1">
                                        <label
                                            htmlFor="system-max-concurrent-lm"
                                            className="text-xs font-medium text-mw-text-secondary cursor-default"
                                        >
                                            Max concurrent LM Studio calls
                                        </label>
                                        <ContextHelpModal
                                            title="Max concurrent LM Studio calls"
                                            triggerLabel="Help: max concurrent LM Studio calls"
                                        >
                                            <div className="space-y-2 text-mw-text-secondary leading-relaxed">
                                                <p>
                                                    Control how many workflow steps run at once when many nodes become
                                                    ready in parallel (for example, several LLM calls to LM Studio).
                                                    Lower values reduce load; higher values may run faster when your
                                                    machine can handle it.
                                                </p>
                                                <p>
                                                    If a <strong className="text-mw-text-primary">For Loop</strong> uses
                                                    parallel iterations, this value also limits how many iterations start
                                                    at once (so a long list does not overwhelm LM Studio).
                                                </p>
                                            </div>
                                        </ContextHelpModal>
                                    </div>
                                    <p className="text-xs text-mw-text-secondary mb-1">
                                        Default {MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT}. Allowed{' '}
                                        {MAX_CONCURRENT_LM_STUDIO_CALLS_MIN}–{MAX_CONCURRENT_LM_STUDIO_CALLS_MAX}.
                                    </p>
                                    <input
                                        id="system-max-concurrent-lm"
                                        type="number"
                                        min={MAX_CONCURRENT_LM_STUDIO_CALLS_MIN}
                                        max={MAX_CONCURRENT_LM_STUDIO_CALLS_MAX}
                                        step={1}
                                        value={systemMaxConcurrentLmCalls}
                                        onChange={e => {
                                            const v = parseInt(e.target.value, 10);
                                            if (Number.isNaN(v)) return;
                                            setSystemMaxConcurrentLmCalls(
                                                Math.max(
                                                    MAX_CONCURRENT_LM_STUDIO_CALLS_MIN,
                                                    Math.min(MAX_CONCURRENT_LM_STUDIO_CALLS_MAX, v),
                                                ),
                                            );
                                        }}
                                        className={inputCls}
                                    />
                                </div>
                                {systemConcurrentDirty && (
                                    <button
                                        type="button"
                                        onClick={() => void handleSaveSystemSettings()}
                                        disabled={isSavingSystem}
                                        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50"
                                    >
                                        <Save size={16} />
                                        Save system settings
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {selectedSection === 'profile' && (
                        <div className="space-y-4 max-w-xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">My Profile</h3>
                            <div className="flex items-center gap-4">
                                <div className="relative">
                                    <UserAvatar username={user.username} avatarUrl={avatarUrl} size="lg" />
                                    <label className="absolute bottom-0 right-0 bg-mw-primary text-white rounded-full p-1 cursor-pointer hover:bg-mw-primary-hover">
                                        <input
                                            type="file"
                                            accept="image/*"
                                            onChange={handleAvatarChange}
                                            className="sr-only"
                                        />
                                        <Upload size={14} />
                                    </label>
                                </div>
                                <div className="flex-1">
                                    <p className="font-medium text-mw-text-primary">{user.username}</p>
                                    <p className="text-sm text-mw-text-secondary">{user.is_admin ? 'Administrator' : 'User'}</p>
                                    <button onClick={logout} className="mt-2 px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors">
                                        Sign Out
                                    </button>
                                </div>
                            </div>
                            <div className="border-t border-mw-border pt-4 space-y-2">
                                <div className="flex items-center gap-1 mb-1">
                                    <label htmlFor="profile-workflow-tz" className="text-xs font-medium text-mw-text-secondary">
                                        Timezone
                                    </label>
                                    <ContextHelpModal title="Timezone" triggerLabel="Timezone help">
                                        <div className="space-y-2 text-mw-text-secondary leading-relaxed">
                                            <p>
                                                Used for Gmail and Calendar <strong className="text-mw-text-primary">date and time</strong>{' '}
                                                pickers in the workflow editor, Calendar{' '}
                                                <strong className="text-mw-text-primary">Skill Explorer</strong> formatting, and Gmail{' '}
                                                <code className="font-mono text-[10px] text-mw-text-primary">after:</code> /{' '}
                                                <code className="font-mono text-[10px] text-mw-text-primary">before:</code> day boundaries
                                                when you run from this browser.
                                            </p>
                                            <p>
                                                <strong className="text-mw-text-primary">System default</strong> follows this
                                                device&apos;s zone ({getSystemTimeZone()}).
                                            </p>
                                        </div>
                                    </ContextHelpModal>
                                </div>
                                <div className="relative">
                                    <select
                                        id="profile-workflow-tz"
                                        value={profileWorkflowTimeZone}
                                        onChange={e => setProfileWorkflowTimeZone(e.target.value)}
                                        className={`${inputCls} max-h-40 w-full appearance-none pr-10`}
                                    >
                                        <option value="system">System default ({getSystemTimeZone()})</option>
                                        {ianaZoneOptions.map(z => (
                                            <option key={z} value={z}>
                                                {z}
                                            </option>
                                        ))}
                                    </select>
                                    <ChevronDown
                                        aria-hidden
                                        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-mw-text-secondary shrink-0"
                                        strokeWidth={2}
                                    />
                                </div>
                                {profileTimezoneDirty && (
                                    <button
                                        type="button"
                                        onClick={() => void handleSaveProfileTimezone()}
                                        disabled={isSavingProfileTz}
                                        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50"
                                    >
                                        <Save size={16} />
                                        Save
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {selectedSection === 'google' && (
                        <div className="space-y-4 max-w-xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">Google Account</h3>
                            {user.google_email ? (
                                <div className="flex justify-between items-center">
                                    <div>
                                        <p className="text-sm text-mw-text-secondary">Linked to</p>
                                        <p className="font-medium text-mw-text-primary">{user.google_email}</p>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={handleDisassociateGoogle}
                                        disabled={isDisassociating}
                                        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors disabled:opacity-50"
                                    >
                                        <Unlink size={16} />
                                        Disassociate
                                    </button>
                                </div>
                            ) : (
                                <div className="flex justify-between items-center">
                                    <p className="text-sm text-mw-text-secondary">Link your Google account for sign-in.</p>
                                    <button
                                        type="button"
                                        onClick={handleAssociateGoogle}
                                        disabled={isAssociating}
                                        className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg transition-colors disabled:opacity-50"
                                    >
                                        <Link2 size={16} />
                                        Associate Google Account
                                    </button>
                                </div>
                            )}

                            <div className="border-t border-mw-border pt-4 mt-6 space-y-3">
                                <h4 className="text-sm font-semibold text-mw-text-primary">Google for workflows</h4>
                                <p className="text-xs text-mw-text-secondary">
                                    Separate from sign-in: grant read-only Gmail and Calendar so workflow skills can list
                                    messages and events. You can connect multiple Google accounts (e.g. work and personal).
                                </p>
                                {workflowGoogleLoading ? (
                                    <p className="text-xs text-mw-text-secondary">Loading connections…</p>
                                ) : (
                                    <ul className="space-y-2">
                                        {workflowGoogleConnections.map(c => (
                                            <li
                                                key={c.id}
                                                className="flex flex-wrap items-center justify-between gap-2 text-sm border border-mw-border rounded-lg px-3 py-2"
                                            >
                                                <div>
                                                    <span className="text-mw-text-primary font-medium">
                                                        {c.label?.trim() || c.google_email || 'Google account'}
                                                    </span>
                                                    {c.google_email ? (
                                                        <span className="block text-xs text-mw-text-secondary">
                                                            {c.google_email}
                                                        </span>
                                                    ) : null}
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => void handleDisconnectWorkflowGoogle(c.id)}
                                                    className="flex items-center gap-1 px-2 py-1 text-xs text-mw-text-secondary hover:bg-mw-card-alt rounded"
                                                >
                                                    <Unlink size={14} />
                                                    Disconnect
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                                <button
                                    type="button"
                                    onClick={() => void handleConnectWorkflowGoogle()}
                                    disabled={workflowGoogleConnecting}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg transition-colors disabled:opacity-50"
                                >
                                    <Link2 size={16} />
                                    Connect Google for workflows
                                </button>
                            </div>

                            <div className="border-t border-mw-border pt-4 mt-6 space-y-3">
                                <h4 className="text-sm font-semibold text-mw-text-primary">Gmail workflow filters</h4>
                                <p className="text-xs text-mw-text-secondary leading-relaxed">
                                    Default <code className="text-[10px] font-mono">category:</code> clauses merged into{' '}
                                    <strong className="text-mw-text-primary">Gmail List Messages</strong>{' '}
                                    <code className="text-[10px] font-mono">q</code> for every workflow run, unless a node
                                    skips account filters or overrides categories in the inspector.
                                </p>
                                <div>
                                    <label className={labelCls}>Inbox focus (default)</label>
                                    <select
                                        value={gmailWorkflowInboxFocus}
                                        onChange={e =>
                                            setGmailWorkflowInboxFocus(e.target.value === 'primary' ? 'primary' : 'off')
                                        }
                                        className={inputCls}
                                    >
                                        <option value="off">All categories</option>
                                        <option value="primary">Primary only</option>
                                    </select>
                                </div>
                                <div>
                                    <div className={labelCls}>Exclude categories (default)</div>
                                    <p className="text-[11px] text-mw-text-secondary mb-2">
                                        Adds <code className="text-[10px] font-mono">-category:…</code> for each (ignored
                                        when inbox focus is Primary only).
                                    </p>
                                    <div
                                        className={`space-y-1.5 pl-0.5 ${gmailWorkflowInboxFocus === 'primary' ? 'opacity-50 pointer-events-none' : ''}`}
                                    >
                                        {GMAIL_EXCLUDABLE_CATEGORY_SLUGS.map((slug: GmailExcludableCategory) => (
                                            <label key={slug} className="flex items-center gap-2 cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    className="rounded border-mw-border"
                                                    checked={gmailWorkflowExclude.has(slug)}
                                                    onChange={e => {
                                                        setGmailWorkflowExclude(prev => {
                                                            const n = new Set(prev);
                                                            if (e.target.checked) n.add(slug);
                                                            else n.delete(slug);
                                                            return n;
                                                        });
                                                    }}
                                                />
                                                <span className="text-sm text-mw-text-primary">
                                                    {GMAIL_CATEGORY_LABELS[slug]}
                                                </span>
                                            </label>
                                        ))}
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => void handleSaveGmailWorkflowFilters()}
                                    disabled={isSavingGmailFilters}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg transition-colors disabled:opacity-50"
                                >
                                    <Save size={16} />
                                    Save Gmail filters
                                </button>
                            </div>
                        </div>
                    )}

                    {selectedSection === 'tts' && user.is_admin && (
                        <div className="space-y-4 max-w-2xl">
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">
                                TTS models
                            </h3>
                            <p className="text-sm text-mw-text-secondary">
                                Register Hugging Face repos for the local TTS bridge. Adding a model downloads weights on the
                                server running the bridge (may take a long time and significant disk space). All users can
                                use models in <span className="text-mw-text-primary">ready</span> status in workflows.
                            </p>
                            <div className="rounded-lg border border-mw-border bg-mw-page/90 dark:bg-mw-card-alt/25 p-4 space-y-3">
                                <h4 className="text-sm font-semibold text-mw-text-primary">Add model</h4>
                                <div>
                                    <label className={labelCls}>Display name</label>
                                    <input
                                        className={inputCls}
                                        value={ttsDisplayName}
                                        onChange={e => setTtsDisplayName(e.target.value)}
                                        placeholder="e.g. Qwen3 TTS VoiceDesign"
                                    />
                                </div>
                                <div>
                                    <label className={labelCls}>Engine</label>
                                    <select
                                        className={inputCls}
                                        value={ttsEngine}
                                        onChange={e => setTtsEngine(e.target.value as 'qwen_torch' | 'qwen_mlx')}
                                    >
                                        <option value="qwen_torch">qwen_torch (PyTorch / MPS)</option>
                                        <option value="qwen_mlx">qwen_mlx (stub — may 501)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className={labelCls}>Hugging Face repo id</label>
                                    <input
                                        className={inputCls}
                                        value={ttsRepoId}
                                        onChange={e => setTtsRepoId(e.target.value)}
                                        placeholder="org/model-name"
                                    />
                                </div>
                                <div>
                                    <label className={labelCls}>Revision (optional)</label>
                                    <input
                                        className={inputCls}
                                        value={ttsRevision}
                                        onChange={e => setTtsRevision(e.target.value)}
                                        placeholder="branch or commit — leave empty for default"
                                    />
                                </div>
                                <button
                                    type="button"
                                    disabled={ttsBusyId === '__create__' || !ttsDisplayName.trim() || !ttsRepoId.trim()}
                                    onClick={() => {
                                        setError(null);
                                        setSuccess(null);
                                        setTtsBusyId('__create__');
                                        void (async () => {
                                            try {
                                                await ApiClient.createTtsModel({
                                                    display_name: ttsDisplayName.trim(),
                                                    engine: ttsEngine,
                                                    source: {
                                                        kind: 'huggingface_repo',
                                                        repo_id: ttsRepoId.trim(),
                                                        revision: ttsRevision.trim() || null,
                                                    },
                                                });
                                                setTtsDisplayName('');
                                                setTtsRepoId('');
                                                setTtsRevision('');
                                                setSuccess('TTS model registered and pulled.');
                                                const rows = await ApiClient.getTtsModelsRegistry();
                                                setTtsRegistry(rows);
                                            } catch (err: unknown) {
                                                setError(err instanceof Error ? err.message : 'Failed to add TTS model');
                                            } finally {
                                                setTtsBusyId(null);
                                            }
                                        })();
                                    }}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50"
                                >
                                    <Volume2 size={16} />
                                    {ttsBusyId === '__create__' ? 'Pulling…' : 'Register & pull'}
                                </button>
                            </div>
                            <div>
                                <h4 className="text-sm font-semibold text-mw-text-primary mb-2">Registered models</h4>
                                {ttsLoading ? (
                                    <p className="text-sm text-mw-text-secondary">Loading…</p>
                                ) : ttsRegistry.length === 0 ? (
                                    <p className="text-sm text-mw-text-secondary">No models yet.</p>
                                ) : (
                                    <ul className="space-y-2">
                                        {ttsRegistry.map(m => (
                                            <li
                                                key={m.id}
                                                className="flex flex-wrap items-center justify-between gap-2 rounded border border-mw-border px-3 py-2 text-sm"
                                            >
                                                <div>
                                                    <div className="font-medium text-mw-text-primary">{m.display_name}</div>
                                                    <div className="text-xs text-mw-text-secondary">
                                                        {m.engine} · {m.status}
                                                        {m.error_message ? ` · ${m.error_message}` : ''}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1">
                                                    <button
                                                        type="button"
                                                        title="Re-pull"
                                                        disabled={ttsBusyId === m.id}
                                                        onClick={() => {
                                                            setError(null);
                                                            setSuccess(null);
                                                            setTtsBusyId(m.id);
                                                            void (async () => {
                                                                try {
                                                                    await ApiClient.pullTtsModel(m.id);
                                                                    setSuccess('Pull completed.');
                                                                    setTtsRegistry(await ApiClient.getTtsModelsRegistry());
                                                                } catch (err: unknown) {
                                                                    setError(
                                                                        err instanceof Error ? err.message : 'Pull failed',
                                                                    );
                                                                } finally {
                                                                    setTtsBusyId(null);
                                                                }
                                                            })();
                                                        }}
                                                        className="p-1.5 rounded hover:bg-mw-card-alt text-mw-text-secondary"
                                                    >
                                                        <RefreshCw size={16} />
                                                    </button>
                                                    <button
                                                        type="button"
                                                        title="Delete"
                                                        disabled={ttsBusyId === m.id}
                                                        onClick={() => {
                                                            if (!window.confirm(`Remove “${m.display_name}” from the registry?`)) return;
                                                            setError(null);
                                                            setSuccess(null);
                                                            setTtsBusyId(m.id);
                                                            void (async () => {
                                                                try {
                                                                    await ApiClient.deleteTtsModel(m.id);
                                                                    setSuccess('Model removed.');
                                                                    setTtsRegistry(await ApiClient.getTtsModelsRegistry());
                                                                } catch (err: unknown) {
                                                                    setError(
                                                                        err instanceof Error ? err.message : 'Delete failed',
                                                                    );
                                                                } finally {
                                                                    setTtsBusyId(null);
                                                                }
                                                            })();
                                                        }}
                                                        className="p-1.5 rounded hover:bg-red-500/10 text-red-500"
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                </div>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        </div>
                    )}

                    {selectedSection === 'api' && (
                        <div
                            className="space-y-4 max-w-xl"
                            key={`api-keys-${user.id}`}
                        >
                            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">API Settings</h3>
                            <p className="text-sm text-mw-text-secondary">
                                Keys are stored encrypted. Type a new value and save to set or replace a key; leave blank to keep the existing stored key.
                            </p>
                            <div>
                                <label className={labelCls} htmlFor="mw-api-lmstudio">LM Studio API Key</label>
                                <p className="text-xs text-mw-text-secondary mt-0.5 mb-1">
                                    Paste the token only (not the word <span className="font-mono">Bearer</span>).
                                </p>
                                <input
                                    id="mw-api-lmstudio"
                                    ref={lmstudioApiKeyInputRef}
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder={
                                        user.api_keys?.['lmstudio_api_key'] === '[stored]'
                                            ? 'Key on file — type a new key to replace'
                                            : 'Paste your LM Studio server API key'
                                    }
                                    className={inputCls}
                                />
                            </div>
                            <div>
                                <label className={labelCls} htmlFor="mw-api-openai">OpenAI API Key</label>
                                <input
                                    id="mw-api-openai"
                                    ref={openaiApiKeyInputRef}
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder={user.api_keys?.['openai'] === '[stored]' ? 'Key on file — type to replace' : ''}
                                    className={inputCls}
                                />
                            </div>
                            <div>
                                <label className={labelCls} htmlFor="mw-api-anthropic">Anthropic API Key</label>
                                <input
                                    id="mw-api-anthropic"
                                    ref={anthropicApiKeyInputRef}
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder={user.api_keys?.['anthropic'] === '[stored]' ? 'Key on file — type to replace' : ''}
                                    className={inputCls}
                                />
                            </div>
                            <div>
                                <label className={labelCls} htmlFor="mw-api-google">Google API Key</label>
                                <input
                                    id="mw-api-google"
                                    ref={googleApiKeyInputRef}
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder={user.api_keys?.['google'] === '[stored]' ? 'Key on file — type to replace' : ''}
                                    className={inputCls}
                                />
                            </div>
                            <div>
                                <label className={labelCls} htmlFor="mw-api-assemblyai">AssemblyAI API Key</label>
                                <input
                                    id="mw-api-assemblyai"
                                    ref={assemblyaiApiKeyInputRef}
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder={user.api_keys?.['assemblyai'] === '[stored]' ? 'Key on file — type to replace' : ''}
                                    className={inputCls}
                                />
                            </div>
                            <button type="button" onClick={handleSaveSettings} disabled={isSaving} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50">
                                <Save size={16} />
                                Save Settings
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </ManagerModal>
    );
};
