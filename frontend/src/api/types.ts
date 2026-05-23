/**
 * API Types
 * =========
 * TypeScript mirrors of the backend Pydantic models.
 */

import type { components } from '../generated/palette-types';

// ---------------------------------------------------------------------------
// Core entities
// ---------------------------------------------------------------------------

export interface PersonaListItem {
    id: string;
    user_id: string | null;
    name: string;
    type: 'custom' | 'system';
    description: string;
    default_model: string | null;
    is_default: boolean;
    creativity: number;
    /** When true, chat completions use reasoning_effort none (LM Studio 0.4.8+). */
    suppress_lm_thinking: boolean;
    created_at: string;
    updated_at: string;
}

export interface Persona extends PersonaListItem {
    system_prompt: string;
}

export interface PersonaCreate {
    name: string;
    description: string;
    system_prompt: string;
    default_model?: string | null;
    type?: 'custom' | 'system';
    is_default?: boolean;
    creativity?: number;
    suppress_lm_thinking?: boolean;
}

export interface PersonaUpdate {
    name?: string;
    description?: string;
    system_prompt?: string;
    default_model?: string | null;
    type?: 'custom' | 'system';
    is_default?: boolean;
    creativity?: number;
    suppress_lm_thinking?: boolean;
}

/** TTS model registry entry (metadata; weights live on the bridge host). */
export interface TtsModelRead {
    id: string;
    display_name: string;
    engine: string;
    source: Record<string, unknown>;
    local_key: string;
    status: string;
    error_message: string | null;
    created_at: string;
    updated_at: string;
}

/** Saved reference clip for Qwen3-TTS voice clone (Base model at workflow run). */
export interface VoiceSampleListItem {
    id: string;
    name: string;
    language: string;
    created_at: string;
}

export interface AudioFileArtifactRead {
    id: string;
    filename: string;
    mime_type: string;
    size_bytes: number;
    created_at: string;
    updated_at: string;
}

/** Public descriptor returned by `GET /transcription/providers` for the editor inspector. */
export interface TranscriptionModelItem {
    id: string;
    label: string;
    description: string | null;
    is_default: boolean;
}

export interface TranscriptionProviderItem {
    id: string;
    label: string;
    /** Capability tags such as `timestamps`, `translation`, `diarization`. */
    capabilities: string[];
    is_synchronous: boolean;
    requires_api_key: boolean;
    api_key_field: string | null;
    notes: string | null;
    /** Per-provider speech models (empty when the provider has no selectable models). */
    models: TranscriptionModelItem[];
}

