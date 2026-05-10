/**
 * API Client
 * ==========
 * Static helper class for all HTTP calls to the Mind Weave backend.
 */

import type { SandboxEnvelopeJson } from '../domain/sandbox/types';
import type { SandboxTickResponseJson } from './types';
import {
    ModelsResponse,
    Persona, PersonaCreate, PersonaListItem, PersonaUpdate,
    Palette, PaletteCreate, PaletteUpdate,
    SystemPalette, SystemPaletteCreate, SystemPaletteUpdate,
    Structure, StructureCreate, StructureUpdate,
    Document, DocumentCreate, DocumentListItem, DocumentMetadata, DocumentUpdate,
    WorkflowDefinition, WorkflowDefinitionCreate, WorkflowDefinitionListItem, WorkflowDefinitionUpdate,
    WorkflowProject,
    WorkflowProjectCreate,
    WorkflowProjectUpdate,
    WorkflowRunResult, WorkflowRun, NodeRunLog, MyWorkflowRunSummary,
    GoogleWorkflowConnection,
    Companion,
    CompanionUpdate,
    Workspace,
    WorkspaceBootstrapResponse,
    WorkspacePipelinePreviewResponse,
    WorkspaceSession,
    WorkspaceSessionCreate,
    WorkspaceTurn,
    WorkspaceTurnDetail,
    WorkspaceUpdate,
    TtsModelRead,
    AudioFileArtifactRead,
    TranscriptionProviderItem,
    VoiceDesignPreviewRequest,
    VoiceDesignPreviewResponse,
    VoiceSampleCreate,
    VoiceSampleDetail,
    VoiceSampleListItem,
    WorkflowExecutionLimitsEnvelope,
    WorkflowExecutionLimitsOverrides,
} from './types';
import { API_BASE } from './baseUrl';
import { apiErrorFromResponse, fetchWithCredentials, readJsonBody } from './http';
import {
    consumeWorkspaceTurnStream,
    type WorkspaceCapabilityProposalCap,
    type WorkspaceStreamDoneMeta,
    type WorkspaceStreamStageEvent,
} from './workspaceStream';
import { consumeWorkflowRunSseResponse } from './workflowRunSse';

const DEFAULT_STT_MAX_AUDIO_UPLOAD_BYTES = 75 * 1024 * 1024;
const STT_MAX_AUDIO_UPLOAD_BYTES = (() => {
    const raw = import.meta.env.VITE_STT_MAX_AUDIO_UPLOAD_BYTES as string | undefined;
    const parsed = raw != null && raw.trim() !== '' ? Number(raw) : DEFAULT_STT_MAX_AUDIO_UPLOAD_BYTES;
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : DEFAULT_STT_MAX_AUDIO_UPLOAD_BYTES;
})();

