import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Mic, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';
import { ApiClient } from '../api/client';
import type { TtsModelRead, VoiceSampleDetail, VoiceSampleListItem } from '../api/types';
import { createObjectUrlForAudioBase64 } from '../domain/ttsAudioPlayback';
import { playTtsAudioFromBase64 } from '../domain/ttsAudioPlayback';
import { ManagerModal } from './ManagerModal';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from './managerShellStyles';

interface Props {
    isOpen: boolean;
    onClose: () => void;
}

const DEFAULT_FORM = {
    name: '',
    language: 'English',
    instruct: '',
    exampleText: '',
    designModelId: '',
};

export const VoiceManager: React.FC<Props> = ({ isOpen, onClose }) => {
    const [samples, setSamples] = useState<VoiceSampleListItem[]>([]);
    const [ttsReady, setTtsReady] = useState<TtsModelRead[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(true);
    const [form, setForm] = useState(DEFAULT_FORM);
    const [detail, setDetail] = useState<VoiceSampleDetail | null>(null);
    const [previewBase64, setPreviewBase64] = useState<string | null>(null);
    const [previewObjectUrl, setPreviewObjectUrl] = useState<string | null>(null);
    const [savedPlayUrl, setSavedPlayUrl] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [s, t] = await Promise.all([
                ApiClient.getVoiceSamples(),
                ApiClient.getTtsModelsReady().catch(() => [] as TtsModelRead[]),
            ]);
            setSamples(s);
            setTtsReady(t);
        } catch {
            setError('Failed to load voice samples. Check your connection and try again.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!isOpen) return;
        void load();
        setSelectedId(null);
        setIsCreating(true);
        setForm(DEFAULT_FORM);
        setDetail(null);
        setPreviewBase64(null);
        setError(null);
    }, [isOpen, load]);

    useEffect(() => {
        if (!isOpen || !ttsReady.length) return;
        setForm(f => (f.designModelId.trim() ? f : { ...f, designModelId: ttsReady[0]!.id }));
    }, [isOpen, ttsReady]);

    useEffect(() => {
        if (!previewBase64) {
            setPreviewObjectUrl(null);
            return;
        }
        let url: string;
        try {
            url = createObjectUrlForAudioBase64(previewBase64, 'audio/wav');
        } catch {
            setPreviewObjectUrl(null);
            return;
        }
        setPreviewObjectUrl(url);
        return () => {
            window.setTimeout(() => URL.revokeObjectURL(url), 2_000);
        };
    }, [previewBase64]);

    useEffect(() => {
        return () => {
            if (savedPlayUrl) URL.revokeObjectURL(savedPlayUrl);
        };
    }, [savedPlayUrl]);

    const startNew = () => {
        setSelectedId(null);
        setIsCreating(true);
        setDetail(null);
        setForm({
            ...DEFAULT_FORM,
            designModelId: ttsReady[0]?.id ?? '',
        });
        setPreviewBase64(null);
        setSavedPlayUrl(prev => {
            if (prev) URL.revokeObjectURL(prev);
            return null;
        });
        setError(null);
    };

    const selectSample = async (row: VoiceSampleListItem) => {
        setSelectedId(row.id);
        setIsCreating(false);
        setPreviewBase64(null);
        setError(null);
        try {
            const d = await ApiClient.getVoiceSample(row.id);
            setDetail(d);
            setForm({
                name: d.name,
                language: d.language,
                instruct: d.instruct,
                exampleText: d.ref_text,
                designModelId: d.design_model_id ?? '',
            });
            const blob = await ApiClient.getVoiceSampleAudioBlob(row.id);
            setSavedPlayUrl(prev => {
                if (prev) URL.revokeObjectURL(prev);
                return URL.createObjectURL(blob);
            });
        } catch {
            setError('Failed to load voice sample.');
            setDetail(null);
        }
    };

    const runGenerate = async () => {
        const tid = form.designModelId.trim();
        const text = form.exampleText.trim();
        if (!tid) {
            setError('Select a Voice Design model.');
            return;
        }
        if (!text) {
            setError('Example text is required.');
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const res = await ApiClient.previewVoiceDesign({
                design_model_id: tid,
                text,
                language: form.language.trim() || 'English',
                instruct: form.instruct.trim(),
            });
            setPreviewBase64(res.audio_base64);
            try {
                await playTtsAudioFromBase64(res.audio_base64, res.mime_type || 'audio/wav');
            } catch {
                /* auto-play may be blocked; inline player still available */
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Preview failed.');
        } finally {
            setBusy(false);
        }
    };

    const runSave = async () => {
        const name = form.name.trim();
        if (!name) {
            setError('Name your voice sample before saving.');
            return;
        }
        if (!previewBase64) {
            setError('Generate a preview first.');
            return;
        }
        const refText = form.exampleText.trim();
        if (!refText) {
            setError('Example text (transcript) is required.');
            return;
        }
        setBusy(true);
        setError(null);
        try {
            await ApiClient.createVoiceSample({
                name,
                ref_text: refText,
                language: form.language.trim() || 'English',
                instruct: form.instruct.trim(),
                design_model_id: form.designModelId.trim() || null,
                audio_base64: previewBase64,
            });
            await load();
            startNew();
        } catch (e) {
            const msg = e instanceof Error ? e.message : 'Save failed.';
            const proxyHint =
                /failed to fetch|networkerror|load failed/i.test(msg)
                    ? ' If this persists, your API reverse proxy may be rejecting large request bodies (raise nginx client_max_body_size; see docs/OPERATIONS.md).'
                    : '';
            setError(msg + proxyHint);
        } finally {
            setBusy(false);
        }
    };

    const runDelete = async () => {
        if (!selectedId) return;
        setBusy(true);
        setError(null);
        try {
            await ApiClient.deleteVoiceSample(selectedId);
            await load();
            startNew();
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Delete failed.');
        } finally {
            setBusy(false);
        }
    };

    if (!isOpen) return null;

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Voice Sample Manager" maxWidth="4xl">
            <div className="flex flex-1 overflow-hidden min-h-0">
                <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col min-h-0">
                    <div className="p-3 border-b border-mw-border">
                        <button
                            type="button"
                            onClick={startNew}
                            className="w-full flex items-center justify-center gap-2 py-2 bg-mw-primary-muted text-mw-primary hover:opacity-90 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={15} /> New sample
                        </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {loading && (
                            <div className="flex items-center justify-center gap-2 text-sm text-mw-text-secondary py-6">
                                <Loader2 size={16} className="animate-spin" /> Loading…
                            </div>
                        )}
                        {!loading &&
                            samples.map(s => (
                                <button
                                    key={s.id}
                                    type="button"
                                    onClick={() => void selectSample(s)}
                                    className={`w-full text-left rounded-lg border px-2.5 py-2 text-sm transition-colors ${
                                        selectedId === s.id && !isCreating
                                            ? 'border-mw-primary bg-mw-primary-muted/40 text-mw-text-primary'
                                            : 'border-mw-border hover:bg-mw-card-alt text-mw-text-primary'
                                    }`}
                                >
                                    <div className="font-medium truncate">{s.name}</div>
                                    <div className="text-[10px] text-mw-text-secondary">{s.language}</div>
                                </button>
                            ))}
                    </div>
                </div>
                <div className="flex-1 flex flex-col overflow-y-auto p-4 space-y-4 min-h-0">
                    <div className="flex items-start gap-2 text-mw-text-secondary text-xs">
                        <Mic size={16} className="shrink-0 mt-0.5 text-mw-primary" />
                        <p>
                            Design a voice with a <strong className="text-mw-text-primary">Voice Design</strong> checkpoint, then save the WAV + transcript for{' '}
                            <strong className="text-mw-text-primary">voice clone</strong> in workflows (select a <strong className="text-mw-text-primary">Base</strong> model on the TTS node).
                        </p>
                    </div>
                    {error && <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{error}</div>}
                    <div className="grid gap-3">
                        <div>
                            <label className={MANAGER_LABEL_CLS}>Name (required to save)</label>
                            <input
                                type="text"
                                value={form.name}
                                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                className={MANAGER_INPUT_CLS}
                                placeholder="e.g. Narrator warm"
                                disabled={!isCreating && !!selectedId}
                            />
                        </div>
                        <div>
                            <label className={MANAGER_LABEL_CLS}>Voice Design model</label>
                            <select
                                value={form.designModelId}
                                onChange={e => setForm(f => ({ ...f, designModelId: e.target.value }))}
                                className={MANAGER_INPUT_CLS}
                            >
                                <option value="">Select ready model</option>
                                {ttsReady.map(m => (
                                    <option key={m.id} value={m.id}>
                                        {m.display_name} ({m.engine})
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className={MANAGER_LABEL_CLS}>Language</label>
                            <input
                                type="text"
                                value={form.language}
                                onChange={e => setForm(f => ({ ...f, language: e.target.value }))}
                                className={MANAGER_INPUT_CLS}
                            />
                        </div>
                        <div>
                            <label className={MANAGER_LABEL_CLS}>Instruct (voice / style)</label>
                            <textarea
                                value={form.instruct}
                                onChange={e => setForm(f => ({ ...f, instruct: e.target.value }))}
                                rows={3}
                                className={`${MANAGER_INPUT_CLS} resize-none`}
                                placeholder="e.g. Male, 40s, calm documentary narrator"
                            />
                        </div>
                        <div>
                            <label className={MANAGER_LABEL_CLS}>Example text (spoken transcript)</label>
                            <textarea
                                value={form.exampleText}
                                onChange={e => setForm(f => ({ ...f, exampleText: e.target.value }))}
                                rows={4}
                                className={`${MANAGER_INPUT_CLS} resize-none`}
                                placeholder="What Voice Design will speak — must match audio when saved"
                            />
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            disabled={busy}
                            onClick={() => void runGenerate()}
                            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-mw-primary text-white hover:opacity-90 disabled:opacity-50"
                        >
                            {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                            Generate
                        </button>
                        <button
                            type="button"
                            disabled={busy || !previewBase64}
                            onClick={() => void runGenerate()}
                            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-mw-border bg-mw-card-alt hover:bg-mw-card disabled:opacity-50"
                        >
                            Re-generate
                        </button>
                        <button
                            type="button"
                            disabled={busy || !previewBase64 || !form.name.trim()}
                            onClick={() => void runSave()}
                            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-mw-border bg-mw-card-alt hover:bg-mw-card disabled:opacity-50"
                        >
                            <Save size={14} />
                            Save as Voice Sample
                        </button>
                        {!isCreating && selectedId && (
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => void runDelete()}
                                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg text-red-600 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50"
                            >
                                <Trash2 size={14} />
                                Delete
                            </button>
                        )}
                    </div>
                    {previewObjectUrl && isCreating && (
                        <div className="space-y-1">
                            <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide">Preview</div>
                            <audio controls preload="auto" src={previewObjectUrl} className="w-full max-w-md h-9" />
                        </div>
                    )}
                    {savedPlayUrl && !isCreating && detail && (
                        <div className="space-y-1">
                            <div className="text-[10px] font-medium text-mw-text-secondary uppercase tracking-wide">Saved audio</div>
                            <audio controls preload="auto" src={savedPlayUrl} className="w-full max-w-md h-9" />
                        </div>
                    )}
                </div>
            </div>
        </ManagerModal>
    );
};
