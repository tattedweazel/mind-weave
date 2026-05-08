/**
 * App
 * ===
 * Top-level application shell.
 *
 * Views:
 *   home      — landing / empty state (only when Workspace UI is disabled)
 *   workspace — Companion chat (when Workspace UI is enabled; top nav item)
 *   workflows — WorkflowEditor (visual DAG editor)
 *
 * Modals:
 *   PersonaManager — create / edit / delete Personas
 *   PaletteManager — create / edit / delete Palettes
 *   StructureManager — create / edit / delete Structures
 *   DocumentManager — create / edit / delete Documents (persisted body text)
 *   VoiceManager — Voice Sample Manager: Voice Design previews + saved clone references
 *   UserManagement — admin only: create / manage users
 *   MySettings — user profile, Google, API keys, avatar
 *   RunExploreModal (Replays) — browse and inspect past workflow runs (read-only graph)
 */

import React, { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { Braces, FileText, History, LayoutGrid, Loader2, MessageSquare, Mic, Users, PanelLeft, Workflow } from 'lucide-react';

const PersonaManager = lazy(() => import('./components/PersonaManager').then(m => ({ default: m.PersonaManager })));
const PaletteManager = lazy(() => import('./components/PaletteManager').then(m => ({ default: m.PaletteManager })));
const StructureManager = lazy(() => import('./components/StructureManager').then(m => ({ default: m.StructureManager })));
const DocumentManager = lazy(() => import('./components/DocumentManager').then(m => ({ default: m.DocumentManager })));
const VoiceManager = lazy(() => import('./components/VoiceManager').then(m => ({ default: m.VoiceManager })));
const WorkflowEditor = lazy(() => import('./components/WorkflowEditor'));
const RunExploreModal = lazy(() => import('./components/RunExploreModal'));
const SandboxView = lazy(() => import('./components/SandboxView').then(m => ({ default: m.SandboxView })));
const WorkspaceView = lazy(() => import('./components/WorkspaceView').then(m => ({ default: m.WorkspaceView })));
const UserManagement = lazy(() => import('./components/auth/UserManagement').then(m => ({ default: m.UserManagement })));
const MySettings = lazy(() => import('./components/auth/MySettings').then(m => ({ default: m.MySettings })));
import { Login } from './components/auth/Login';
import { UserAvatar } from './components/UserAvatar';
import { useAuth } from './contexts/AuthContext';
import { useCompactViewport } from './hooks/useCompactViewport';
import {
    interpretParsedPath,
    parseAppPathname,
    pathForTopLevelView,
    pathForWorkflowEditor,
} from './appUrlState';

type ActiveView = 'home' | 'workflows' | 'sandbox' | 'workspace';

const SANDBOX_UI_ENABLED = import.meta.env.VITE_SANDBOX_ENABLED !== 'false';
const WORKSPACE_UI_ENABLED = import.meta.env.VITE_WORKSPACE_ENABLED !== 'false';

const URL_SHELL_FLAGS = { workspaceEnabled: WORKSPACE_UI_ENABLED, sandboxEnabled: SANDBOX_UI_ENABLED };

const NavItem: React.FC<{
    id: ActiveView;
    icon: React.ReactNode;
    label: string;
    activeView: ActiveView;
    isSidebarOpen: boolean;
    onNav: (id: ActiveView) => void;
}> = ({ id, icon, label, activeView, isSidebarOpen, onNav }) => (
    <button
        id={`nav-${id}`}
        onClick={() => onNav(id)}
        title={label}
        className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${activeView === id
            ? 'bg-mw-primary-muted text-mw-primary'
            : 'text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary'
            }`}
    >
        {icon}
        {isSidebarOpen && <span>{label}</span>}
    </button>
);

const GOOGLE_TOAST_MESSAGES: Record<string, string> = {
    google_associated: 'Google account linked successfully.',
    google_error_denied: 'Google authorization was denied.',
    google_error_expired: 'Google authorization expired. Please try again.',
    google_error_missing_params: 'Google authorization failed: missing parameters.',
    google_error_exchange_failed: 'Google authorization failed. Please try again.',
    google_error_already_linked: 'This Google account is already linked to another user.',
    google_error_no_account: 'No Mind Weave account is linked to this Google account.',
    google_error_not_configured: 'Google sign-in is not configured.',
    google_error_session_exchange_failed:
        'Could not complete Google sign-in. Check that the frontend API URL matches your backend (see VITE_API_BASE).',
    google_workflow_connected: 'Google account connected for workflows (Gmail / Calendar).',
    google_error_workflow_denied: 'Google workflow connection was denied.',
    google_error_workflow_missing_params: 'Google workflow connection failed: missing parameters.',
    google_error_workflow_expired: 'Google workflow connection expired. Try again.',
    google_error_workflow_exchange_failed: 'Google workflow connection failed during token exchange.',
    google_error_workflow_no_refresh: 'Google did not return a refresh token. Try reconnecting with consent.',
    google_error_workflow_userinfo_failed: 'Could not read Google profile after connecting.',
};

function App() {
    performance.mark('mw:app-render');
    const { isAuthenticated, isLoading, checkAuth, user } = useAuth();
    const compactShell = useCompactViewport();
    const [googleToast, setGoogleToast] = useState<{ message: string; isError: boolean } | null>(null);

    // Handle Google OAuth callback query params
    useEffect(() => {
        if (!isAuthenticated) return;
        const params = new URLSearchParams(window.location.search);
        const wfOk = params.get('google_workflow_connected');
        if (wfOk === '1') {
            setGoogleToast({
                message: GOOGLE_TOAST_MESSAGES.google_workflow_connected,
                isError: false,
            });
            window.history.replaceState({}, '', window.location.pathname);
            return;
        }
        const associated = params.get('google_associated');
        const error = params.get('google_error');
        if (associated === '1') {
            void checkAuth({ silent: true });
            setGoogleToast({ message: GOOGLE_TOAST_MESSAGES.google_associated, isError: false });
            window.history.replaceState({}, '', window.location.pathname);
        } else if (error) {
            // Stale session_exchange_failed (e.g. duplicate effect / Strict Mode) while cookies are valid
            if (error === 'session_exchange_failed' && user) {
                window.history.replaceState({}, '', window.location.pathname);
                return;
            }
            void checkAuth({ silent: true });
            const key = `google_error_${error}`;
            const message = GOOGLE_TOAST_MESSAGES[key] || `Google authorization failed: ${error}`;
            setGoogleToast({ message, isError: true });
            window.history.replaceState({}, '', window.location.pathname);
        }
    }, [isAuthenticated, checkAuth, user]);

    // Clear toast after 4 seconds
    useEffect(() => {
        if (!googleToast) return;
        const t = setTimeout(() => setGoogleToast(null), 4000);
        return () => clearTimeout(t);
    }, [googleToast]);

    const initialShell = interpretParsedPath(parseAppPathname(window.location.pathname), URL_SHELL_FLAGS);

    const [activeView, setActiveView] = useState<ActiveView>(initialShell.activeView);
    const [urlWorkflowId, setUrlWorkflowId] = useState<string | null>(initialShell.urlWorkflowId);

    // Modals
    const [isPersonaManagerOpen, setIsPersonaManagerOpen] = useState(false);
    const [isPaletteManagerOpen, setIsPaletteManagerOpen] = useState(false);
    const [isStructureManagerOpen, setIsStructureManagerOpen] = useState(false);
    const [isDocumentManagerOpen, setIsDocumentManagerOpen] = useState(false);
    const [isVoiceManagerOpen, setIsVoiceManagerOpen] = useState(false);
    const [isUserManagerOpen, setIsUserManagerOpen] = useState(false);
    const [isMySettingsOpen, setIsMySettingsOpen] = useState(false);
    const [isRunExploreOpen, setIsRunExploreOpen] = useState(false);

    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    useEffect(() => {
        if (compactShell) setIsSidebarOpen(false);
    }, [compactShell]);
    const [paletteRevision, setPaletteRevision] = useState(0);

    // Unsaved changes state for the active view (e.g. WorkflowEditor)
    const [unsavedChanges, setUnsavedChanges] = useState(false);
    const [pendingNav, setPendingNav] = useState<ActiveView | null>(null);
    const [requestSave, setRequestSave] = useState(0); // Trigger to tell child to save

    /** Workflow Editor immersive mode: hide app sidebar + top bar; slide-over palette/Explorer. */
    const [workflowImmersive, setWorkflowImmersive] = useState(false);

    const activeViewRef = useRef(activeView);
    const unsavedRef = useRef(unsavedChanges);
    useEffect(() => {
        activeViewRef.current = activeView;
    }, [activeView]);
    useEffect(() => {
        unsavedRef.current = unsavedChanges;
    }, [unsavedChanges]);

    useEffect(() => {
        if (!initialShell.normalizePath) return;
        const q = window.location.search || '';
        window.history.replaceState({}, '', initialShell.normalizePath + q);
    }, []);

    useEffect(() => {
        if (activeView !== 'workflows') setWorkflowImmersive(false);
    }, [activeView]);

    useEffect(() => {
        const onPop = () => {
            let interpreted = interpretParsedPath(parseAppPathname(window.location.pathname), URL_SHELL_FLAGS);
            if (interpreted.normalizePath) {
                const q = window.location.search || '';
                window.history.replaceState({}, '', interpreted.normalizePath + q);
                interpreted = interpretParsedPath(parseAppPathname(window.location.pathname), URL_SHELL_FLAGS);
            }
            const nextView = interpreted.activeView;
            const nextWorkflowId = interpreted.urlWorkflowId;

            if (unsavedRef.current && activeViewRef.current === 'workflows' && nextView !== 'workflows') {
                window.history.forward();
                setPendingNav(nextView);
                return;
            }

            setActiveView(nextView);
            setUrlWorkflowId(nextView === 'workflows' ? nextWorkflowId : null);
        };
        window.addEventListener('popstate', onPop);
        return () => window.removeEventListener('popstate', onPop);
    }, []);

    const searchSuffix = useCallback(() => window.location.search || '', []);

    const navigateTopLevel = useCallback(
        (id: ActiveView) => {
            const path = pathForTopLevelView(id, { workspaceEnabled: WORKSPACE_UI_ENABLED });
            window.history.pushState({}, '', path + searchSuffix());
            setActiveView(id);
            setUrlWorkflowId(null);
        },
        [searchSuffix],
    );

    const attemptNav = useCallback(
        (id: ActiveView) => {
            if (id === activeView) {
                if (id === 'workflows' && urlWorkflowId != null) {
                    if (unsavedChanges && activeView === 'workflows') {
                        setPendingNav('workflows');
                    } else {
                        window.history.pushState({}, '', pathForWorkflowEditor(null) + searchSuffix());
                        setUrlWorkflowId(null);
                    }
                }
                return;
            }
            if (unsavedChanges && activeView === 'workflows' && id !== 'workflows') {
                setPendingNav(id);
                return;
            }
            navigateTopLevel(id);
        },
        [activeView, navigateTopLevel, searchSuffix, unsavedChanges, urlWorkflowId],
    );

    const onSyncWorkflowPath = useCallback((workflowId: string | null) => {
        window.history.replaceState({}, '', pathForWorkflowEditor(workflowId) + searchSuffix());
        setUrlWorkflowId(workflowId);
    }, [searchSuffix]);

    const completePendingTopLevelNav = useCallback(
        (target: ActiveView) => {
            const path = pathForTopLevelView(target, { workspaceEnabled: WORKSPACE_UI_ENABLED });
            window.history.pushState({}, '', path + searchSuffix());
            setActiveView(target);
            setUrlWorkflowId(null);
        },
        [searchSuffix],
    );

    // ------------------------------------------------------------------
    // Auth guard
    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-screen bg-mw-page">
                <Loader2 className="animate-spin text-mw-primary" size={36} />
            </div>
        );
    }
    if (!isAuthenticated) {
        return <Login />;
    }

    // ------------------------------------------------------------------
    const hideAppChromeForWorkflowImmersive = activeView === 'workflows' && workflowImmersive;

    // ------------------------------------------------------------------
    return (
        <div className="flex h-screen overflow-hidden bg-mw-page text-mw-text-primary">
            {/* Google OAuth toast */}
            {googleToast && (
                <div className={`fixed top-4 right-4 z-[60] px-4 py-3 rounded-lg shadow-lg max-w-sm border ${
                    googleToast.isError
                        ? 'bg-mw-error-muted text-mw-error border-mw-error'
                        : 'bg-mw-success-muted text-mw-success border-mw-success'
                }`}>
                    {googleToast.message}
                </div>
            )}

            {/* =================== Sidebar =================== */}
            {!hideAppChromeForWorkflowImmersive && (
            <aside className={`${isSidebarOpen ? 'w-56' : 'w-16'} shrink-0 border-r border-mw-border bg-mw-sidebar flex flex-col transition-all duration-200`}>

                {/* Logo + collapse (expanded only). Collapsed: toggle lives in nav so it lines up with icon column. */}
                {isSidebarOpen && (
                    <div className="h-14 flex items-center px-4 border-b border-mw-border gap-3 shrink-0">
                        <span className="text-base font-bold text-mw-text-primary truncate">Mind Weave</span>
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(false)}
                            title="Collapse sidebar"
                            className="ml-auto text-mw-text-secondary hover:text-mw-text-primary transition-colors shrink-0 p-1 rounded-lg hover:bg-mw-card-alt"
                        >
                            <PanelLeft size={18} />
                        </button>
                    </div>
                )}

                {/* Nav */}
                <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
                    {!isSidebarOpen && (
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(true)}
                            title="Expand sidebar"
                            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors"
                        >
                            <PanelLeft size={18} className="shrink-0" />
                        </button>
                    )}
                    {WORKSPACE_UI_ENABLED ? (
                        <NavItem id="workspace" icon={<MessageSquare size={18} />} label="Workspace" activeView={activeView} isSidebarOpen={isSidebarOpen} onNav={attemptNav} />
                    ) : (
                        <NavItem
                            id="home"
                            icon={
                                <svg
                                    width="18"
                                    height="18"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                                    <polyline points="9 22 9 12 15 12 15 22" />
                                </svg>
                            }
                            label="Home"
                            activeView={activeView}
                            isSidebarOpen={isSidebarOpen}
                            onNav={attemptNav}
                        />
                    )}

                    <div
                        className={`shrink-0 border-t-4 border-mw-border ${isSidebarOpen ? 'my-8' : 'my-14'}`}
                        aria-hidden
                    />
                    {isSidebarOpen && <div className="pt-4 pb-1 px-3 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide opacity-70">Build</div>}
                    <NavItem id="workflows" icon={<Workflow size={18} />} label="Workflows" activeView={activeView} isSidebarOpen={isSidebarOpen} onNav={attemptNav} />
                    {SANDBOX_UI_ENABLED && (
                        <NavItem id="sandbox" icon={<LayoutGrid size={18} />} label="Sandbox" activeView={activeView} isSidebarOpen={isSidebarOpen} onNav={attemptNav} />
                    )}
                    <button
                        id="nav-replays"
                        type="button"
                        onClick={() => setIsRunExploreOpen(true)}
                        title="Replays"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors"
                    >
                        <History size={18} className="shrink-0" />
                        {isSidebarOpen && <span>Replays</span>}
                    </button>

                    <div
                        className={`shrink-0 border-t-4 border-mw-border ${isSidebarOpen ? 'my-8' : 'my-14'}`}
                        aria-hidden
                    />
                    {isSidebarOpen && <div className="pt-4 pb-1 px-3 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide opacity-70">Configure</div>}
                    <button id="nav-personas" onClick={() => setIsPersonaManagerOpen(true)} title="Personas"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        {isSidebarOpen && <span>Personas</span>}
                    </button>
                    <button id="nav-structures" onClick={() => setIsStructureManagerOpen(true)} title="Structures"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                        <Braces size={18} className="shrink-0" aria-hidden />
                        {isSidebarOpen && <span>Structures</span>}
                    </button>
                    <button id="nav-documents" onClick={() => setIsDocumentManagerOpen(true)} title="Documents"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                        <FileText size={18} className="shrink-0" />
                        {isSidebarOpen && <span>Documents</span>}
                    </button>
                    <button id="nav-voice-samples" onClick={() => setIsVoiceManagerOpen(true)} title="Voice Sample Manager"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                        <Mic size={18} className="shrink-0" />
                        {isSidebarOpen && <span>Voice Sample Manager</span>}
                    </button>
                    <button id="nav-palettes" onClick={() => setIsPaletteManagerOpen(true)} title="Palettes"
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.648 0-.437-.18-.835-.437-1.125.29-.293.434-.652.434-1.125a1.64 1.64 0 0 0-1.649-1.649h-2.86a4.985 4.985 0 0 0-4.985 4.986 4.985 4.985 0 0 0 4.985 4.987h2.86a1.64 1.64 0 0 0 1.649-1.648 1.64 1.64 0 0 0-.434-1.125c.258-.29.437-.689.437-1.125a1.647 1.647 0 0 0-1.648-1.648z"/></svg>
                        {isSidebarOpen && <span>Palettes</span>}
                    </button>
                    {user?.is_admin && (
                        <button id="nav-users" onClick={() => setIsUserManagerOpen(true)} title="User Management"
                            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt hover:text-mw-text-primary transition-colors">
                            <Users size={18} />
                            {isSidebarOpen && <span>User Management</span>}
                        </button>
                    )}
                </nav>
            </aside>
            )}

            {/* =================== Main content =================== */}
            <main className="flex-1 flex flex-col overflow-hidden">
                {/* View header */}
                {!hideAppChromeForWorkflowImmersive && (
                <header className="h-14 border-b border-mw-border bg-mw-card flex items-center justify-between px-4 sm:px-6 shrink-0 min-w-0">
                    <h1 className="text-base font-semibold text-mw-text-primary">
                        {activeView === 'home' && 'Home'}
                        {activeView === 'workflows' && 'Workflow Editor'}
                        {activeView === 'sandbox' && 'Sandbox'}
                        {activeView === 'workspace' && 'Workspace'}
                    </h1>
                    {user && (
                        <button
                            onClick={() => setIsMySettingsOpen(true)}
                            className="rounded-full focus:outline-none focus:ring-2 focus:ring-mw-primary focus:ring-offset-2 focus:ring-offset-mw-card"
                            title="My Settings"
                        >
                            <UserAvatar
                                username={user.username}
                                avatarUrl={user.settings?.avatar_url as string | undefined}
                                size="sm"
                            />
                        </button>
                    )}
                </header>
                )}

                {/* View body */}
                <div className="flex-1 overflow-hidden">
                    {activeView === 'home' && (
                        <div className="h-full flex flex-col items-center justify-center text-mw-text-secondary gap-4">
                            <Workflow size={56} className="opacity-50" />
                            <div className="text-center">
                                <p className="text-lg font-semibold text-mw-text-secondary mb-1">Welcome to Mind Weave</p>
                                <p className="text-sm text-mw-text-primary">Create <button className="text-mw-primary hover:underline" onClick={() => setIsPersonaManagerOpen(true)}>Personas</button> and compose <button className="text-mw-success hover:underline" onClick={() => attemptNav('workflows')}>Workflows</button>.</p>
                            </div>
                        </div>
                    )}
                    {activeView === 'workflows' && (
                        <Suspense
                            fallback={
                                <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                                    <Loader2 className="animate-spin" size={24} />
                                    <span>Loading…</span>
                                </div>
                            }
                        >
                            <WorkflowEditor 
                                setUnsavedChanges={setUnsavedChanges} 
                                requestSave={requestSave} 
                                palettesRefreshKey={paletteRevision}
                                immersive={workflowImmersive}
                                onImmersiveChange={setWorkflowImmersive}
                                onOpenMySettings={() => setIsMySettingsOpen(true)}
                                routeWorkflowId={urlWorkflowId}
                                onSyncWorkflowPath={onSyncWorkflowPath}
                                onSaved={() => {
                                    setUnsavedChanges(false);
                                    if (pendingNav) {
                                        const target = pendingNav;
                                        setPendingNav(null);
                                        completePendingTopLevelNav(target);
                                    }
                                }}
                            />
                        </Suspense>
                    )}
                    {WORKSPACE_UI_ENABLED && activeView === 'workspace' && (
                        <Suspense
                            fallback={
                                <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                                    <Loader2 className="animate-spin" size={24} />
                                    <span>Loading…</span>
                                </div>
                            }
                        >
                            <WorkspaceView />
                        </Suspense>
                    )}
                    {SANDBOX_UI_ENABLED && activeView === 'sandbox' && (
                        <Suspense
                            fallback={
                                <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                                    <Loader2 className="animate-spin" size={24} />
                                    <span>Loading…</span>
                                </div>
                            }
                        >
                            <SandboxView />
                        </Suspense>
                    )}
                </div>
            </main>

            {/* =================== Modals =================== */}
            {isPersonaManagerOpen && (
                <Suspense fallback={null}>
                    <PersonaManager isOpen={isPersonaManagerOpen} onClose={() => setIsPersonaManagerOpen(false)} />
                </Suspense>
            )}
            {isPaletteManagerOpen && (
                <Suspense fallback={null}>
                    <PaletteManager
                        isOpen={isPaletteManagerOpen}
                        onClose={() => {
                            setIsPaletteManagerOpen(false);
                            setPaletteRevision(r => r + 1);
                        }}
                    />
                </Suspense>
            )}
            {isStructureManagerOpen && (
                <Suspense fallback={null}>
                    <StructureManager isOpen={isStructureManagerOpen} onClose={() => setIsStructureManagerOpen(false)} />
                </Suspense>
            )}
            {isDocumentManagerOpen && (
                <Suspense fallback={null}>
                    <DocumentManager isOpen={isDocumentManagerOpen} onClose={() => setIsDocumentManagerOpen(false)} />
                </Suspense>
            )}
            {isVoiceManagerOpen && (
                <Suspense fallback={null}>
                    <VoiceManager isOpen={isVoiceManagerOpen} onClose={() => setIsVoiceManagerOpen(false)} />
                </Suspense>
            )}
            {isUserManagerOpen && (
                <Suspense fallback={null}>
                    <UserManagement isOpen={isUserManagerOpen} onClose={() => setIsUserManagerOpen(false)} />
                </Suspense>
            )}
            {isMySettingsOpen && (
                <Suspense fallback={null}>
                    <MySettings isOpen={isMySettingsOpen} onClose={() => setIsMySettingsOpen(false)} />
                </Suspense>
            )}
            {isRunExploreOpen && (
                <Suspense fallback={null}>
                    <RunExploreModal isOpen={isRunExploreOpen} onClose={() => setIsRunExploreOpen(false)} />
                </Suspense>
            )}
            {/* Unsaved Changes Form */}
            {pendingNav && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm">
                    <div className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-sm p-6 space-y-4">
                        <h3 className="text-lg font-bold text-mw-text-primary">Unsaved Changes</h3>
                        <p className="text-sm text-mw-text-secondary">You have unsaved changes in your workflow. What would you like to do?</p>
                        <div className="flex flex-col gap-2 pt-2">
                            <button onClick={() => setRequestSave(Date.now())} className="w-full py-2.5 bg-mw-primary hover:bg-mw-primary-hover text-white rounded-lg text-sm font-medium transition-colors">Save and Continue</button>
                            <button onClick={() => {
                                if (!pendingNav) return;
                                const target = pendingNav;
                                setUnsavedChanges(false);
                                setPendingNav(null);
                                completePendingTopLevelNav(target);
                            }} className="w-full py-2.5 bg-mw-error-muted text-mw-error hover:opacity-90 rounded-lg text-sm font-medium transition-colors">Discard Changes</button>
                            <button onClick={() => setPendingNav(null)} className="w-full py-2.5 bg-mw-card-alt text-mw-text-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors">Cancel</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default App;