export interface VoiceSampleDetail {
    id: string;
    name: string;
    language: string;
    ref_text: string;
    instruct: string;
    design_model_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface VoiceSampleCreate {
    name: string;
    ref_text: string;
    language?: string;
    instruct?: string;
    design_model_id?: string | null;
    audio_base64: string;
}

export interface VoiceDesignPreviewRequest {
    design_model_id: string;
    text: string;
    language?: string;
    instruct?: string;
}

export interface VoiceDesignPreviewResponse {
    mime_type: string;
    audio_base64: string;
}
/**
 * Palette + request bodies come from codegen (`openapi.palette.json`). Run `npm run codegen:palette-types`.
 */

export type Palette = components['schemas']['PalettePublic'];

export type PaletteCreate = components['schemas']['PaletteCreate'];

export type PaletteUpdate = components['schemas']['PaletteUpdate'];

export type PaletteValidateResult = components['schemas']['PaletteValidateResult'];

export type WorkflowPaletteEntryOut = components['schemas']['WorkflowPaletteEntryOut'];

/** App-wide UI theme (`system_palettes`); `colors` is `{ light: { token: hex }, dark: { ... } }`. */
export interface SystemPalette {
    id: string;
    user_id: string | null;
    name: string;
    slug?: string | null;
    colors: Record<string, Record<string, string>>;
    created_at: string;
    updated_at: string;
}

export interface SystemPaletteCreate {
    name: string;
    colors?: Record<string, Record<string, string>>;
}

export interface SystemPaletteUpdate {
    name?: string;
    colors?: Record<string, Record<string, string>>;
}

export interface Structure {
    id: string;
    user_id: string | null;
    name: string;
    description: string;
    json_schema: string;
    created_at: string;
    updated_at: string;
}

export interface StructureCreate {
    name: string;
    description?: string;
    json_schema: string;
}

export interface StructureUpdate {
    name?: string;
    description?: string;
    json_schema?: string;
}

export interface DocumentListItem {
    id: string;
    user_id: string | null;
    name: string;
    description: string;
    created_at: string;
    updated_at: string;
}

export interface Document extends DocumentListItem {
    body: string;
}

export interface DocumentCreate {
    name: string;
    description?: string;
    body?: string;
}

export interface DocumentUpdate {
    name?: string;
    description?: string;
    body?: string;
}

/**
 * Derived size statistics surfaced in the Manage Documents → Metadata tab.
 * Token counts are an estimate against ``tokenizer`` (currently ``o200k_base``,
 * the GPT-4o family); local LM Studio models may use a different tokenizer.
 */
export interface DocumentMetadata {
    id: string;
    name: string;
    created_at: string;
    updated_at: string;
    token_count: number;
    character_count: number;
    word_count: number;
    line_count: number;
    tokenizer: string;
}

export interface WorkflowProject {
    id: string;
    user_id: string;
    name: string;
    sort_order: number;
    workflow_count: number;
    created_at: string;
    updated_at: string;
}

export interface WorkflowProjectCreate {
    name: string;
    sort_order?: number | null;
}

export interface WorkflowProjectUpdate {
    name?: string;
    sort_order?: number | null;
}

export interface WorkflowDefinitionListItem {
    id: string;
    user_id: string | null;
    name: string;
    description: string | null;
    palette_id?: string | null;
    project_id?: string | null;
    expose_as_custom_skill?: boolean;
    is_system?: boolean;
    builtin_slug?: string | null;
    created_at?: string;
    updated_at?: string;
}

/** List-row shape with optional graph after client hydration (e.g. editor prefetches nested `workflow_id` defs). */
export type WorkflowDefinitionListItemHydrated = WorkflowDefinitionListItem & {
    graph?: WorkflowGraph;
};

export interface WorkflowDefinition extends WorkflowDefinitionListItem {
    graph: WorkflowGraph;
}

export interface WorkflowDefinitionCreate {
    name: string;
    description?: string | null;
    palette_id?: string | null;
    project_id?: string | null;
    expose_as_custom_skill?: boolean;
    graph?: WorkflowGraph;
}

export interface WorkflowDefinitionUpdate {
    name?: string;
    description?: string | null;
    palette_id?: string | null;
    project_id?: string | null;
    expose_as_custom_skill?: boolean;
    graph?: WorkflowGraph;
}

// ---------------------------------------------------------------------------
// Graph types (mirror backend GraphNode / GraphEdge)
// ---------------------------------------------------------------------------

export interface RequiredInput {
    key: string;
    type: 'string' | 'list' | 'dictionary' | 'structure' | 'document' | 'boolean' | 'int' | 'datetime' | 'gmail' | 'audio' | 'any';
    value: string | any[] | Record<string, any> | boolean | number | null;
}

export interface RequiredOutput {
    key: string;
    type: 'string' | 'list' | 'dictionary' | 'structure' | 'document' | 'boolean' | 'int' | 'datetime' | 'gmail' | 'audio' | 'any';
}

export interface GraphEdge {
    source: string;
    target: string;
    source_handle?: string | null;
    target_handle?: string | null;
}

export interface SimpleLLMCallSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'simple_llm_call';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        persona_id: string | null;
        structure_id?: string | null;
        additional_system_prompt_context?: string | null;
    };
    position: { x: number; y: number };
}

export interface MultimodalLLMCallSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'multimodal_llm';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        persona_id: string | null;
        structure_id?: string | null;
        additional_system_prompt_context?: string | null;
        /** When set, overrides Persona default_model for this step. */
        model?: string | null;
    };
    position: { x: number; y: number };
}

export interface TextToSpeechSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'text_to_speech';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        tts_model_id: string | null;
        engine?: string | null;
        tts_options?: Record<string, unknown>;
        /** When set, workflow run uses voice clone with this sample's ref audio + transcript. */
        voice_sample_id?: string | null;
        /**
         * When set, overrides My Settings → TTS playback during Build SSE runs (`inline` | `manual` | `after_workflow`).
         * null/undefined: use user setting.
         */
        tts_playback_when?: 'inline' | 'manual' | 'after_workflow' | null;
        /**
         * Legacy: overrides My Settings auto-play when `tts_playback_when` is absent.
         * Prefer `tts_playback_when` for new graphs.
         */
        auto_play_tts_on_node_end?: boolean | null;
    };
    position: { x: number; y: number };
}

export interface TranscribeAudioSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'transcribe_audio';
    label: string;
    data: {
        /** BCP-47 / Whisper language code; omit for auto-detect. */
        language?: string | null;
        /** `transcribe` (default) or `translate` (to English). */
        task?: 'transcribe' | 'translate' | null;
        /** Reserved: bridge / server model id override. */
        model?: string | null;
    };
    position: { x: number; y: number };
}

export interface AudioFileInputSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'audio_file_input';
    label: string;
    data: {
        audio_artifact_id?: string | null;
        /** BCP-47 / Whisper language code; omit for auto-detect. */
        language?: string | null;
        /** `transcribe` (default) or `translate` (to English). */
        task?: 'transcribe' | 'translate' | null;
        /** Reserved: bridge / server model id override. */
        model?: string | null;
    };
    position: { x: number; y: number };
}