function formatUploadBytes(bytes: number): string {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export class ApiClient {
    private static async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...(options?.headers as Record<string, string>),
        };

        const response = await fetchWithCredentials(`${API_BASE}${endpoint}`, {
            ...options,
            headers,
        });

        if (!response.ok) {
            const body = await readJsonBody(response);
            throw apiErrorFromResponse(response, body);
        }

        // 204 No Content returns no body.
        if (response.status === 204) {
            return undefined as unknown as T;
        }

        return response.json();
    }

    // -------------------------------------------------------------------------
    // Models
    // -------------------------------------------------------------------------

    static getModels(): Promise<ModelsResponse> {
        return this.request<ModelsResponse>('/models/');
    }

    // -------------------------------------------------------------------------
    // Personas
    // -------------------------------------------------------------------------

    static getPersonas(): Promise<PersonaListItem[]> {
        return this.request<PersonaListItem[]>('/personas/');
    }

    static getPersona(id: string): Promise<Persona> {
        return this.request<Persona>(`/personas/${id}`);
    }

    static createPersona(data: PersonaCreate): Promise<Persona> {
        return this.request<Persona>('/personas/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updatePersona(id: string, data: PersonaUpdate): Promise<Persona> {
        return this.request<Persona>(`/personas/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deletePersona(id: string): Promise<void> {
        await this.request<void>(`/personas/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // TTS models (bridge registry)
    // -------------------------------------------------------------------------

    static getTtsModelsReady(): Promise<TtsModelRead[]> {
        return this.request<TtsModelRead[]>('/tts-models');
    }

    static getTtsModelsRegistry(): Promise<TtsModelRead[]> {
        return this.request<TtsModelRead[]>('/tts-models/registry');
    }

    static createTtsModel(data: {
        display_name: string;
        engine: string;
        source: { kind: 'huggingface_repo'; repo_id: string; revision?: string | null };
    }): Promise<TtsModelRead> {
        return this.request<TtsModelRead>('/tts-models', { method: 'POST', body: JSON.stringify(data) });
    }

    static pullTtsModel(id: string): Promise<TtsModelRead> {
        return this.request<TtsModelRead>(`/tts-models/${id}/pull`, { method: 'POST' });
    }

    static async deleteTtsModel(id: string): Promise<void> {
        await this.request<void>(`/tts-models/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Voice samples (Voice Design previews + clone references)
    // -------------------------------------------------------------------------

    static getVoiceSamples(): Promise<VoiceSampleListItem[]> {
        return this.request<VoiceSampleListItem[]>('/voice-samples/');
    }

    static getVoiceSample(id: string): Promise<VoiceSampleDetail> {
        return this.request<VoiceSampleDetail>(`/voice-samples/${id}`);
    }

    static previewVoiceDesign(body: VoiceDesignPreviewRequest): Promise<VoiceDesignPreviewResponse> {
        return this.request<VoiceDesignPreviewResponse>('/voice-samples/preview-design', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    static createVoiceSample(body: VoiceSampleCreate): Promise<VoiceSampleDetail> {
        return this.request<VoiceSampleDetail>('/voice-samples/', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    static async deleteVoiceSample(id: string): Promise<void> {
        await this.request<void>(`/voice-samples/${id}`, { method: 'DELETE' });
    }

    static async getVoiceSampleAudioBlob(id: string): Promise<Blob> {
        const response = await fetchWithCredentials(`${API_BASE}/voice-samples/${id}/audio`);
        if (!response.ok) {
            const body = await readJsonBody(response);
            throw apiErrorFromResponse(response, body);
        }
        return response.blob();
    }

    // -------------------------------------------------------------------------
    // Audio file artifacts (Workflow Audio File Input)
    // -------------------------------------------------------------------------

    static getAudioFileArtifacts(): Promise<AudioFileArtifactRead[]> {
        return this.request<AudioFileArtifactRead[]>('/audio-file-artifacts/');
    }

    static async createAudioFileArtifact(file: File): Promise<AudioFileArtifactRead> {
        const form = new FormData();
        form.append('file', file, file.name);
        const response = await fetchWithCredentials(`${API_BASE}/audio-file-artifacts/`, {
            method: 'POST',
            body: form,
        });
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
        return (await response.json()) as AudioFileArtifactRead;
    }

    static async deleteAudioFileArtifact(id: string): Promise<void> {
        await this.request<void>(`/audio-file-artifacts/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Palettes
    // -------------------------------------------------------------------------

    static getPalettes(): Promise<Palette[]> {
        return this.request<Palette[]>('/palettes/');
    }

    static getPalette(id: string): Promise<Palette> {
        return this.request<Palette>(`/palettes/${id}`);
    }

    static getPaletteBySlug(slug: string): Promise<Palette> {
        return this.request<Palette>(`/palettes/by-slug/${encodeURIComponent(slug)}`);
    }

    static createPalette(data: PaletteCreate): Promise<Palette> {
        return this.request<Palette>('/palettes/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updatePalette(id: string, data: PaletteUpdate): Promise<Palette> {
        return this.request<Palette>(`/palettes/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deletePalette(id: string): Promise<void> {
        await this.request<void>(`/palettes/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // System palettes (app-wide themes)
    // -------------------------------------------------------------------------

    static getSystemPalettes(): Promise<SystemPalette[]> {
        return this.request<SystemPalette[]>('/system-palettes/');
    }

    static getSystemPalette(id: string): Promise<SystemPalette> {
        return this.request<SystemPalette>(`/system-palettes/${id}`);
    }

    static getSystemPaletteBySlug(slug: string): Promise<SystemPalette> {
        return this.request<SystemPalette>(`/system-palettes/by-slug/${encodeURIComponent(slug)}`);
    }

    static createSystemPalette(data: SystemPaletteCreate): Promise<SystemPalette> {
        return this.request<SystemPalette>('/system-palettes/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updateSystemPalette(id: string, data: SystemPaletteUpdate): Promise<SystemPalette> {
        return this.request<SystemPalette>(`/system-palettes/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deleteSystemPalette(id: string): Promise<void> {
        await this.request<void>(`/system-palettes/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Structures
    // -------------------------------------------------------------------------

    static getStructures(): Promise<Structure[]> {
        return this.request<Structure[]>('/structures/');
    }

    static getStructure(id: string): Promise<Structure> {
        return this.request<Structure>(`/structures/${id}`);
    }

    static createStructure(data: StructureCreate): Promise<Structure> {
        return this.request<Structure>('/structures/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updateStructure(id: string, data: StructureUpdate): Promise<Structure> {
        return this.request<Structure>(`/structures/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deleteStructure(id: string): Promise<void> {
        await this.request<void>(`/structures/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Documents
    // -------------------------------------------------------------------------

    static getDocuments(): Promise<DocumentListItem[]> {
        return this.request<DocumentListItem[]>('/documents/');
    }

    static getDocument(id: string): Promise<Document> {
        return this.request<Document>(`/documents/${id}`);
    }

    static getDocumentMetadata(id: string): Promise<DocumentMetadata> {
        return this.request<DocumentMetadata>(`/documents/${id}/metadata`);
    }

    static createDocument(data: DocumentCreate): Promise<Document> {
        return this.request<Document>('/documents/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updateDocument(id: string, data: DocumentUpdate): Promise<Document> {
        return this.request<Document>(`/documents/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deleteDocument(id: string): Promise<void> {
        await this.request<void>(`/documents/${id}`, { method: 'DELETE' });
    }

    /** Upload a PNG, JPEG, or WebP for the Image workflow primitive (stored as url_snapshot_artifacts). */
    static async postUrlSnapshotImageUpload(file: File): Promise<{
        artifact_id: string;
        mime_type: string;
        width: number;
        height: number;
    }> {
        const form = new FormData();
        form.append('file', file);
        const response = await fetchWithCredentials(`${API_BASE}/url-snapshot-artifacts`, {
            method: 'POST',
            body: form,
        });
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
        return response.json();
    }

    // -------------------------------------------------------------------------
    // Workflow Projects (folders)
    // -------------------------------------------------------------------------

    static getWorkflowProjects(): Promise<WorkflowProject[]> {
        return this.request<WorkflowProject[]>('/workflow-projects/');
    }

    static createWorkflowProject(data: WorkflowProjectCreate): Promise<WorkflowProject> {
        return this.request<WorkflowProject>('/workflow-projects/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updateWorkflowProject(id: string, data: WorkflowProjectUpdate): Promise<WorkflowProject> {
        return this.request<WorkflowProject>(`/workflow-projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
    }

    static async deleteWorkflowProject(id: string): Promise<void> {
        await this.request<void>(`/workflow-projects/${id}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Workflow Definitions
    // -------------------------------------------------------------------------

    static getWorkflows(): Promise<WorkflowDefinitionListItem[]> {
        return this.request<WorkflowDefinitionListItem[]>('/workflow-definitions/');
    }

    static getWorkflow(id: string): Promise<WorkflowDefinition> {
        return this.request<WorkflowDefinition>(`/workflow-definitions/${id}`);
    }

    static createWorkflow(data: WorkflowDefinitionCreate): Promise<WorkflowDefinition> {
        return this.request<WorkflowDefinition>('/workflow-definitions/', { method: 'POST', body: JSON.stringify(data) });
    }

    static updateWorkflow(id: string, data: WorkflowDefinitionUpdate): Promise<WorkflowDefinition> {
        return this.request<WorkflowDefinition>(`/workflow-definitions/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    }

    static async deleteWorkflow(id: string): Promise<void> {
        await this.request<void>(`/workflow-definitions/${id}`, { method: 'DELETE' });
    }

    static getWorkflowExecutionLimits(): Promise<WorkflowExecutionLimitsEnvelope> {
        return this.request<WorkflowExecutionLimitsEnvelope>('/workflow-execution-limits/');
    }

    static runWorkflow(
        id: string,
        options?: {
            input_overrides?: Record<string, unknown>;
            output_overrides?: Record<string, unknown>;
            execution_time_zone?: string;
            execution_limits?: WorkflowExecutionLimitsOverrides;
        },
    ): Promise<WorkflowRunResult> {
        const body: Record<string, unknown> = {};
        if (options?.input_overrides) {
            body.input_overrides = options.input_overrides;
        }
        if (options?.output_overrides && Object.keys(options.output_overrides).length > 0) {
            body.output_overrides = options.output_overrides;
        }
        if (options?.execution_time_zone) {
            body.execution_time_zone = options.execution_time_zone;
        }
        if (options?.execution_limits != null && Object.keys(options.execution_limits).length > 0) {
            body.execution_limits = options.execution_limits;
        }
        return this.request<WorkflowRunResult>(`/workflow-definitions/${id}/run`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    static async runWorkflowStream(
        id: string,
        onEvent: (event: any) => void,
        options?: {
            input_overrides?: Record<string, any>;
            output_overrides?: Record<string, unknown>;
            execution_time_zone?: string;
            execution_limits?: WorkflowExecutionLimitsOverrides;
            signal?: AbortSignal;
        },
    ): Promise<void> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        const body: Record<string, unknown> = {};
        if (options?.input_overrides) {
            body.input_overrides = options.input_overrides;
        }
        if (options?.output_overrides && Object.keys(options.output_overrides).length > 0) {
            body.output_overrides = options.output_overrides;
        }
        if (options?.execution_time_zone) {
            body.execution_time_zone = options.execution_time_zone;
        }
        if (options?.execution_limits != null && Object.keys(options.execution_limits).length > 0) {
            body.execution_limits = options.execution_limits;
        }

        const enqueueResp = await fetchWithCredentials(`${API_BASE}/workflow-definitions/${id}/runs`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            signal: options?.signal,
        });

        if (!enqueueResp.ok) {
            const errBody = await readJsonBody(enqueueResp);
            throw apiErrorFromResponse(enqueueResp, errBody);
        }

        type EnqueueRow = { run_id: string };
        const row = (await readJsonBody(enqueueResp)) as EnqueueRow;
        const runId = row.run_id;
        const streamResp = await fetchWithCredentials(`${API_BASE}/workflow-runs/${runId}/events`, {
            signal: options?.signal,
            headers: { Accept: 'text/event-stream' },
        });

        if (!streamResp.ok) {
            const errBody = await readJsonBody(streamResp);
            throw apiErrorFromResponse(streamResp, errBody);
        }

        let sawEnd = false;
        let sawError = false;

        try {
            await consumeWorkflowRunSseResponse(streamResp, event => {
                if (event.event === 'end') sawEnd = true;
                if (event.event === 'error') sawError = true;
                onEvent(event);
            });
        } catch (err) {
            if (options?.signal?.aborted) {
                return;
            }
            throw err;
        }

        if (!sawEnd && !sawError) {
            onEvent({
                event: 'error',
                error: 'SSE stream ended before completion (no end event).',
            });
        }
    }

    /**
     * Upload recorded audio for a `transcribe_audio` node during an async Build run (`GET …/workflow-runs/…/events`) (multipart).
     * Completes the server-side wait; transcription runs on the API after the upload.
     */
    static async postWorkflowTranscribeAudio(
        runId: string,
        params: {
            nodeId: string;
            forLoopId?: string | null;
            forLoopIteration: number;
            blob: Blob;
            filename?: string;
        },
    ): Promise<void> {
        const form = new FormData();
        form.append('node_id', params.nodeId);
        if (params.forLoopId) {
            form.append('for_loop_id', params.forLoopId);
        }
        form.append('for_loop_iteration', String(params.forLoopIteration));
        form.append('file', params.blob, params.filename ?? 'recording.webm');
        const response = await fetchWithCredentials(`${API_BASE}/workflow-runs/${runId}/transcribe-audio`, {
            method: 'POST',
            body: form,
        });
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
    }

    /**
     * Upload an audio file for an `audio_file_input` node during an async Build run (`GET …/workflow-runs/…/events`) (multipart).
     * Completes the server-side wait; transcription runs on the API after the upload.
     */
    static async postWorkflowAudioFileInput(
        runId: string,
        params: {
            nodeId: string;
            forLoopId?: string | null;
            forLoopIteration: number;
            file: File;
        },
    ): Promise<void> {
        if (params.file.size > STT_MAX_AUDIO_UPLOAD_BYTES) {
            throw new Error(
                `Audio file is too large (${formatUploadBytes(params.file.size)}). Runtime Audio File Input supports files up to ${formatUploadBytes(STT_MAX_AUDIO_UPLOAD_BYTES)}.`,
            );
        }
        const form = new FormData();
        form.append('node_id', params.nodeId);
        if (params.forLoopId) {
            form.append('for_loop_id', params.forLoopId);
        }
        form.append('for_loop_iteration', String(params.forLoopIteration));
        form.append('file', params.file, params.file.name);
        let response: Response;
        try {
            response = await fetchWithCredentials(`${API_BASE}/workflow-runs/${runId}/audio-file-input`, {
                method: 'POST',
                body: form,
            });
        } catch (err) {
            if (err instanceof TypeError && /failed to fetch/i.test(err.message)) {
                throw new Error(
                    'Could not upload the audio file. The API connection was interrupted or blocked; check the backend server, proxy body limit, and CORS settings.',
                );
            }
            throw err;
        }
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
    }

    /**
     * Upload an audio file for a `transcribe_file` node during an async Build run (`GET …/workflow-runs/…/events`) (multipart).
     * The executor consumes the bytes, dispatches them to the provider, and (for async providers)
     * persists a transcription_job that survives client disconnects.
     */
    static async postWorkflowTranscribeFileInput(
        runId: string,
        params: {
            nodeId: string;
            forLoopId?: string | null;
            forLoopIteration: number;
            file: File;
        },
    ): Promise<void> {
        if (params.file.size > STT_MAX_AUDIO_UPLOAD_BYTES) {
            throw new Error(
                `Audio file is too large (${formatUploadBytes(params.file.size)}). Runtime Transcribe File supports files up to ${formatUploadBytes(STT_MAX_AUDIO_UPLOAD_BYTES)}.`,
            );
        }
        const form = new FormData();
        form.append('node_id', params.nodeId);
        if (params.forLoopId) {
            form.append('for_loop_id', params.forLoopId);
        }
        form.append('for_loop_iteration', String(params.forLoopIteration));
        form.append('file', params.file, params.file.name);
        let response: Response;
        try {
            response = await fetchWithCredentials(`${API_BASE}/workflow-runs/${runId}/transcribe-file-input`, {
                method: 'POST',
                body: form,
            });
        } catch (err) {
            if (err instanceof TypeError && /failed to fetch/i.test(err.message)) {
                throw new Error(
                    'Could not upload the audio file. The API connection was interrupted or blocked; check the backend server, proxy body limit, and CORS settings.',
                );
            }
            throw err;
        }
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
    }

    /** List enabled speech-transcription providers (for the editor inspector dropdown). */
    static getTranscriptionProviders(): Promise<TranscriptionProviderItem[]> {
        return this.request<TranscriptionProviderItem[]>(`/transcription/providers`).then(rows =>
            rows.map(r => ({
                ...r,
                models: Array.isArray(r.models) ? r.models : [],
            })),
        );
    }

    /**
     * Reattach to a workflow run event stream (`GET …/workflow-runs/{id}/events`) after disconnect/reload.
     * Historical events replay as SSE, then polling tails terminal transcription jobs until the run settles.
     */
    static async reattachWorkflowRunStream(
        runId: string,
        onEvent: (event: any) => void,
        signal?: AbortSignal,
    ): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/workflow-runs/${runId}/events`, {
            signal,
            headers: { Accept: 'text/event-stream' },
        });
        if (!response.ok) {
            const errBody = await readJsonBody(response);
            throw apiErrorFromResponse(response, errBody);
        }
        await consumeWorkflowRunSseResponse(response, onEvent);
    }

    // -------------------------------------------------------------------------
    // Workflow Run Logs
    // -------------------------------------------------------------------------

    static getWorkflowRuns(workflowId: string): Promise<WorkflowRun[]> {
        return this.request<WorkflowRun[]>(`/workflow-definitions/${workflowId}/runs`);
    }

    static getWorkflowRunLogs(workflowId: string, runId: string): Promise<NodeRunLog[]> {
        return this.request<NodeRunLog[]>(`/workflow-definitions/${workflowId}/runs/${runId}/logs`);
    }

    static getMyWorkflowRuns(): Promise<MyWorkflowRunSummary[]> {
        return this.request<MyWorkflowRunSummary[]>(`/me/workflow-runs`);
    }

    static deleteWorkflowRun(workflowId: string, runId: string): Promise<void> {
        return this.request<void>(`/workflow-definitions/${workflowId}/runs/${runId}`, { method: 'DELETE' });
    }

    // -------------------------------------------------------------------------
    // Google workflow OAuth connections
    // -------------------------------------------------------------------------

    static getGoogleWorkflowConnections(): Promise<GoogleWorkflowConnection[]> {
        return this.request<GoogleWorkflowConnection[]>(`/google-workflow/connections`);
    }

    static postGoogleWorkflowAuthorize(): Promise<{ redirect_url: string }> {
        return this.request<{ redirect_url: string }>(`/google-workflow/oauth/authorize`, {
            method: 'POST',
        });
    }

    static patchGoogleWorkflowConnectionLabel(
        connectionId: string,
        body: { label: string | null },
    ): Promise<GoogleWorkflowConnection> {
        return this.request<GoogleWorkflowConnection>(`/google-workflow/connections/${connectionId}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
        });
    }

    static deleteGoogleWorkflowConnection(connectionId: string): Promise<void> {
        return this.request<void>(`/google-workflow/connections/${connectionId}`, {
            method: 'DELETE',
        });
    }

    // -------------------------------------------------------------------------
    // Sandbox (workflow-driven simulation)
    // -------------------------------------------------------------------------

    static createSandboxSession(body?: { workflow_id?: string }): Promise<{
        document_id: string;
        envelope: SandboxEnvelopeJson;
    }> {
        return this.request('/sandbox/sessions', {
            method: 'POST',
            body: JSON.stringify(body ?? {}),
        });
    }

    static getSandboxSession(documentId: string): Promise<{ envelope: SandboxEnvelopeJson }> {
        return this.request(`/sandbox/sessions/${documentId}`);
    }

    static tickSandbox(
        documentId: string,
        body: { interactions: unknown[]; state_version: number; workflow_id?: string },
    ): Promise<SandboxTickResponseJson> {
        return this.request(`/sandbox/sessions/${documentId}/tick`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    static resizeSandboxGrid(
        documentId: string,
        body: { width: number; height: number; state_version: number },
    ): Promise<{ envelope: SandboxEnvelopeJson }> {
        return this.request(`/sandbox/sessions/${documentId}/grid`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    static getStarterSandboxWorkflowId(): Promise<{ workflow_id: string }> {
        return this.request('/sandbox/starter-workflow-id');
    }

    // -------------------------------------------------------------------------
    // Companion / Workspace
    // -------------------------------------------------------------------------

    static getCompanion(): Promise<Companion> {
        return this.request<Companion>('/companion/');
    }

    static updateCompanion(data: CompanionUpdate): Promise<Companion> {
        return this.request<Companion>('/companion/', { method: 'PUT', body: JSON.stringify(data) });
    }

    static postWorkspaceBootstrap(): Promise<WorkspaceBootstrapResponse> {
        return this.request<WorkspaceBootstrapResponse>('/workspaces/bootstrap', { method: 'POST' });
    }

    static createWorkspaceSession(workspaceId: string, body?: WorkspaceSessionCreate): Promise<WorkspaceSession> {
        return this.request<WorkspaceSession>(`/workspaces/${workspaceId}/sessions`, {
            method: 'POST',
            body: JSON.stringify(body ?? {}),
        });
    }

    static updateWorkspace(workspaceId: string, data: WorkspaceUpdate): Promise<Workspace> {
        return this.request<Workspace>(`/workspaces/${workspaceId}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    static listWorkspaceTurns(workspaceId: string, sessionId: string): Promise<WorkspaceTurn[]> {
        return this.request<WorkspaceTurn[]>(`/workspaces/${workspaceId}/sessions/${sessionId}/turns`);
    }

    static getWorkspaceTurn(workspaceId: string, sessionId: string, turnId: string): Promise<WorkspaceTurnDetail> {
        return this.request<WorkspaceTurnDetail>(
            `/workspaces/${workspaceId}/sessions/${sessionId}/turns/${turnId}`,
        );
    }

    static getWorkspacePipelinePreview(workspaceId: string): Promise<WorkspacePipelinePreviewResponse> {
        return this.request<WorkspacePipelinePreviewResponse>(`/workspaces/${workspaceId}/pipeline/preview`);
    }

    static async streamWorkspaceTurn(
        workspaceId: string,
        sessionId: string,
        message: string,
        onToken: (text: string) => void,
        onDone: (meta: WorkspaceStreamDoneMeta) => void,
        onProposal?: (p: { proposal_id: string; capabilities: WorkspaceCapabilityProposalCap[] }) => void,
        onStage?: (e: WorkspaceStreamStageEvent) => void,
    ): Promise<void> {
        const response = await fetchWithCredentials(
            `${API_BASE}/workspaces/${workspaceId}/sessions/${sessionId}/turns/stream`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            },
        );
        if (!response.ok) {
            const body = await readJsonBody(response);
            throw apiErrorFromResponse(response, body);
        }
        await consumeWorkspaceTurnStream(response, onToken, onDone, onProposal, onStage);
    }

    static async streamWorkspaceConfirm(
        workspaceId: string,
        sessionId: string,
        proposalBody: { proposal_id: string; cancel: boolean },
        onToken: (text: string) => void,
        onDone: (meta: WorkspaceStreamDoneMeta) => void,
        onStage?: (e: WorkspaceStreamStageEvent) => void,
    ): Promise<void> {
        const response = await fetchWithCredentials(
            `${API_BASE}/workspaces/${workspaceId}/sessions/${sessionId}/turns/confirm-stream`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(proposalBody),
            },
        );
        if (!response.ok) {
            const body = await readJsonBody(response);
            throw apiErrorFromResponse(response, body);
        }
        await consumeWorkspaceTurnStream(response, onToken, onDone, undefined, onStage);
    }
}
