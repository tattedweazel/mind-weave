/**
 * Workspace — chat with Companion (streaming turns).
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Boxes, GitBranch, Loader2, MessageSquare, MessageSquarePlus, Send, Settings2, Terminal } from 'lucide-react';

import { ApiClient } from '../api/client';
import type {
    Companion,
    WorkspaceBootstrapResponse,
    WorkspaceTurn,
    WorkspaceTurnDetail,
} from '../api/types';
import type {
    WorkspaceCapabilityProposalCap,
    WorkspaceStreamDoneMeta,
    WorkspaceStreamStageEvent,
} from '../api/workspaceStream';
import { CompanionSettingsModal } from './CompanionSettingsModal';
import { WorkspacePipelinePanel } from './WorkspacePipelinePanel';
import { WorkspaceSettingsModal } from './WorkspaceSettingsModal';

type ChatMessage = { role: 'user' | 'assistant'; content: string };

type PendingProposal = { proposalId: string; capabilities: WorkspaceCapabilityProposalCap[] };

export const WorkspaceView: React.FC = () => {
    const [bootstrap, setBootstrap] = useState<WorkspaceBootstrapResponse | null>(null);
    const [companion, setCompanion] = useState<Companion | null>(null);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const [memoryToast, setMemoryToast] = useState<string | null>(null);
    const [newChatBusy, setNewChatBusy] = useState(false);
    const [newChatError, setNewChatError] = useState<string | null>(null);
    const [pendingProposal, setPendingProposal] = useState<PendingProposal | null>(null);
    const [proposalBusy, setProposalBusy] = useState(false);
    const [workspacePanelTab, setWorkspacePanelTab] = useState<'chat' | 'console'>('chat');
    const [consoleTurns, setConsoleTurns] = useState<WorkspaceTurn[]>([]);
    const [consoleDetail, setConsoleDetail] = useState<WorkspaceTurnDetail | null>(null);
    const [consoleLoading, setConsoleLoading] = useState(false);
    const [consoleError, setConsoleError] = useState<string | null>(null);
    const [selectedConsoleTurnId, setSelectedConsoleTurnId] = useState('');
    const [pipelineOpen, setPipelineOpen] = useState(false);
    const [pipelineRunStages, setPipelineRunStages] = useState<WorkspaceStreamStageEvent[]>([]);
    const bottomRef = useRef<HTMLDivElement>(null);

    const onPipelineStage = useCallback((e: WorkspaceStreamStageEvent) => {
        setPipelineRunStages(prev => [...prev, e]);
    }, []);

    const onWorkspaceStreamDone = useCallback(
        (meta: WorkspaceStreamDoneMeta) => {
            if (meta.memory_proposed && meta.memory_proposed > 0) {
                setMemoryToast(
                    `Memory proposal: ${meta.memory_proposed} item(s) — review in Companion settings when available.`,
                );
            }
            if (meta.phase === 'completed' && meta.turn_id && bootstrap) {
                void (async () => {
                    try {
                        const { workspace, session } = bootstrap;
                        const [detail, list] = await Promise.all([
                            ApiClient.getWorkspaceTurn(workspace.id, session.id, meta.turn_id!),
                            ApiClient.listWorkspaceTurns(workspace.id, session.id),
                        ]);
                        setConsoleDetail(detail);
                        setConsoleTurns(list);
                        setSelectedConsoleTurnId(meta.turn_id!);
                    } catch {
                        /* Console prefetch is best-effort */
                    }
                })();
            }
        },
        [bootstrap],
    );

    useEffect(() => {
        let cancelled = false;
        performance.mark('mw:workspace-bootstrap-start');
        (async () => {
            try {
                const data = await ApiClient.postWorkspaceBootstrap();
                performance.mark('mw:workspace-bootstrap-done');
                if (!cancelled) {
                    setBootstrap(data);
                    setCompanion(data.companion);
                }
            } catch (e) {
                performance.mark('mw:workspace-bootstrap-done');
                if (!cancelled) {
                    setLoadError(e instanceof Error ? e.message : 'Could not load Workspace.');
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, sending]);

    useEffect(() => {
        if (!memoryToast) {
            return;
        }
        const t = setTimeout(() => setMemoryToast(null), 5000);
        return () => clearTimeout(t);
    }, [memoryToast]);

    useEffect(() => {
        if (!newChatError) {
            return;
        }
        const t = setTimeout(() => setNewChatError(null), 6000);
        return () => clearTimeout(t);
    }, [newChatError]);

    useEffect(() => {
        if (workspacePanelTab !== 'console' || !bootstrap) {
            return;
        }
        let cancelled = false;
        (async () => {
            setConsoleLoading(true);
            setConsoleError(null);
            try {
                const list = await ApiClient.listWorkspaceTurns(
                    bootstrap.workspace.id,
                    bootstrap.session.id,
                );
                if (cancelled) {
                    return;
                }
                setConsoleTurns(list);
                setSelectedConsoleTurnId(prev => {
                    if (prev && list.some(t => t.id === prev)) {
                        return prev;
                    }
                    return list[list.length - 1]?.id ?? '';
                });
            } catch (e) {
                if (!cancelled) {
                    setConsoleError(e instanceof Error ? e.message : 'Failed to load turns');
                }
            } finally {
                if (!cancelled) {
                    setConsoleLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [workspacePanelTab, bootstrap]);

    useEffect(() => {
        if (workspacePanelTab !== 'console' || !bootstrap || !selectedConsoleTurnId) {
            return;
        }
        let cancelled = false;
        (async () => {
            try {
                const d = await ApiClient.getWorkspaceTurn(
                    bootstrap.workspace.id,
                    bootstrap.session.id,
                    selectedConsoleTurnId,
                );
                if (!cancelled) {
                    setConsoleDetail(d);
                    setConsoleError(null);
                }
            } catch (e) {
                if (!cancelled) {
                    setConsoleError(e instanceof Error ? e.message : 'Failed to load turn detail');
                    setConsoleDetail(null);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [workspacePanelTab, bootstrap, selectedConsoleTurnId]);

    const send = useCallback(async () => {
        const text = input.trim();
        if (!text || !bootstrap || sending || pendingProposal) {
            return;
        }
        setInput('');
        setSending(true);
        setPendingProposal(null);
        setPipelineRunStages([]);
        setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);

        let acc = '';
        const wsId = bootstrap.workspace.id;
        const sessId = bootstrap.session.id;

        try {
            await ApiClient.streamWorkspaceTurn(
                wsId,
                sessId,
                text,
                chunk => {
                    acc += chunk;
                    setMessages(prev => {
                        const next = [...prev];
                        const last = next[next.length - 1];
                        if (last?.role === 'assistant') {
                            next[next.length - 1] = { role: 'assistant', content: acc };
                        }
                        return next;
                    });
                },
                onWorkspaceStreamDone,
                proposal => {
                    setPendingProposal({
                        proposalId: proposal.proposal_id,
                        capabilities: proposal.capabilities,
                    });
                },
                onPipelineStage,
            );
        } catch (e) {
            setPendingProposal(null);
            setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === 'assistant') {
                    next[next.length - 1] = {
                        role: 'assistant',
                        content: e instanceof Error ? e.message : 'Something went wrong.',
                    };
                }
                return next;
            });
        } finally {
            setSending(false);
        }
    }, [bootstrap, input, sending, pendingProposal, onWorkspaceStreamDone, onPipelineStage]);

    const resolveProposal = useCallback(
        async (cancel: boolean) => {
            if (!bootstrap || !pendingProposal || proposalBusy) {
                return;
            }
            setProposalBusy(true);
            const wsId = bootstrap.workspace.id;
            const sessId = bootstrap.session.id;
            let acc = '';
            setPipelineRunStages([]);
            setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
            try {
                await ApiClient.streamWorkspaceConfirm(
                    wsId,
                    sessId,
                    { proposal_id: pendingProposal.proposalId, cancel },
                    chunk => {
                        acc += chunk;
                        setMessages(prev => {
                            const next = [...prev];
                            const last = next[next.length - 1];
                            if (last?.role === 'assistant') {
                                next[next.length - 1] = { role: 'assistant', content: acc };
                            }
                            return next;
                        });
                    },
                    onWorkspaceStreamDone,
                    onPipelineStage,
                );
            } catch (e) {
                setMessages(prev => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    if (last?.role === 'assistant') {
                        next[next.length - 1] = {
                            role: 'assistant',
                            content: e instanceof Error ? e.message : 'Something went wrong.',
                        };
                    }
                    return next;
                });
            } finally {
                setPendingProposal(null);
                setProposalBusy(false);
            }
        },
        [bootstrap, pendingProposal, proposalBusy, onWorkspaceStreamDone, onPipelineStage],
    );

    const startNewChat = useCallback(async () => {
        if (!bootstrap || newChatBusy || sending || pendingProposal || proposalBusy) {
            return;
        }
        setNewChatBusy(true);
        setNewChatError(null);
        try {
            const sess = await ApiClient.createWorkspaceSession(bootstrap.workspace.id, { title: 'Chat' });
            setBootstrap(prev => (prev ? { ...prev, session: sess } : null));
            setMessages([]);
            setPendingProposal(null);
            setProposalBusy(false);
            setConsoleTurns([]);
            setConsoleDetail(null);
            setSelectedConsoleTurnId('');
            setInput('');
        } catch (e) {
            setNewChatError(e instanceof Error ? e.message : 'Could not start a new chat.');
        } finally {
            setNewChatBusy(false);
        }
    }, [bootstrap, newChatBusy, sending, pendingProposal, proposalBusy]);

    if (loadError) {
        return (
            <div className="h-full flex items-center justify-center text-mw-error px-6 text-center">
                {loadError}
            </div>
        );
    }

    if (!bootstrap) {
        return (
            <div className="h-full flex items-center justify-center text-mw-text-secondary gap-2">
                <Loader2 className="animate-spin" size={24} />
                Loading Workspace…
            </div>
        );
    }

    const displayName = companion?.name ?? bootstrap.companion.name;

    return (
        <div className="h-full flex flex-col bg-mw-page min-h-0">
            <header className="shrink-0 flex items-center justify-between gap-3 px-4 py-3 border-b border-mw-border bg-mw-card">
                <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-mw-text-primary truncate">{displayName}</h2>
                    <p className="text-xs text-mw-text-secondary truncate">{bootstrap.workspace.name}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        type="button"
                        onClick={() => void startNewChat()}
                        disabled={newChatBusy || sending || !!pendingProposal || proposalBusy}
                        className="shrink-0 flex items-center gap-2 rounded-xl border border-mw-border bg-mw-page px-3 py-2 text-xs font-medium text-mw-text-primary hover:bg-mw-card-alt transition-colors disabled:opacity-50 disabled:pointer-events-none"
                        title="Start a new conversation thread (fresh session memory)"
                    >
                        {newChatBusy ? (
                            <Loader2 className="animate-spin" size={16} aria-hidden />
                        ) : (
                            <MessageSquarePlus size={16} aria-hidden />
                        )}
                        New chat
                    </button>
                    <button
                        type="button"
                        onClick={() => setPipelineOpen(o => !o)}
                        className={`shrink-0 flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-medium transition-colors ${
                            pipelineOpen
                                ? 'border-mw-primary bg-mw-primary-muted text-mw-primary'
                                : 'border-mw-border bg-mw-page text-mw-text-primary hover:bg-mw-card-alt'
                        }`}
                        title="Companion pipeline: prompts, models, post steps"
                    >
                        <GitBranch size={16} aria-hidden />
                        Pipeline
                    </button>
                    <button
                        type="button"
                        onClick={() => setWorkspaceSettingsOpen(true)}
                        className="shrink-0 flex items-center gap-2 rounded-xl border border-mw-border bg-mw-page px-3 py-2 text-xs font-medium text-mw-text-primary hover:bg-mw-card-alt transition-colors"
                        title="Workspace capabilities"
                    >
                        <Boxes size={16} aria-hidden />
                        Workspace
                    </button>
                    <button
                        type="button"
                        onClick={() => setSettingsOpen(true)}
                        className="shrink-0 flex items-center gap-2 rounded-xl border border-mw-border bg-mw-page px-3 py-2 text-xs font-medium text-mw-text-primary hover:bg-mw-card-alt transition-colors"
                        title="Customize Companion"
                    >
                        <Settings2 size={16} aria-hidden />
                        Customize
                    </button>
                </div>
            </header>
            <WorkspaceSettingsModal
                isOpen={workspaceSettingsOpen}
                onClose={() => setWorkspaceSettingsOpen(false)}
                workspace={bootstrap.workspace}
                onSaved={w =>
                    setBootstrap(prev => (prev ? { ...prev, workspace: w } : null))
                }
            />
            {companion && (
                <CompanionSettingsModal
                    isOpen={settingsOpen}
                    onClose={() => setSettingsOpen(false)}
                    companion={companion}
                    workspaceEnabledWorkflowIds={bootstrap.workspace.enabled_workflow_ids ?? []}
                    onSaved={c => setCompanion(c)}
                />
            )}
            {newChatError && (
                <div className="shrink-0 px-4 py-2 bg-red-500/10 border-b border-mw-border text-sm text-mw-error">
                    {newChatError}
                </div>
            )}
            {memoryToast && (
                <div className="shrink-0 px-4 py-2 bg-mw-primary-muted border-b border-mw-border text-sm text-mw-text-primary">
                    {memoryToast}
                </div>
            )}
            <div className="flex-1 flex min-h-0 overflow-hidden">
            <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
            <div className="shrink-0 flex bg-mw-card border-b border-mw-border px-2 gap-1">
                <button
                    type="button"
                    onClick={() => setWorkspacePanelTab('chat')}
                    className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-colors ${
                        workspacePanelTab === 'chat'
                            ? 'text-mw-primary border-mw-primary bg-mw-page'
                            : 'text-mw-text-secondary border-transparent hover:text-mw-text-primary'
                    }`}
                >
                    <MessageSquare size={16} aria-hidden />
                    Chat
                </button>
                <button
                    type="button"
                    onClick={() => setWorkspacePanelTab('console')}
                    className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-colors ${
                        workspacePanelTab === 'console'
                            ? 'text-mw-primary border-mw-primary bg-mw-page'
                            : 'text-mw-text-secondary border-transparent hover:text-mw-text-primary'
                    }`}
                >
                    <Terminal size={16} aria-hidden />
                    Console
                </button>
            </div>

            {workspacePanelTab === 'chat' ? (
                <>
                    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
                        {messages.length === 0 && (
                            <p className="text-sm text-mw-text-secondary text-center mt-8">
                                Chat with your Companion. Replies stream as they are composed.
                            </p>
                        )}
                        {messages.map((m, i) => (
                            <div
                                key={i}
                                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[min(100%,42rem)] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                                        m.role === 'user'
                                            ? 'bg-mw-primary text-white'
                                            : 'bg-mw-card border border-mw-border text-mw-text-primary'
                                    }`}
                                >
                                    {m.content || (m.role === 'assistant' && sending ? '…' : '')}
                                </div>
                            </div>
                        ))}
                        <div ref={bottomRef} />
                    </div>
                    {pendingProposal && (
                        <div className="shrink-0 border-t border-mw-border bg-mw-card-alt px-4 py-3 space-y-2">
                            <p className="text-xs font-semibold text-mw-text-primary">Confirm workflow run</p>
                            <ul className="text-xs text-mw-text-secondary space-y-2">
                                {pendingProposal.capabilities.map(c => (
                                    <li
                                        key={c.capability_key}
                                        className="rounded-lg border border-mw-border bg-mw-page p-2"
                                    >
                                        <div className="font-medium text-mw-text-primary">{c.name}</div>
                                        {c.missing_start_binding_keys && c.missing_start_binding_keys.length > 0 ? (
                                            <p className="mt-1 text-xs text-mw-error font-medium">
                                                Missing required Start inputs:{' '}
                                                {c.missing_start_binding_keys.join(', ')} — cancel and rephrase, or
                                                confirm only if defaults exist on the graph.
                                            </p>
                                        ) : null}
                                        {c.start_slots && c.start_slots.length > 0 ? (
                                            <p className="mt-1 text-[11px] text-mw-text-secondary">
                                                Start inputs:{' '}
                                                {c.start_slots
                                                    .map(
                                                        s =>
                                                            `${s.key}${s.required ? ' (required)' : ' (optional)'}: ${s.input_type}`,
                                                    )
                                                    .join(' · ')}
                                            </p>
                                        ) : null}
                                        {Object.keys(c.input_bindings).length > 0 ? (
                                            <pre className="mt-1 text-[11px] overflow-x-auto text-mw-text-secondary whitespace-pre-wrap font-mono">
                                                {JSON.stringify(c.input_bindings, null, 2)}
                                            </pre>
                                        ) : (
                                            <p className="mt-1 text-mw-text-secondary">No parameters</p>
                                        )}
                                    </li>
                                ))}
                            </ul>
                            <div className="flex flex-wrap gap-2 pt-1">
                                <button
                                    type="button"
                                    disabled={proposalBusy}
                                    onClick={() => void resolveProposal(false)}
                                    className="rounded-xl bg-mw-primary text-white px-4 py-2 text-xs font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                                >
                                    Confirm
                                </button>
                                <button
                                    type="button"
                                    disabled={proposalBusy}
                                    onClick={() => void resolveProposal(true)}
                                    className="rounded-xl border border-mw-border bg-mw-page px-4 py-2 text-xs font-medium text-mw-text-primary disabled:opacity-50 hover:bg-mw-card transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    )}
                    <div className="shrink-0 border-t border-mw-border bg-mw-card p-3 flex gap-2">
                        <textarea
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={e => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    void send();
                                }
                            }}
                            placeholder={pendingProposal ? 'Confirm or cancel the pending run above…' : 'Message…'}
                            rows={2}
                            disabled={sending || !!pendingProposal}
                            className="flex-1 min-w-0 rounded-xl border border-mw-border bg-mw-page px-3 py-2 text-sm text-mw-text-primary placeholder:text-mw-text-secondary resize-none focus:outline-none focus:ring-2 focus:ring-mw-primary"
                        />
                        <button
                            type="button"
                            onClick={() => void send()}
                            disabled={sending || !input.trim() || !!pendingProposal}
                            className="shrink-0 self-end rounded-xl bg-mw-primary text-white p-3 disabled:opacity-50 hover:opacity-90 transition-opacity"
                            title="Send"
                        >
                            {sending ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
                        </button>
                    </div>
                </>
            ) : (
                <div className="flex-1 flex flex-col min-h-0 p-4 gap-3">
                    <p className="text-xs text-mw-text-secondary">
                        Redacted turn traces (interpretation, routing, execution, composition). Use this when the
                        chat reply mentions workflow errors or partial runs.
                    </p>
                    <div className="shrink-0 flex flex-wrap items-center gap-2">
                        <label htmlFor="ws-console-turn" className="text-xs font-medium text-mw-text-primary">
                            Turn
                        </label>
                        <select
                            id="ws-console-turn"
                            value={selectedConsoleTurnId}
                            onChange={e => setSelectedConsoleTurnId(e.target.value)}
                            disabled={consoleLoading || consoleTurns.length === 0}
                            className="flex-1 min-w-[12rem] max-w-md rounded-lg border border-mw-border bg-mw-page px-2 py-1.5 text-sm text-mw-text-primary"
                        >
                            {consoleTurns.length === 0 ? (
                                <option value="">—</option>
                            ) : (
                                consoleTurns.map(t => (
                                    <option key={t.id} value={t.id}>
                                        #{t.turn_index} · {t.outcome_type} · {t.trace_id.slice(0, 8)}…
                                    </option>
                                ))
                            )}
                        </select>
                        {consoleLoading && <Loader2 className="animate-spin text-mw-text-secondary" size={18} />}
                    </div>
                    {consoleError && (
                        <p className="text-xs text-mw-error shrink-0" role="alert">
                            {consoleError}
                        </p>
                    )}
                    {consoleDetail && !consoleLoading && (
                        <pre className="flex-1 min-h-0 overflow-auto rounded-xl border border-mw-border bg-mw-page p-3 text-[11px] font-mono text-mw-text-primary whitespace-pre-wrap break-words">
                            {JSON.stringify(consoleDetail.traces, null, 2)}
                        </pre>
                    )}
                    {!consoleLoading && consoleTurns.length === 0 && (
                        <p className="text-sm text-mw-text-secondary">No turns yet for this session.</p>
                    )}
                </div>
            )}
            </div>
            {pipelineOpen && (
                <WorkspacePipelinePanel
                    workspace={bootstrap.workspace}
                    onClose={() => setPipelineOpen(false)}
                    onSaved={w => setBootstrap(prev => (prev ? { ...prev, workspace: w } : null))}
                    runStages={pipelineRunStages}
                />
            )}
            </div>
        </div>
    );
};