export interface TranscribeFileSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'transcribe_file';
    label: string;
    data: {
        /** Provider id (e.g. `local_whisper`, `assemblyai`). Defaults to `local_whisper`. */
        provider?: string | null;
        audio_artifact_id?: string | null;
        /** BCP-47 / language code; omit for auto-detect. */
        language?: string | null;
        /** `transcribe` (default) or `translate` (to English). */
        task?: 'transcribe' | 'translate' | null;
        /** Optional provider-specific bias prompt / vocab hint. */
        prompt?: string | null;
        /** Request speaker diarization in the resulting transcript primitive. */
        diarization_enabled?: boolean | null;
        /** Request word-level timestamps in the resulting transcript primitive. */
        include_word_timestamps?: boolean | null;
        /** Primary model slug for the selected provider (e.g. AssemblyAI `universal-3-pro`). */
        provider_model_id?: string | null;
    };
    position: { x: number; y: number };
}

export interface GmailListMessagesSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'gmail_list_messages';
    label: string;
    data: {
        google_connection_id: string | null;
        max_results?: number;
        unread_only?: boolean;
        after?: string | null;
        before?: string | null;
        query?: string | null;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface CalendarListEventsSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'calendar_list_events';
    label: string;
    data: {
        google_connection_id: string | null;
        calendar_id?: string;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface GoogleDocsGetDocumentSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'google_docs_get_document';
    label: string;
    data: {
        google_connection_id: string | null;
        document_url_or_id?: string | null;
        include_tabs_content?: boolean;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface GoogleDocsParseDocumentUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'google_docs_parse_document';
    label: string;
    data: {
        chunk_strategy?: 'structure' | 'tab' | 'flat';
        max_chunk_text_chars?: number | null;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface FetchUrlSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'fetch_url';
    label: string;
    data: {
        url?: string;
        method?: string;
        headers?: Record<string, string>;
        timeout_ms?: number | null;
        cache_policy?: 'default' | 'refresh' | 'bypass' | string;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface CaptureUrlSnapshotSkillNode {
    id: string;
    kind: 'skill';
    skill_type: 'capture_url_snapshot';
    label: string;
    data: {
        url?: string;
        full_page?: boolean;
        viewport_width?: number | null;
        viewport_height?: number | null;
        wait_until?: 'load' | 'domcontentloaded' | 'networkidle' | string;
        timeout_ms?: number | null;
        cache_policy?: 'default' | 'refresh' | 'bypass' | string;
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface ListToStringUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'list_to_string';
    label: string;
    data: {
        use_text_join?: boolean;
        add_line_breaks_between_items?: boolean;
    };
    position: { x: number; y: number };
}

export interface StringToListUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'string_to_list';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface PrependTextUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'prepend_text';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        add_additional_line?: boolean;
    };
    position: { x: number; y: number };
}

export interface StringTruncUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'string_trunc';
    label: string;
    data: {
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface MessageUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'message';
    label: string;
    data: {
        required_inputs: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface StructurePrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'structure';
    label: string;
    data: { structure_id: string };
    position: { x: number; y: number };
}

export interface DocumentPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'document';
    label: string;
    data: { document_id: string };
    position: { x: number; y: number };
}

/** User-owned image artifact (manual ``artifact_id`` and/or wired ``image`` input). */
export interface ImagePrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'image';
    label: string;
    data: {
        artifact_id?: string;
        required_inputs?: RequiredInput[];
    };
    position: { x: number; y: number };
}

/** Single curated Gmail message object (static ``message`` and/or wired ``gmail`` input). */
export interface GmailPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'gmail';
    label: string;
    data: {
        message?: Record<string, unknown>;
        required_inputs?: RequiredInput[];
    };
    position: { x: number; y: number };
}

export interface SandboxTickPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'sandbox_tick';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface SandboxGetPositionUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_get_position';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface SandboxGetFacingUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_get_facing';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface SandboxGetNearbyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_get_nearby';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface SandboxMoveForwardUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_move_forward';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxTurnLeftUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_turn_left';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxTurnRightUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_turn_right';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxIdleUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_idle';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxPickUpItemUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_pick_up_item';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxPlaceItemUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_place_item';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface SandboxGetInventoryUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'sandbox_get_inventory';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface StringPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'string';
    label: string;
    data: { text: string };
    position: { x: number; y: number };
}

export interface ListPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'list';
    label: string;
    data: any[];
    position: { x: number; y: number };
}

export interface DictionaryPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'dictionary';
    label: string;
    data: Record<string, any>;
    position: { x: number; y: number };
}

export interface BooleanPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'boolean';
    label: string;
    data: { value: boolean };
    position: { x: number; y: number };
}

export interface IntPrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'int';
    label: string;
    data: { value: number };
    position: { x: number; y: number };
}

export interface DateTimePrimitiveNode {
    id: string;
    kind: 'primitive';
    primitive_type: 'datetime';
    label: string;
    data: { iso: string | null; use_now?: boolean };
    position: { x: number; y: number };
}

export interface LenFromListUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'len_from_list';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface RandomItemFromListUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'random_item_from_list';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface IntToStringUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'int_to_string';
    label: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface ListItemByIndexUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'list_item_by_index';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export type DictionaryOutputValueType =
    | 'string'
    | 'list'
    | 'dictionary'
    | 'boolean'
    | 'int'
    | 'datetime';

export interface DictionaryValueByKeyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'dictionary_value_by_key';
    label: string;
    data: {
        required_inputs?: RequiredInput[];
        output_value_type?: DictionaryOutputValueType;
        /** When set, used if key missing or null (unless fallback input is wired; wire wins). */
        fallback_value?: unknown;
    };
    position: { x: number; y: number };
}

export interface DictionarySetValueByKeyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'dictionary_set_value_by_key';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface ReadDocumentPropertyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'read_document_property';
    label: string;
    data: {
        required_inputs?: RequiredInput[];
        output_value_type?: DictionaryOutputValueType;
    };
    position: { x: number; y: number };
}

export interface LoadDocumentUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'load_document';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export type DocumentWriteMode = 'replace' | 'append' | 'merge_json';

export interface UpsertDocumentUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'upsert_document';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface ParseDocumentBodyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'parse_document_body';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

/** One item in `text_blocks` from the html_parse_basic utility run output (dictionary). */
export interface HtmlParseBasicTextBlock {
    tag: string;
    text: string;
}

export interface HtmlParseBasicUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'html_parse_basic';
    label: string;
    data: {
        required_inputs?: RequiredInput[];
        /** Omitted or `default`: legacy output keys only. `list_items` | `articles`: also `segment_text_blocks` + `parse_options`. */
        granularity?: string | null;
        /** Optional CSS selector (BeautifulSoup `select_one`); scopes `text_blocks` / `links` / segments; title stays from `<title>`. */
        content_root_css?: string | null;
    };
    position: { x: number; y: number };
}

export interface WriteObjectToDocumentBodyUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'write_object_to_document_body';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface AppendValueToDocumentUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'append_value_to_document';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface ValidateAgainstStructureUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'validate_against_structure';
    label: string;
    data: { required_inputs?: RequiredInput[]; structure_id?: string | null };
    position: { x: number; y: number };
}

export interface AddToListUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'add_to_list';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface AddDaysUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: 'add_days';
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

/** Binary int math utilities (two int inputs → int output). */
export type BinaryIntUtilityType =
    | 'add_ints'
    | 'subtract_ints'
    | 'multiply_ints'
    | 'divide_ints'
    | 'modulo_ints'
    | 'min_ints'
    | 'max_ints';

export interface BinaryIntMathUtilityNode {
    id: string;
    kind: 'utility';
    utility_type: BinaryIntUtilityType;
    label: string;
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

/** Editor-only canvas annotation; ignored by workflow execution. */
export interface AnnotationNoteGraphNode {
    id: string;
    kind: 'annotation';
    annotation_type: 'note';
    label: string;
    /** Note body; shown as **Content** in the Workflow Editor Explorer. */
    data: {
        text: string;
        color?: string | null;
        /** Header chrome (General → Label); independent from **Content** font size. */
        label_font_size_px?: number;
        content_font_size_px?: number;
        /** Canvas header alignment (`left` | `center` | `right`); Explorer label input stays default. */
        label_align?: 'left' | 'center' | 'right';
        /** Canvas body alignment; Explorer Content textarea stays left-aligned for editing. */
        content_align?: 'left' | 'center' | 'right';
        /** Canvas size (px); resizable in the editor like regions. */
        width?: number;
        height?: number;
        /** Stack order among notes (`0`…`999`); above regions, below edges. */
        z_index?: number;
    };
    position?: { x: number; y: number };
}

/** Editor-only resizable frame; ignored by workflow execution. */
export interface AnnotationRegionGraphNode {
    id: string;
    kind: 'annotation';
    annotation_type: 'region';
    label: string;
    data: {
        color?: string | null;
        width: number;
        height: number;
        label_font_size_px?: number;
        /** Floating label badge alignment on the canvas (`left` | `center` | `right`). */
        label_align?: 'left' | 'center' | 'right';
        /** Canvas stack order among regions (higher draws on top); clamped in the editor. */
        z_index?: number;
    };
    position?: { x: number; y: number };
}

export interface StartGraphNode {
    id: string;
    kind: 'start';
    label: string;
    data?: { text?: string; required_inputs?: RequiredInput[] };
    position?: { x: number; y: number };
}

export interface StopGraphNode {
    id: string;
    kind: 'stop';
    label: string;
    data?: { required_outputs?: RequiredOutput[] };
    position?: { x: number; y: number };
}

export interface WorkflowRefNode {
    id: string;
    kind: 'workflow';
    label: string;
    data: { workflow_id: string };
    position?: { x: number; y: number };
}

export interface BasicConditionalControlNode {
    id: string;
    kind: 'control';
    control_type: 'basic_conditional';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        condition?: string | boolean | null;
    };
    position: { x: number; y: number };
}

export interface IsControlNode {
    id: string;
    kind: 'control';
    control_type: 'is';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface IsEmptyControlNode {
    id: string;
    kind: 'control';
    control_type: 'is_empty';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface GtControlNode {
    id: string;
    kind: 'control';
    control_type: 'gt';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface LtControlNode {
    id: string;
    kind: 'control';
    control_type: 'lt';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface GteControlNode {
    id: string;
    kind: 'control';
    control_type: 'gte';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface LteControlNode {
    id: string;
    kind: 'control';
    control_type: 'lte';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface AndControlNode {
    id: string;
    kind: 'control';
    control_type: 'and';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface OrControlNode {
    id: string;
    kind: 'control';
    control_type: 'or';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface XorControlNode {
    id: string;
    kind: 'control';
    control_type: 'xor';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface NotControlNode {
    id: string;
    kind: 'control';
    control_type: 'not';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface BetweenControlNode {
    id: string;
    kind: 'control';
    control_type: 'between';
    label: string;
    data: { required_inputs: RequiredInput[] };
    position: { x: number; y: number };
}

export interface TryCatchControlNode {
    id: string;
    kind: 'control';
    control_type: 'try_catch';
    label: string;
    /** Optional wired value surfaced on handle `value` when the try branch succeeds without error. */
    data: { required_inputs?: RequiredInput[] };
    position: { x: number; y: number };
}

export interface ForLoopControlNode {
    id: string;
    kind: 'control';
    control_type: 'for_loop';
    label: string;
    data: {
        required_inputs: RequiredInput[];
        /** @deprecated Prefer `iteration_mode`; kept for older graphs */
        parallel_iterations?: boolean;
        iteration_mode?: 'sequential' | 'parallel' | 'batched';
        batch_size?: number;
        continue_on_error?: boolean;
        max_iterations?: number;
    };
    position: { x: number; y: number };
}

export interface ForLoopEndControlNode {
    id: string;
    kind: 'control';
    control_type: 'for_loop_end';
    label: string;
    data: { for_loop_id: string; exports?: string[] };
    position: { x: number; y: number };
}

export type GraphNode =
    | SimpleLLMCallSkillNode
    | MultimodalLLMCallSkillNode
    | TextToSpeechSkillNode
    | TranscribeAudioSkillNode
    | AudioFileInputSkillNode
    | TranscribeFileSkillNode
    | GmailListMessagesSkillNode
    | CalendarListEventsSkillNode
    | GoogleDocsGetDocumentSkillNode
    | GoogleDocsParseDocumentUtilityNode
    | FetchUrlSkillNode
    | CaptureUrlSnapshotSkillNode
    | ListToStringUtilityNode
    | StringToListUtilityNode
    | PrependTextUtilityNode
    | StringTruncUtilityNode
    | MessageUtilityNode
    | LenFromListUtilityNode
    | RandomItemFromListUtilityNode
    | SandboxGetPositionUtilityNode
    | SandboxGetFacingUtilityNode
    | SandboxGetNearbyUtilityNode
    | SandboxMoveForwardUtilityNode
    | SandboxTurnLeftUtilityNode
    | SandboxTurnRightUtilityNode
    | SandboxIdleUtilityNode
    | SandboxPickUpItemUtilityNode
    | SandboxPlaceItemUtilityNode
    | SandboxGetInventoryUtilityNode
    | IntToStringUtilityNode
    | ListItemByIndexUtilityNode
    | DictionaryValueByKeyUtilityNode
    | DictionarySetValueByKeyUtilityNode
    | ReadDocumentPropertyUtilityNode
    | LoadDocumentUtilityNode
    | UpsertDocumentUtilityNode
    | ParseDocumentBodyUtilityNode
    | GoogleDocsParseDocumentUtilityNode
    | HtmlParseBasicUtilityNode
    | WriteObjectToDocumentBodyUtilityNode
    | AppendValueToDocumentUtilityNode
    | ValidateAgainstStructureUtilityNode
    | AddToListUtilityNode
    | AddDaysUtilityNode
    | BinaryIntMathUtilityNode
    | BasicConditionalControlNode
    | IsControlNode
    | IsEmptyControlNode
    | GtControlNode
    | LtControlNode
    | GteControlNode
    | LteControlNode
    | AndControlNode
    | OrControlNode
    | XorControlNode
    | NotControlNode
    | BetweenControlNode
    | TryCatchControlNode
    | ForLoopControlNode
    | ForLoopEndControlNode
    | StringPrimitiveNode
    | ListPrimitiveNode
    | DictionaryPrimitiveNode
    | BooleanPrimitiveNode
    | IntPrimitiveNode
    | DateTimePrimitiveNode
    | StructurePrimitiveNode
    | DocumentPrimitiveNode
    | ImagePrimitiveNode
    | GmailPrimitiveNode
    | SandboxTickPrimitiveNode
    | AnnotationNoteGraphNode
    | AnnotationRegionGraphNode
    | StartGraphNode
    | StopGraphNode
    | WorkflowRefNode;

export type {
    SandboxEnvelopeJson,
    SandboxSandboxStateJson,
} from '../domain/sandbox/types';

/** Optional overrides merged server-side under deployment ceilings (defaults + graph + run). */
export interface WorkflowExecutionLimitsOverrides {
    workflow_ttl_seconds?: number;
    max_node_executions?: number;
    max_loop_iterations?: number;
    max_nested_depth?: number;
}

/** `GET /workflow-execution-limits/` payloads (defaults + ceilings). */
export interface WorkflowExecutionLimitsEnvelope {
    defaults: Required<WorkflowExecutionLimitsOverrides>;
    ceilings: Required<WorkflowExecutionLimitsOverrides> & { max_loop_batch_size: number };
}

export interface WorkflowGraph {
    nodes: GraphNode[];
    edges: GraphEdge[];
    /** Present on API responses after save; omitted = legacy implicit v1 */
    schema_version?: number | null;
    /** Saved with the graph JSON; merged at run-time with defaults and optional per-run overrides. */
    execution_limits?: WorkflowExecutionLimitsOverrides | null;
}

// ---------------------------------------------------------------------------
// Workflow run results
// ---------------------------------------------------------------------------

export type NodeOutputKind =
    | 'string'
    | 'response'
    | 'list'
    | 'dictionary'
    | 'audio'
    | 'gmail'
    | 'start'
    | 'stop'
    | 'conditional';

export interface NodeOutputBase {
    node_id: string;
    kind: NodeOutputKind;
}

export interface StringNodeOutput extends NodeOutputBase {
    kind: 'string';
    text: string;
}

export interface ResponseNodeOutput extends NodeOutputBase {
    kind: 'response';
    text: string;
    metadata: Record<string, unknown>;
}

export interface ListNodeOutput extends NodeOutputBase {
    kind: 'list';
    data: any[];
}

export interface DictionaryNodeOutput extends NodeOutputBase {
    kind: 'dictionary';
    data: Record<string, any>;
}

/** Text-to-Speech WAV (or compatible) as base64 for JSON/stream transport. */
export interface AudioNodeOutput extends NodeOutputBase {
    kind: 'audio';
    mime_type: string;
    audio_base64: string;
}

/** Curated Gmail message fields (mirrors backend ``GmailNodeOutput``). */
export interface GmailNodeOutput extends NodeOutputBase {
    kind: 'gmail';
    id?: string | null;
    threadId?: string | null;
    internalDate?: string | null;
    snippet?: string | null;
    labelIds?: string[];
    subject?: string | null;
    from?: string | null;
    to?: string | null;
    date?: string | null;
    body_text?: string | null;
    body_truncated?: boolean | null;
    fetch_error?: string | null;
}

export interface StartNodeOutput extends NodeOutputBase {
    kind: 'start';
    outputs?: Record<string, any>;
    text: string;
}

export interface StopNodeOutput extends NodeOutputBase {
    kind: 'stop';
    text: string;
}

export interface ConditionalNodeOutput extends NodeOutputBase {
    kind: 'conditional';
    branch: 'true' | 'false';
}

export type NodeOutputUnion =
    | StringNodeOutput
    | ResponseNodeOutput
    | ListNodeOutput
    | DictionaryNodeOutput
    | AudioNodeOutput
    | GmailNodeOutput
    | StartNodeOutput
    | StopNodeOutput
    | ConditionalNodeOutput;

/** Editor-only `details.output_explorer` (see docs/OUTPUT_EXPLORER_UI.md). Legacy: `details.skill_explorer`. */
export type OutputExplorerKind =
    | 'gmail_list_messages'
    | 'calendar_list_events'
    | 'google_docs_get_document'
    | 'google_docs_parse_document'
    | 'fetch_url'
    | 'capture_url_snapshot'
    | 'list_primitive'
    | 'dictionary_primitive'
    | 'string_primitive'
    | 'int_primitive'
    | 'boolean_primitive'
    | 'start_outputs'
    | 'generic';

export interface OutputExplorerSummary {
    line: string;
    detail_lines?: string[];
}

export interface OutputExplorerItem {
    index: number;
    row_state: 'ok' | 'error';
    primary_line: string;
    secondary_line: string;
    teaser: string;
    badges: string[];
    /** List / dictionary primitive rows — guides modal + clipboard formatting. */
    inferred_primitive?: string;
}

export interface OutputExplorerV1 {
    version: 1;
    kind: OutputExplorerKind | string;
    summary: OutputExplorerSummary;
    items: OutputExplorerItem[];
    overflow_count?: number;
}

function isOutputExplorerItem(it: unknown): it is OutputExplorerItem {
    if (!it || typeof it !== 'object') return false;
    const r = it as Record<string, unknown>;
    if (typeof r.index !== 'number') return false;
    if (r.row_state !== 'ok' && r.row_state !== 'error') return false;
    if (typeof r.primary_line !== 'string') return false;
    if (typeof r.secondary_line !== 'string') return false;
    if (typeof r.teaser !== 'string') return false;
    if (!Array.isArray(r.badges)) return false;
    for (const b of r.badges) {
        if (typeof b !== 'string') return false;
    }
    if (r.inferred_primitive !== undefined && typeof r.inferred_primitive !== 'string') return false;
    return true;
}

export function parseOutputExplorerV1(raw: unknown): OutputExplorerV1 | null {
    if (!raw || typeof raw !== 'object') return null;
    const o = raw as Record<string, unknown>;
    if (o.version !== 1) return null;
    if (typeof o.kind !== 'string' || !o.kind.trim()) return null;
    const summary = o.summary;
    if (!summary || typeof summary !== 'object') return null;
    const line = (summary as Record<string, unknown>).line;
    if (typeof line !== 'string') return null;
    const dl = (summary as Record<string, unknown>).detail_lines;
    if (dl !== undefined) {
        if (!Array.isArray(dl)) return null;
        for (const x of dl) {
            if (typeof x !== 'string') return null;
        }
    }
    const items = o.items;
    if (!Array.isArray(items)) return null;
    for (const it of items) {
        if (!isOutputExplorerItem(it)) return null;
    }
    if (o.overflow_count !== undefined && typeof o.overflow_count !== 'number') return null;
    return raw as OutputExplorerV1;
}

/** Prefer `output_explorer`; fall back to deprecated `skill_explorer` (same v1 shape). */
export function parseEffectiveOutputExplorer(details: Record<string, unknown> | undefined): OutputExplorerV1 | null {
    if (!details) return null;
    const oe = parseOutputExplorerV1(details.output_explorer);
    if (oe) return oe;
    return parseOutputExplorerV1(details.skill_explorer);
}

/** @deprecated Use `OutputExplorerKind` / `OutputExplorerV1`. */
export type SkillExplorerKind =
    | 'gmail_list_messages'
    | 'calendar_list_events'
    | 'google_docs_get_document';
/** @deprecated Use `OutputExplorerV1`. */
export type SkillExplorerV1 = OutputExplorerV1;
/** @deprecated Use `parseOutputExplorerV1` or `parseEffectiveOutputExplorer`. */
export function parseSkillExplorerV1(raw: unknown): SkillExplorerV1 | null {
    const ex = parseOutputExplorerV1(raw);
    if (!ex) return null;
    if (
        ex.kind !== 'gmail_list_messages' &&
        ex.kind !== 'calendar_list_events' &&
        ex.kind !== 'google_docs_get_document'
    ) {
        return null;
    }
    return ex;
}

export interface NodeRunResult {
    node_id: string;
    status: 'ok' | 'error';
    output?: NodeOutputUnion;
    error?: string;
    latency_ms?: number;
    details?: Record<string, any>;
    /** 1-based execution order within the run (omitted on legacy results). */
    step_number?: number;
}

export interface WorkflowRunResult {
    workflow_id: string;
    run_id?: string;
    /** Client may set `running` while a stream is in flight before the final result arrives. */
    status: 'ok' | 'partial' | 'error' | 'running' | 'canceled';
    node_results: NodeRunResult[];
    /** Client-side or stream-level failure when no node result was produced. */
    error?: string;
}

/** `POST /api/v1/sandbox/sessions/{id}/tick` — envelope plus per-creature workflow traces. */
export interface SandboxTickResponseJson {
    envelope: import('../domain/sandbox/types').SandboxEnvelopeJson;
    last_workflow_runs: Record<string, WorkflowRunResult | null>;
}

// Run log records returned from the history API.
export interface WorkflowRun {
    id: string;
    workflow_id: string;
    started_by_user_id?: string;
    status: 'running' | 'ok' | 'partial' | 'error';
    created_at: string;
    updated_at: string;
}

/** Row from GET /api/v1/me/workflow-runs (Explore past runs). */
export interface MyWorkflowRunSummary {
    id: string;
    workflow_id: string;
    workflow_name: string;
    status: string;
    created_at: string;
    updated_at: string;
}

export interface NodeRunLog {
    id: string;
    run_id: string;
    node_id: string;
    step_number?: number | null;
    status: 'ok' | 'error';
    output_data?: Record<string, any>;
    error?: string;
    latency_ms?: number;
    details?: Record<string, any>;
    created_at: string;
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

export interface ModelsResponse {
    local: string[];
    external: string[];
    /** Set when LM Studio model listing failed or LMSTUDIO_API_KEY is unset (pickers still load). */
    lm_studio_list_error?: string | null;
}

// ---------------------------------------------------------------------------
// Auth / User
// ---------------------------------------------------------------------------

/** Google account linked for workflow skills (Gmail/Calendar readonly). */
export interface GoogleWorkflowConnection {
    id: string;
    google_email: string | null;
    label: string | null;
    scopes: string;
    created_at: string;
    updated_at: string;
}

export interface User {
    id: string;
    username: string;
    is_admin: boolean;
    /**
     * May include `workflow_execution_limits_prefs` ({ workflow_ttl_seconds?, max_node_executions?, max_loop_iterations?, max_nested_depth? }), optional overlays merged between deployment defaults and graph/run limits under server ceilings.
     */
    settings: Record<string, unknown>;
    api_keys: Record<string, string>;
    google_email?: string | null;
}

export interface Token {
    /** Omitted when using HttpOnly cookies (preferred). */
    access_token?: string | null;
    token_type: string;
}

// ---------------------------------------------------------------------------
// Companion / Workspace
// ---------------------------------------------------------------------------

export interface Companion {
    id: string;
    owner_user_id: string;
    name: string;
    description: string;
    persona_id: string | null;
    identity_profile: Record<string, unknown>;
    default_mode: string;
    available_modes: string[];
    /** Workflow definition UUIDs this Companion may use (intersected with Workspace). */
    enabled_workflow_ids: string[];
    memory_policy: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

/** Partial update for PUT /companion/ — omit fields you do not want to change. Use `persona_id: null` to clear. */
export interface CompanionUpdate {
    name?: string;
    description?: string;
    persona_id?: string | null;
    identity_profile?: Record<string, unknown>;
    default_mode?: string;
    available_modes?: string[];
    enabled_workflow_ids?: string[];
    memory_policy?: Record<string, unknown>;
}

/** Stored under ``runtime_configuration.companion_pipeline`` (backend-validated). */
export interface CompanionPipelinePostComposeStep {
    id: string;
    enabled: boolean;
    name: string;
    model?: string | null;
    system_prompt: string;
    replace_streamed_reply: boolean;
    expose_in_traces: boolean;
    output_key: string;
}

export type ProcessStepKind = 'review' | 'critique' | 'summarize' | 'investigate' | 'analyze';

export interface CompanionPipelineProcessStep {
    id: string;
    kind: ProcessStepKind;
    enabled: boolean;
    name: string;
    model?: string | null;
    description: string;
    max_iterations: number;
    questions: string[];
    expose_in_traces: boolean;
}

export interface CompanionPipelineStored {
    version: number;
    stages: {
        interpret: {
            enabled: boolean;
            model_override?: string | null;
            system_prompt_base?: string | null;
            system_instructions_append?: string | null;
        };
        compose: {
            enabled: boolean;
            model_override?: string | null;
            voice_override?: string | null;
            instructions_append?: string | null;
        };
        session_summary: {
            enabled: boolean;
            model_override?: string | null;
            instructions_append?: string | null;
        };
    };
    process: CompanionPipelineProcessStep[];
    post_compose: CompanionPipelinePostComposeStep[];
}

export interface WorkspacePipelinePreviewResponse {
    version: number;
    models: Record<string, string | null | undefined>;
    interpret_system: string;
    compose_system: string;
    session_summary_system: string;
    process: Array<{
        id: string;
        kind: string;
        enabled: boolean;
        name: string;
        model: string | null;
        description: string;
        max_iterations: number;
        questions: string[];
    }>;
    post_compose: Array<{
        id: string;
        enabled: boolean;
        name: string;
        model: string | null;
        output_key: string;
        replace_streamed_reply: boolean;
        user_prompt_rendered: string;
    }>;
}

export interface Workspace {
    id: string;
    owner_user_id: string;
    name: string;
    runtime_configuration: Record<string, unknown>;
    ui_configuration: Record<string, unknown>;
    interaction_configuration: Record<string, unknown>;
    /** Workflow definition UUIDs enabled for this Workspace (intersected with Companion). */
    enabled_workflow_ids: string[];
    /** LM Studio model id for interpret / routing (structured JSON); compose uses Companion Persona. */
    interpretation_model?: string | null;
    created_at: string;
    updated_at: string;
}

/** Partial update for PUT /workspaces/{id} — omit fields you do not want to change. */
export interface WorkspaceUpdate {
    name?: string;
    runtime_configuration?: Record<string, unknown>;
    ui_configuration?: Record<string, unknown>;
    interaction_configuration?: Record<string, unknown>;
    enabled_workflow_ids?: string[];
    interpretation_model?: string | null;
}

export interface WorkspaceSession {
    id: string;
    workspace_id: string;
    companion_id: string;
    title: string;
    status: string;
    turn_count: number;
    transient_state: Record<string, unknown>;
    active_summary: string;
    last_turn_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface WorkspaceSessionCreate {
    title?: string;
}

export interface WorkspaceBootstrapResponse {
    companion: Companion;
    workspace: Workspace;
    session: WorkspaceSession;
}

export interface WorkspaceTurn {
    id: string;
    session_id: string;
    turn_index: number;
    trace_id: string;
    user_input: string;
    outcome_type: string;
    created_at: string;
}

/** Redacted stage payloads from GET .../turns/{tid} (Workspace Console). */
export interface WorkspaceTurnTraces {
    interpretation_result?: Record<string, unknown> | null;
    routing_plan?: Record<string, unknown> | null;
    execution_results?: Record<string, unknown> | null;
    process_results?: Record<string, unknown> | null;
    composition_result?: Record<string, unknown> | null;
    delivered_response?: Record<string, unknown> | null;
}

export interface WorkspaceTurnDetail {
    id: string;
    session_id: string;
    turn_index: number;
    trace_id: string;
    user_input: string;
    outcome_type: string;
    created_at: string;
    traces: WorkspaceTurnTraces;
}
