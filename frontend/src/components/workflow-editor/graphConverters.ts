import { MarkerType, type Node, type Edge } from '@xyflow/react';
import type {
    BinaryIntUtilityType,
    GraphNode as AppGraphNode,
    GraphEdge as AppGraphEdge,
    ForLoopControlNode,
    MultimodalLLMCallSkillNode,
    RequiredInput,
    WorkflowDefinitionListItemHydrated,
} from '../../api/types';
import { DEFAULT_SANDBOX_DECISION_ACTION, isSandboxDecisionAction } from '../../domain/sandbox/decisionActions';
import { resolveWorkflowPaletteColor } from '../../domain/paletteDefaults';
import { reactFlowTypeForAppNode } from './stepKindRegistry';
import { normalizeAnnotationTextAlign } from './annotationTextAlign';

export const genId = () => `n_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

/** React Flow types for editor-only annotations (not in shared step manifest). */
export const ANNOTATION_FLOW_NODE_TYPES = ['annotationNote', 'annotationRegion'] as const;

/** Default note dimensions when `data.width` / `data.height` are missing (matches palette / drop). */
export const ANNOTATION_NOTE_DEFAULT_WIDTH = 280;
export const ANNOTATION_NOTE_DEFAULT_HEIGHT = 160;
/** Default header label font size (px); matches former `text-[10px]` chrome. */
export const ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX = 10;

/** Note canvas stacking; kept below edges (`1000`), above regions (negative z). */
export const ANNOTATION_NOTE_DEFAULT_Z_INDEX = 0;
export const ANNOTATION_NOTE_Z_INDEX_MIN = 0;
export const ANNOTATION_NOTE_Z_INDEX_MAX = 999;

export function clampAnnotationNoteZIndex(raw: unknown): number {
    const z =
        typeof raw === 'number' && Number.isFinite(raw)
            ? Math.round(raw)
            : ANNOTATION_NOTE_DEFAULT_Z_INDEX;
    return Math.min(ANNOTATION_NOTE_Z_INDEX_MAX, Math.max(ANNOTATION_NOTE_Z_INDEX_MIN, z));
}

/** Region canvas stacking; kept below notes (`0`…`999`) and edges (`1000`). */
export const ANNOTATION_REGION_DEFAULT_Z_INDEX = -10;
export const ANNOTATION_REGION_Z_INDEX_MIN = -1000;
export const ANNOTATION_REGION_Z_INDEX_MAX = -1;

export function clampAnnotationRegionZIndex(raw: unknown): number {
    const z =
        typeof raw === 'number' && Number.isFinite(raw)
            ? Math.round(raw)
            : ANNOTATION_REGION_DEFAULT_Z_INDEX;
    return Math.min(ANNOTATION_REGION_Z_INDEX_MAX, Math.max(ANNOTATION_REGION_Z_INDEX_MIN, z));
}

export function isAnnotationFlowNodeType(nodeType: string | undefined | null): boolean {
    return nodeType != null && (ANNOTATION_FLOW_NODE_TYPES as readonly string[]).includes(nodeType);
}

/** React Flow explorer: show Last Run / session output override chrome for this step type (editor-only annotations excluded). */
export function showInspectorLastRunExplorerSection(nodeType: string | undefined | null): boolean {
    return !isAnnotationFlowNodeType(nodeType);
}

function parseStyleDimension(v: unknown, fallback: number): number {
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
        const n = parseFloat(v);
        if (Number.isFinite(n)) return n;
    }
    return fallback;
}

/** Accept use_now / useNow on node data or graph node root (matches executor normalization). */
export function coerceDatetimePrimitiveUseNow(
    data: Record<string, unknown> | undefined,
    root?: Record<string, unknown>,
): boolean {
    const d = data ?? {};
    const r = root ?? {};
    const pick = d['use_now'] ?? d['useNow'] ?? r['use_now'] ?? r['useNow'];
    if (pick === true) return true;
    if (pick === false || pick === null || pick === undefined) return false;
    if (typeof pick === 'number' && pick === 1) return true;
    if (typeof pick === 'string') {
        const s = pick.trim().toLowerCase();
        return s === 'true' || s === '1' || s === 'yes' || s === 'on';
    }
    return Boolean(pick);
}

const UPSERT_ALLOWED_KEYS = new Set(['name', 'content', 'existing_document_id', 'write_mode']);

/** Persisted edges may target these instead of Upsert Document `content` (mirror executor aliasing). */
export const UPSERT_DOCUMENT_CONTENT_TARGET_ALIASES = new Set(['output', 'text', 'body', 'markdown']);

/**
 * Persisted Upsert Document `required_inputs`.
 * Missing or empty list → legacy full template (four handles).
 * Explicit non-empty lists keep only keys the graph stores (typically `name` + `content`); optional
 * `existing_document_id` / `write_mode` are emitted only when present in the filtered source.
 */
export function normalizeUpsertDocumentRequiredInputs(
    requiredInputsUnknown: RequiredInput[] | undefined | null,
): RequiredInput[] {
    const legacyFull = (): RequiredInput[] => [
        { key: 'name', type: 'string', value: '' },
        { key: 'content', type: 'string', value: '' },
        { key: 'existing_document_id', type: 'string', value: null },
        { key: 'write_mode', type: 'string', value: 'replace' },
    ];
    if (!Array.isArray(requiredInputsUnknown) || requiredInputsUnknown.length === 0) {
        return legacyFull();
    }
    const filtered = requiredInputsUnknown.filter(
        r =>
            typeof r?.key === 'string' &&
            UPSERT_ALLOWED_KEYS.has(r.key),
    );
    if (filtered.length === 0) {
        return legacyFull();
    }
    const presentKeys = new Set(filtered.map(r => String(r.key)));
    const byKey = new Map<string, RequiredInput>();
    for (const ri of filtered) {
        const k = String(ri.key);
        byKey.set(k, ri);
    }
    if (!byKey.has('name')) {
        byKey.set('name', { key: 'name', type: 'string', value: '' });
    }
    if (!byKey.has('content')) {
        byKey.set('content', { key: 'content', type: 'string', value: '' });
    }
    const out: RequiredInput[] = [byKey.get('name')!, byKey.get('content')!];
    if (presentKeys.has('existing_document_id')) {
        out.push(byKey.get('existing_document_id')!);
    }
    if (presentKeys.has('write_mode')) {
        out.push(byKey.get('write_mode')!);
    }
    return out;
}

const BINARY_INT_UTILITY_API_TYPES = new Set([
    'add_ints',
    'subtract_ints',
    'multiply_ints',
    'divide_ints',
    'modulo_ints',
    'min_ints',
    'max_ints',
]);

function defaultBinaryIntRequiredInputs(): RequiredInput[] {
    return [
        { key: 'input_a', type: 'int', value: 0 },
        { key: 'input_b', type: 'int', value: 0 },
    ];
}

/**
 * LLM-authored exports sometimes nest `primitive_type` / `utility_type` / `control_type` / `skill_type`
 * inside `data`. The API and canvas expect those fields on the node object (next to `kind`).
 */
export function hoistStepDiscriminatorsFromData(n: AppGraphNode): AppGraphNode {
    const d = n.data as Record<string, unknown> | undefined;
    if (!d || typeof d !== 'object' || Array.isArray(d)) return n;

    if (n.kind === 'primitive') {
        const pt = (n as { primitive_type?: string }).primitive_type;
        if (!pt && typeof d.primitive_type === 'string' && d.primitive_type !== '') {
            const { primitive_type: _p, ...rest } = d;
            return { ...n, primitive_type: d.primitive_type as string, data: rest } as AppGraphNode;
        }
    }
    if (n.kind === 'utility') {
        const ut = (n as { utility_type?: string }).utility_type;
        if (!ut && typeof d.utility_type === 'string' && d.utility_type !== '') {
            const { utility_type: _u, ...rest } = d;
            return { ...n, utility_type: d.utility_type as string, data: rest } as AppGraphNode;
        }
    }
    if (n.kind === 'control') {
        const ct = (n as { control_type?: string }).control_type;
        if (!ct && typeof d.control_type === 'string' && d.control_type !== '') {
            const { control_type: _c, ...rest } = d;
            return { ...n, control_type: d.control_type as string, data: rest } as AppGraphNode;
        }
    }
    if (n.kind === 'skill') {
        const st = (n as { skill_type?: string }).skill_type;
        if (!st && typeof d.skill_type === 'string' && d.skill_type !== '') {
            const { skill_type: _s, ...rest } = d;
            return { ...n, skill_type: d.skill_type as string, data: rest } as AppGraphNode;
        }
    }
    if (n.kind === 'annotation') {
        const at = (n as { annotation_type?: string }).annotation_type;
        if (!at && typeof d.annotation_type === 'string' && d.annotation_type !== '') {
            const { annotation_type: _a, ...rest } = d;
            return { ...n, annotation_type: d.annotation_type as string, data: rest } as AppGraphNode;
        }
    }
    return n;
}

export function appNodeToFlow(n: AppGraphNode): Node {
    n = hoistStepDiscriminatorsFromData(n);
    const pos = { x: n.position?.x ?? 100, y: n.position?.y ?? 100 };
    const isSimpleLlmAppNode =
        (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'simple_llm_call') ||
        (n.kind === 'utility' && (n as AppGraphNode & { utility_type?: string }).utility_type === 'simple_llm_call');
    if (isSimpleLlmAppNode) {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'user_prompt')
            : [{ key: 'user_prompt', type: 'string' as const, value: null }];
        if (requiredInputs.length === 0) requiredInputs.push({ key: 'user_prompt', type: 'string' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                persona_id: d?.persona_id ?? null,
                structure_id: d?.structure_id ?? null,
                additional_system_prompt_context: d?.additional_system_prompt_context ?? null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'multimodal_llm') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const mmKeys = ['user_prompt', 'images', 'additional_context', 'structure'] as const;
        for (const key of mmKeys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === key)) {
                requiredInputs.push({
                    key,
                    type:
                        key === 'user_prompt'
                            ? ('string' as const)
                            : key === 'images'
                              ? ('list' as const)
                              : key === 'structure'
                                ? ('structure' as const)
                                : ('string' as const),
                    value: null,
                });
            }
        }
        requiredInputs = requiredInputs.filter((r: { key?: string }) => mmKeys.includes(r?.key as (typeof mmKeys)[number]));
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                persona_id: d?.persona_id ?? null,
                structure_id: d?.structure_id ?? null,
                additional_system_prompt_context: d?.additional_system_prompt_context ?? null,
                model: d?.model ?? null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'text_to_speech') {
        const d = n.data as any;
        const requiredInputs =
            Array.isArray(d?.required_inputs) && d.required_inputs.some((r: { key?: string }) => r?.key === 'text')
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'text')
                : [{ key: 'text', type: 'string' as const, value: null }];
        const rawOpts = d?.tts_options;
        const tts_options =
            rawOpts != null && typeof rawOpts === 'object' && !Array.isArray(rawOpts) ? { ...rawOpts } : {};
        const tw = d?.tts_playback_when;
        const hasTw = tw === 'inline' || tw === 'manual' || tw === 'after_workflow';
        const ap = d?.auto_play_tts_on_node_end;
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                tts_model_id: d?.tts_model_id ?? null,
                voice_sample_id: d?.voice_sample_id ?? null,
                engine: d?.engine ?? null,
                tts_options,
                ...(hasTw ? { tts_playback_when: tw } : {}),
                ...(!hasTw && (ap === true || ap === false) ? { auto_play_tts_on_node_end: ap } : {}),
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'transcribe_audio') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const taskNorm = task === 'translate' ? 'translate' : 'transcribe';
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
                task: taskNorm,
                model: typeof d?.model === 'string' && d.model.trim() !== '' ? d.model.trim() : null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'audio_file_input') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const taskNorm = task === 'translate' ? 'translate' : 'transcribe';
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                audio_artifact_id:
                    typeof d?.audio_artifact_id === 'string' && d.audio_artifact_id.trim() !== ''
                        ? d.audio_artifact_id.trim()
                        : null,
                language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
                task: taskNorm,
                model: typeof d?.model === 'string' && d.model.trim() !== '' ? d.model.trim() : null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'transcribe_file') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const taskNorm = task === 'translate' ? 'translate' : 'transcribe';
        const provider =
            typeof d?.provider === 'string' && d.provider.trim() !== '' ? d.provider.trim() : 'local_whisper';
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                provider,
                audio_artifact_id:
                    typeof d?.audio_artifact_id === 'string' && d.audio_artifact_id.trim() !== ''
                        ? d.audio_artifact_id.trim()
                        : null,
                language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
                task: taskNorm,
                prompt: typeof d?.prompt === 'string' && d.prompt.trim() !== '' ? d.prompt.trim() : null,
                diarization_enabled: Boolean(d?.diarization_enabled),
                include_word_timestamps: Boolean(d?.include_word_timestamps),
                provider_model_id:
                    typeof d?.provider_model_id === 'string' && d.provider_model_id.trim() !== ''
                        ? d.provider_model_id.trim()
                        : null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'gmail_list_messages') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const gmailKeys = ['after', 'before', 'unread_only', 'query', 'max_results'] as const;
        for (const key of gmailKeys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === key)) {
                if (key === 'max_results') {
                    requiredInputs.push({ key: 'max_results', type: 'int' as const, value: d?.max_results ?? 10 });
                } else if (key === 'unread_only') {
                    requiredInputs.push({
                        key: 'unread_only',
                        type: 'boolean' as const,
                        value: d?.unread_only ?? false,
                    });
                } else {
                    requiredInputs.push({
                        key,
                        type: 'string' as const,
                        value:
                            key === 'after'
                                ? (d?.after ?? null)
                                : key === 'before'
                                  ? (d?.before ?? null)
                                  : key === 'query'
                                    ? (d?.query ?? null)
                                    : null,
                    });
                }
            }
        }
        requiredInputs = requiredInputs.filter((r: { key?: string }) =>
            gmailKeys.includes(r?.key as (typeof gmailKeys)[number]),
        );
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                google_connection_id: d?.google_connection_id ?? null,
                max_results: d?.max_results ?? 10,
                unread_only: d?.unread_only ?? false,
                after: d?.after ?? null,
                before: d?.before ?? null,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'calendar_list_events') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const hasA = requiredInputs.some((r: { key?: string }) => r?.key === 'time_min');
        const hasB = requiredInputs.some((r: { key?: string }) => r?.key === 'time_max');
        if (!hasA) requiredInputs.push({ key: 'time_min', type: 'string' as const, value: null });
        if (!hasB) requiredInputs.push({ key: 'time_max', type: 'string' as const, value: null });
        requiredInputs = requiredInputs.filter(
            (r: { key?: string }) => r?.key === 'time_min' || r?.key === 'time_max',
        );
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                google_connection_id: d?.google_connection_id ?? null,
                calendar_id: d?.calendar_id ?? 'primary',
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'fetch_url') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const hasU = requiredInputs.some((r: { key?: string }) => r?.key === 'url');
        if (!hasU) requiredInputs.push({ key: 'url', type: 'string' as const, value: null });
        requiredInputs = requiredInputs.filter((r: { key?: string }) => r?.key === 'url');
        const pol = d?.cache_policy;
        const cachePolicy =
            pol === 'refresh' || pol === 'bypass' || pol === 'default' ? pol : 'default';
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                url: d?.url ?? '',
                method: d?.method ?? 'GET',
                headers: d?.headers && typeof d.headers === 'object' && !Array.isArray(d.headers) ? d.headers : {},
                timeout_ms: d?.timeout_ms ?? null,
                cache_policy: cachePolicy,
            },
        };
    }
    if (n.kind === 'skill' && (n as AppGraphNode & { skill_type?: string }).skill_type === 'capture_url_snapshot') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const hasU = requiredInputs.some((r: { key?: string }) => r?.key === 'url');
        if (!hasU) requiredInputs.push({ key: 'url', type: 'string' as const, value: null });
        requiredInputs = requiredInputs.filter((r: { key?: string }) => r?.key === 'url');
        const pol = d?.cache_policy;
        const cachePolicy =
            pol === 'refresh' || pol === 'bypass' || pol === 'default' ? pol : 'default';
        const wu = d?.wait_until;
        const waitUntil =
            wu === 'domcontentloaded' || wu === 'networkidle' || wu === 'load' ? wu : 'load';
        const fp = d?.full_page;
        const fullPage = fp === undefined || fp === null ? true : Boolean(fp);
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                url: d?.url ?? '',
                full_page: fullPage,
                viewport_width: d?.viewport_width ?? null,
                viewport_height: d?.viewport_height ?? null,
                wait_until: waitUntil,
                timeout_ms: d?.timeout_ms ?? null,
                cache_policy: cachePolicy,
            },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'list_to_string') {
        const d = (n.data ?? {}) as {
            use_text_join?: boolean;
            add_line_breaks_between_items?: boolean;
        };
        const data: Record<string, unknown> = { label: n.label };
        if (d.use_text_join === true) {
            data.use_text_join = true;
            data.add_line_breaks_between_items = d.add_line_breaks_between_items !== false;
        } else if (d.use_text_join === false) {
            data.use_text_join = false;
            if (d.add_line_breaks_between_items !== undefined) {
                data.add_line_breaks_between_items = Boolean(d.add_line_breaks_between_items);
            }
        }
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data };
    }
    if (n.kind === 'utility' && n.utility_type === 'string_to_list') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'len_from_list') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'random_item_from_list') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_tick_items') {
        const d = n.data as { item_type?: string } | undefined;
        const item_type = d?.item_type === 'food' ? 'food' : 'all';
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, item_type } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_world_grid') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_available_cells') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_tick_pet') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_nearest_item_by_type') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'sandbox_tick' || r?.key === 'item_type')
            : [
                  { key: 'sandbox_tick', type: 'dictionary' as const, value: null },
                  { key: 'item_type', type: 'string' as const, value: 'food' },
              ];
        const hasTick = requiredInputs.some((r: { key?: string }) => r?.key === 'sandbox_tick');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasTick) requiredInputs.push({ key: 'sandbox_tick', type: 'dictionary' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_closest_item') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'sandbox_tick' || r?.key === 'item_type')
            : [
                  { key: 'sandbox_tick', type: 'dictionary' as const, value: null },
                  { key: 'item_type', type: 'string' as const, value: 'food' },
              ];
        const hasTick = requiredInputs.some((r: { key?: string }) => r?.key === 'sandbox_tick');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasTick) requiredInputs.push({ key: 'sandbox_tick', type: 'dictionary' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_decision_move_to') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'target_item_id' || r?.key === 'target_cell' || r?.key === 'reason',
              )
            : [
                  { key: 'target_item_id', type: 'string' as const, value: null },
                  { key: 'target_cell', type: 'dictionary' as const, value: null },
                  { key: 'reason', type: 'string' as const, value: null },
              ];
        const keys = ['target_item_id', 'target_cell', 'reason'] as const;
        for (const k of keys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === k)) {
                if (k === 'target_item_id') {
                    requiredInputs.push({ key: 'target_item_id', type: 'string' as const, value: null });
                } else if (k === 'target_cell') {
                    requiredInputs.push({ key: 'target_cell', type: 'dictionary' as const, value: null });
                } else {
                    requiredInputs.push({ key: 'reason', type: 'string' as const, value: null });
                }
            }
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_starter_decision') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_filter_items_by_type') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'items' || r?.key === 'item_type')
            : [
                  { key: 'items', type: 'list' as const, value: null },
                  { key: 'item_type', type: 'string' as const, value: 'food' },
              ];
        const hasItems = requiredInputs.some((r: { key?: string }) => r?.key === 'items');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasItems) requiredInputs.push({ key: 'items', type: 'list' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_decision_intent') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'action' ||
                      r?.key === 'target_item_id' ||
                      r?.key === 'target_cell' ||
                      r?.key === 'reason',
              )
            : [
                  { key: 'action', type: 'string' as const, value: 'wander' },
                  { key: 'target_item_id', type: 'string' as const, value: null },
                  { key: 'target_cell', type: 'dictionary' as const, value: null },
                  { key: 'reason', type: 'string' as const, value: null },
              ];
        const keys = ['action', 'target_item_id', 'target_cell', 'reason'] as const;
        for (const k of keys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === k)) {
                if (k === 'action') requiredInputs.push({ key: 'action', type: 'string' as const, value: 'wander' });
                else if (k === 'target_item_id') {
                    requiredInputs.push({ key: 'target_item_id', type: 'string' as const, value: null });
                } else if (k === 'target_cell') {
                    requiredInputs.push({ key: 'target_cell', type: 'dictionary' as const, value: null });
                } else {
                    requiredInputs.push({ key: 'reason', type: 'string' as const, value: null });
                }
            }
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_pet_hunger') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_pet_energy') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_pet_cell') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_is_nearby8') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'cell_a' || r?.key === 'cell_b')
            : [
                  { key: 'cell_a', type: 'dictionary' as const, value: null },
                  { key: 'cell_b', type: 'dictionary' as const, value: null },
              ];
        const hasA = requiredInputs.some((r: { key?: string }) => r?.key === 'cell_a');
        const hasB = requiredInputs.some((r: { key?: string }) => r?.key === 'cell_b');
        if (!hasA) requiredInputs.push({ key: 'cell_a', type: 'dictionary' as const, value: null });
        if (!hasB) requiredInputs.push({ key: 'cell_b', type: 'dictionary' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_first_nearby_food') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'sandbox_first_food_world_order') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'int_to_string') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'utility' && n.utility_type === 'list_item_by_index') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'index' || r?.key === 'list')
            : [{ key: 'index', type: 'int' as const, value: 0 }, { key: 'list', type: 'list' as const, value: null }];
        const hasIndex = requiredInputs.some((r: { key?: string }) => r?.key === 'index');
        const hasList = requiredInputs.some((r: { key?: string }) => r?.key === 'list');
        if (!hasIndex) requiredInputs.push({ key: 'index', type: 'int' as const, value: 0 });
        if (!hasList) requiredInputs.push({ key: 'list', type: 'list' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'dictionary_value_by_key') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'key' || r?.key === 'dictionary' || r?.key === 'fallback',
              )
            : [
                  { key: 'key', type: 'string' as const, value: '' },
                  { key: 'dictionary', type: 'dictionary' as const, value: null },
                  { key: 'fallback', type: 'any' as const, value: null },
              ];
        const hasKey = requiredInputs.some((r: { key?: string }) => r?.key === 'key');
        const hasDict = requiredInputs.some((r: { key?: string }) => r?.key === 'dictionary');
        const hasFb = requiredInputs.some((r: { key?: string }) => r?.key === 'fallback');
        if (!hasKey) requiredInputs.push({ key: 'key', type: 'string' as const, value: '' });
        if (!hasDict) requiredInputs.push({ key: 'dictionary', type: 'dictionary' as const, value: null });
        if (!hasFb) requiredInputs.push({ key: 'fallback', type: 'any' as const, value: null });
        const ovt = d?.output_value_type;
        const output_value_type =
            ovt === 'string' || ovt === 'list' || ovt === 'dictionary' || ovt === 'boolean' || ovt === 'int' || ovt === 'datetime'
                ? ovt
                : 'list';
        const outData: Record<string, unknown> = {
            label: n.label,
            required_inputs: requiredInputs,
            output_value_type,
        };
        if (d != null && Object.prototype.hasOwnProperty.call(d, 'fallback_value')) {
            outData.fallback_value = d.fallback_value;
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: outData,
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'dictionary_set_value_by_key') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) =>
                r?.key === 'dictionary' || r?.key === 'key' || r?.key === 'value',
            )
            : [
                  { key: 'dictionary', type: 'dictionary' as const, value: null },
                  { key: 'key', type: 'string' as const, value: '' },
                  { key: 'value', type: 'any' as const, value: null },
              ];
        const hasDict = requiredInputs.some((r: { key?: string }) => r?.key === 'dictionary');
        const hasKey = requiredInputs.some((r: { key?: string }) => r?.key === 'key');
        const hasVal = requiredInputs.some((r: { key?: string }) => r?.key === 'value');
        if (!hasDict) requiredInputs.push({ key: 'dictionary', type: 'dictionary' as const, value: null });
        if (!hasKey) requiredInputs.push({ key: 'key', type: 'string' as const, value: '' });
        if (!hasVal) requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'read_document_property') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'target_property' || r?.key === 'document')
            : [
                  { key: 'target_property', type: 'string' as const, value: '' },
                  { key: 'document', type: 'document' as const, value: null },
              ];
        const hasTp = requiredInputs.some((r: { key?: string }) => r?.key === 'target_property');
        const hasDoc = requiredInputs.some((r: { key?: string }) => r?.key === 'document');
        if (!hasTp) requiredInputs.push({ key: 'target_property', type: 'string' as const, value: '' });
        if (!hasDoc) requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        const ovt = d?.output_value_type;
        const output_value_type =
            ovt === 'string' || ovt === 'list' || ovt === 'dictionary' || ovt === 'boolean' || ovt === 'int' ? ovt : 'string';
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs, output_value_type },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'load_document') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document_id' || r?.key === 'document_name')
            : [
                  { key: 'document_id', type: 'string' as const, value: null },
                  { key: 'document_name', type: 'string' as const, value: null },
              ];
        const hasId = requiredInputs.some((r: { key?: string }) => r?.key === 'document_id');
        const hasName = requiredInputs.some((r: { key?: string }) => r?.key === 'document_name');
        if (!hasId) requiredInputs.push({ key: 'document_id', type: 'string' as const, value: null });
        if (!hasName) requiredInputs.push({ key: 'document_name', type: 'string' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'upsert_document') {
        const d = n.data as any;
        const requiredInputs = normalizeUpsertDocumentRequiredInputs(d?.required_inputs);
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'parse_document_body') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document')
            : [{ key: 'document', type: 'document' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'document')) {
            requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'html_parse_basic') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'html')
            : [{ key: 'html', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'html')) {
            requiredInputs.push({ key: 'html', type: 'string' as const, value: null });
        }
        const hpData: Record<string, unknown> = { label: n.label, required_inputs: requiredInputs };
        if (d && Object.prototype.hasOwnProperty.call(d, 'granularity')) {
            hpData.granularity = d.granularity;
        }
        if (d && Object.prototype.hasOwnProperty.call(d, 'content_root_css')) {
            hpData.content_root_css = d.content_root_css;
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: hpData,
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'write_object_to_document_body') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
            : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'append_value_to_document') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document' || r?.key === 'value')
            : [
                  { key: 'document', type: 'document' as const, value: null },
                  { key: 'value', type: 'any' as const, value: null },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'document')) {
            requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'validate_against_structure') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value' || r?.key === 'structure')
            : [
                  { key: 'value', type: 'any' as const, value: null },
                  { key: 'structure', type: 'structure' as const, value: null },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'structure')) {
            requiredInputs.push({ key: 'structure', type: 'structure' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                structure_id: d?.structure_id ?? null,
            },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'add_to_list') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'list' || r?.key === 'value')
            : [{ key: 'list', type: 'list' as const, value: null }, { key: 'value', type: 'any' as const, value: null }];
        const hasList = requiredInputs.some((r: { key?: string }) => r?.key === 'list');
        const hasVal = requiredInputs.some((r: { key?: string }) => r?.key === 'value');
        if (!hasList) requiredInputs.push({ key: 'list', type: 'list' as const, value: null });
        if (!hasVal) requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'add_days') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input' || r?.key === 'days')
            : [{ key: 'input', type: 'datetime' as const, value: null }, { key: 'days', type: 'int' as const, value: 0 }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'datetime' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'days')) {
            requiredInputs.push({ key: 'days', type: 'int' as const, value: 0 });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && BINARY_INT_UTILITY_API_TYPES.has(n.utility_type)) {
        const d = n.data as { required_inputs?: RequiredInput[] };
        const requiredInputs =
            Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                ? d.required_inputs.filter(
                      (r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b',
                  )
                : defaultBinaryIntRequiredInputs();
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) {
            requiredInputs.push({ key: 'input_a', type: 'int', value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) {
            requiredInputs.push({ key: 'input_b', type: 'int', value: 0 });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'prepend_text') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'target_string' || r?.key === 'text_to_prepend')
            : [{ key: 'target_string', type: 'string' as const, value: null }, { key: 'text_to_prepend', type: 'string' as const, value: null }];
        const hasTarget = requiredInputs.some((r: { key?: string }) => r?.key === 'target_string');
        const hasPrepend = requiredInputs.some((r: { key?: string }) => r?.key === 'text_to_prepend');
        if (!hasTarget) requiredInputs.push({ key: 'target_string', type: 'string' as const, value: null });
        if (!hasPrepend) requiredInputs.push({ key: 'text_to_prepend', type: 'string' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                add_additional_line: d?.add_additional_line ?? false,
            },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'string_trunc') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'target_string' || r?.key === 'start_index' || r?.key === 'end_index',
              )
            : [
                  { key: 'target_string', type: 'string' as const, value: null },
                  { key: 'start_index', type: 'int' as const, value: 0 },
                  { key: 'end_index', type: 'int' as const, value: -1 },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'target_string')) {
            requiredInputs.push({ key: 'target_string', type: 'string' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'start_index')) {
            requiredInputs.push({ key: 'start_index', type: 'int' as const, value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'end_index')) {
            requiredInputs.push({ key: 'end_index', type: 'int' as const, value: -1 });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'utility' && n.utility_type === 'message') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'message')
            : [{ key: 'message', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'message')) {
            requiredInputs.push({ key: 'message', type: 'string' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'control' && (n as any).control_type === 'basic_conditional') {
        const d = n.data as any;
        let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'condition')
            : [{ key: 'condition', type: 'boolean' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'condition')) {
            requiredInputs.push({ key: 'condition', type: 'boolean' as const, value: null });
        }
        requiredInputs = requiredInputs.map(r => r.key === 'condition' ? { ...r, type: 'boolean' as const } : r);
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                condition: d?.condition ?? null,
            },
        };
    }
    if (n.kind === 'control' && (n as any).control_type === 'is') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
            : [{ key: 'input_a', type: 'string' as const, value: null }, { key: 'input_b', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'string' as const, value: null });
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'string' as const, value: null });
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'control' && (n as any).control_type === 'is_empty') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
            : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    const comparisonTypes = ['gt', 'lt', 'gte', 'lte'] as const;
    for (const ctype of comparisonTypes) {
        if (n.kind === 'control' && (n as any).control_type === ctype) {
            const d = n.data as any;
            const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
                : [{ key: 'input_a', type: 'string' as const, value: null }, { key: 'input_b', type: 'string' as const, value: null }];
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'string' as const, value: null });
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'string' as const, value: null });
            return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, required_inputs: requiredInputs } };
        }
    }
    const logicalTypes = ['and', 'or', 'xor'] as const;
    for (const _ctype of logicalTypes) {
        if (n.kind === 'control' && (n as any).control_type === _ctype) {
            const d = n.data as any;
            const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
                : [{ key: 'input_a', type: 'boolean' as const, value: null }, { key: 'input_b', type: 'boolean' as const, value: null }];
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'boolean' as const, value: null });
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'boolean' as const, value: null });
            return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, required_inputs: requiredInputs } };
        }
    }
    if (n.kind === 'control' && (n as any).control_type === 'not') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input')
            : [{ key: 'input', type: 'boolean' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'boolean' as const, value: null });
        }
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, required_inputs: requiredInputs } };
    }
    if (n.kind === 'control' && (n as any).control_type === 'between') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) => r?.key === 'low' || r?.key === 'value' || r?.key === 'high',
              )
            : [
                  { key: 'low', type: 'int' as const, value: 0 },
                  { key: 'value', type: 'int' as const, value: 0 },
                  { key: 'high', type: 'int' as const, value: 0 },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'low')) {
            requiredInputs.push({ key: 'low', type: 'int', value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'int', value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'high')) {
            requiredInputs.push({ key: 'high', type: 'int', value: 0 });
        }
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, required_inputs: requiredInputs } };
    }
    if (n.kind === 'control' && (n as any).control_type === 'try_catch') {
        const tcData = (n.data as any) ?? {};
        let requiredInputs =
            Array.isArray(tcData.required_inputs) && tcData.required_inputs.length > 0
                ? tcData.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
                : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        requiredInputs = requiredInputs.map((r: RequiredInput) =>
            r.key === 'value' ? { ...r, type: 'any' as const } : r,
        );
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, required_inputs: requiredInputs },
        };
    }
    if (n.kind === 'control' && (n as any).control_type === 'for_loop') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input')
            : [{ key: 'input', type: 'list' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'list' as const, value: null });
        }
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_inputs: requiredInputs,
                ...(d?.parallel_iterations === true ? { parallel_iterations: true } : {}),
                ...(typeof d?.iteration_mode === 'string'
                    ? { iteration_mode: d.iteration_mode }
                    : d?.parallel_iterations === true &&
                        !(typeof d?.iteration_mode === 'string' && d.iteration_mode !== '')
                      ? { iteration_mode: 'parallel' as const }
                      : {}),
                ...(typeof d?.batch_size === 'number' && Number.isFinite(d.batch_size)
                    ? { batch_size: d.batch_size }
                    : {}),
                ...(d?.continue_on_error === true ? { continue_on_error: true } : {}),
                ...(typeof d?.max_iterations === 'number' && Number.isFinite(d.max_iterations)
                    ? { max_iterations: d.max_iterations }
                    : {}),
            },
        };
    }
    if (n.kind === 'control' && (n as any).control_type === 'for_loop_end') {
        const d = n.data as any;
        const exports =
            Array.isArray(d?.exports) && d.exports.length > 0 ? d.exports : ['odds', 'evens'];
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                for_loop_id: d?.for_loop_id ?? '',
                exports,
            },
        };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'structure') {
        const d = n.data as any;
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: d?.label ?? 'Structure', structure_id: d?.structure_id ?? '' } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'document') {
        const d = n.data as any;
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: d?.label ?? 'Document', document_id: d?.document_id ?? '' } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'image') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs
            : [{ key: 'image', type: 'dictionary' as const, value: null }];
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: d?.label ?? 'Image',
                artifact_id: d?.artifact_id ?? '',
                required_inputs: requiredInputs,
            },
        };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'gmail') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs
            : [{ key: 'gmail', type: 'gmail' as const, value: null }];
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: d?.label ?? 'Gmail',
                message: d?.message ?? {},
                required_inputs: requiredInputs,
            },
        };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'sandbox_behavior') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'decision_action') {
        const d = n.data as { action?: string } | undefined;
        const raw = d?.action;
        const action =
            typeof raw === 'string' && isSandboxDecisionAction(raw) ? raw : DEFAULT_SANDBOX_DECISION_ACTION;
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, action } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'sandbox_tick') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'string') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, text: (n.data as any)?.text ?? '' } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'list') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, data: (n as any).data ?? [] } };
    }
    if (n.kind === 'primitive' && n.primitive_type === 'dictionary') {
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, data: (n as any).data ?? {} } };
    }
    if (n.kind === 'primitive' && (n as any).primitive_type === 'boolean') {
        const d = n.data as any;
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, value: d?.value ?? false } };
    }
    if (n.kind === 'primitive' && (n as any).primitive_type === 'int') {
        const d = n.data as any;
        return { id: n.id, type: reactFlowTypeForAppNode(n), position: pos, data: { label: n.label, value: d?.value ?? 0 } };
    }
    if (n.kind === 'primitive' && (n as any).primitive_type === 'datetime') {
        const d = n.data as any;
        const root = n as unknown as Record<string, unknown>;
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                iso: d?.iso ?? null,
                use_now: coerceDatetimePrimitiveUseNow(d as Record<string, unknown>, root),
            },
        };
    }
    if (n.kind === 'start') {
        const d = n.data as any;
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                text: d?.text ?? '',
                required_inputs: d?.required_inputs,
            },
        };
    }
    if (n.kind === 'stop') {
        const d = n.data as any;
        const sp = d?.stop_priority;
        const stopPriority =
            typeof sp === 'number'
                ? sp
                : sp != null && String(sp).trim() !== '' && !Number.isNaN(Number(sp))
                  ? Number(sp)
                  : undefined;
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: {
                label: n.label,
                required_outputs: d?.required_outputs ?? [{ key: 'output', type: 'string' as const }],
                ...(stopPriority !== undefined ? { stop_priority: stopPriority } : {}),
            },
        };
    }
    if (n.kind === 'workflow') {
        const d = n.data as { workflow_id: string };
        return {
            id: n.id,
            type: reactFlowTypeForAppNode(n),
            position: pos,
            data: { label: n.label, workflow_id: d?.workflow_id ?? '' },
        };
    }
    if (n.kind === 'annotation') {
        const ann = n as AppGraphNode & { annotation_type?: string };
        if (ann.annotation_type === 'note') {
            const d = (ann as {
                data?: {
                    text?: string;
                    color?: string | null;
                    label_font_size_px?: number;
                    content_font_size_px?: number;
                    label_align?: string;
                    content_align?: string;
                    width?: number;
                    height?: number;
                    z_index?: number;
                };
            }).data ?? {};
            const cfs =
                typeof d.content_font_size_px === 'number' && Number.isFinite(d.content_font_size_px)
                    ? d.content_font_size_px
                    : 12;
            const lfs =
                typeof d.label_font_size_px === 'number' && Number.isFinite(d.label_font_size_px)
                    ? d.label_font_size_px
                    : ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX;
            const w =
                typeof d.width === 'number' && Number.isFinite(d.width) ? d.width : ANNOTATION_NOTE_DEFAULT_WIDTH;
            const h =
                typeof d.height === 'number' && Number.isFinite(d.height) ? d.height : ANNOTATION_NOTE_DEFAULT_HEIGHT;
            const labelAlign = normalizeAnnotationTextAlign(d.label_align);
            const contentAlign = normalizeAnnotationTextAlign(d.content_align);
            const ziNote = clampAnnotationNoteZIndex(d.z_index);
            return {
                id: n.id,
                type: reactFlowTypeForAppNode(n),
                position: pos,
                zIndex: ziNote,
                selectable: true,
                connectable: false,
                style: { width: w, height: h },
                data: {
                    label: n.label,
                    text: typeof d.text === 'string' ? d.text : '',
                    color: d.color ?? null,
                    label_font_size_px: lfs,
                    content_font_size_px: cfs,
                    label_align: labelAlign,
                    content_align: contentAlign,
                    width: w,
                    height: h,
                    z_index: ziNote,
                },
            };
        }
        if (ann.annotation_type === 'region') {
            const d = (ann as {
                data?: {
                    color?: string | null;
                    width?: number;
                    height?: number;
                    label_font_size_px?: number;
                    label_align?: string;
                    z_index?: number;
                };
            }).data ?? {};
            const w = typeof d.width === 'number' && Number.isFinite(d.width) ? d.width : 400;
            const h = typeof d.height === 'number' && Number.isFinite(d.height) ? d.height : 280;
            const lf =
                typeof d.label_font_size_px === 'number' && Number.isFinite(d.label_font_size_px)
                    ? d.label_font_size_px
                    : 11;
            const zi = clampAnnotationRegionZIndex(d.z_index);
            const labelAlign = normalizeAnnotationTextAlign(d.label_align);
            return {
                id: n.id,
                type: reactFlowTypeForAppNode(n),
                position: pos,
                zIndex: zi,
                selectable: true,
                connectable: false,
                style: { width: w, height: h },
                data: {
                    label: n.label,
                    color: d.color ?? null,
                    width: w,
                    height: h,
                    label_font_size_px: lf,
                    label_align: labelAlign,
                    z_index: zi,
                },
            };
        }
    }
    return {
        id: (n as { id: string }).id,
        type: 'invalidStep',
        position: pos,
        data: {
            label: (n as { label?: string }).label ?? (n as { id: string }).id,
            appKind: (n as { kind?: string }).kind ?? 'unknown',
            hint: 'Missing step type field (primitive_type, utility_type, control_type, or skill_type) on the node object. LLM JSON often omits these; add them at the same level as kind.',
            rawNode: n,
        },
    };
}

export function getSourceOutputType(nodes: Node[], sourceId: string, sourceHandle: string | undefined, edges?: Edge[]): string {
    if (sourceHandle === 'signal_out') return 'signal';
    const src = nodes.find(n => n.id === sourceId);
    if (!src) return 'any';
    if (isAnnotationFlowNodeType(src.type)) return 'any';
    if (src.type === 'stringPrimitive') return 'string';
    if (src.type === 'decisionActionPrimitive') return 'string';
    if (src.type === 'sandboxTickPrimitive') return 'dictionary';
    if (src.type === 'listPrimitive') return 'list';
    if (src.type === 'dictionaryPrimitive') return 'dictionary';
    if (src.type === 'booleanPrimitive') return 'boolean';
    if (src.type === 'intPrimitive') return 'int';
    if (src.type === 'dateTimePrimitive') return 'datetime';
    if (src.type === 'structurePrimitive') return 'structure';
    if (src.type === 'documentPrimitive') return 'document';
    if (src.type === 'imagePrimitive') return 'dictionary';
    if (src.type === 'gmailPrimitive') return 'gmail';
    if (src.type === 'sandboxBehaviorPrimitive') return 'dictionary';
    if (
        src.type === 'sandboxTickItems' ||
        src.type === 'sandboxAvailableCells' ||
        src.type === 'sandboxFilterItemsByType' ||
        src.type === 'sandboxNearestItemByType'
    ) {
        return 'list';
    }
    if (
        src.type === 'sandboxWorldGrid' ||
        src.type === 'sandboxTickPet' ||
        src.type === 'sandboxPetCell' ||
        src.type === 'sandboxDecisionMoveTo' ||
        src.type === 'sandboxClosestItem'
    ) {
        return 'dictionary';
    }
    if (src.type === 'sandboxFirstNearbyFood' || src.type === 'sandboxFirstFoodWorldOrder') return 'list';
    if (src.type === 'sandboxPetHunger' || src.type === 'sandboxPetEnergy') return 'int';
    if (src.type === 'sandboxIsNearby8') return 'boolean';
    if (src.type === 'sandboxDecisionIntent' || src.type === 'sandboxStarterDecision') return 'dictionary';
    if (src.type === 'listToString') return 'string';
    if (src.type === 'stringToList') return 'list';
    if (src.type === 'prependText') return 'string';
    if (src.type === 'stringTrunc') return 'string';
    if (src.type === 'messageUtility') return 'string';
    if (src.type === 'lenFromList') return 'int';
    if (src.type === 'randomItemFromList') return 'any';
    if (src.type === 'intToString') return 'string';
    if (
        src.type === 'addInts' ||
        src.type === 'subtractInts' ||
        src.type === 'multiplyInts' ||
        src.type === 'divideInts' ||
        src.type === 'moduloInts' ||
        src.type === 'minInts' ||
        src.type === 'maxInts'
    ) {
        return 'int';
    }
    if (src.type === 'addDays') return 'datetime';
    if (src.type === 'listItemByIndex') return 'any';
    if (src.type === 'dictionaryValueByKey') {
        const d = src.data as { output_value_type?: string };
        const t = d?.output_value_type;
        if (t === 'string' || t === 'list' || t === 'dictionary' || t === 'boolean' || t === 'int' || t === 'datetime')
            return t;
        return 'any';
    }
    if (src.type === 'dictionarySetValueByKey') return 'dictionary';
    if (src.type === 'readDocumentProperty') {
        const d = src.data as { output_value_type?: string };
        const t = d?.output_value_type;
        if (t === 'string' || t === 'list' || t === 'dictionary' || t === 'boolean' || t === 'int' || t === 'datetime')
            return t;
        return 'any';
    }
    if (src.type === 'loadDocument' || src.type === 'upsertDocument') return 'document';
    if (src.type === 'parseDocumentBody') return 'dictionary';
    if (src.type === 'htmlParseBasic') return 'dictionary';
    if (src.type === 'writeObjectToDocumentBody' || src.type === 'appendValueToDocument') return 'string';
    if (src.type === 'validateAgainstStructure') return 'any';
    if (src.type === 'addToList') return 'list';
    if (src.type === 'forLoopControl' && sourceHandle === 'summary') return 'dictionary';
    if (src.type === 'forLoopControl' && sourceHandle === 'item') return 'any';
    if (src.type === 'forLoopEndControl' && sourceHandle === 'output') return 'dictionary';
    if (
        src.type === 'tryCatchControl' &&
        (sourceHandle === 'output' || sourceHandle === 'envelope')
    )
        return 'dictionary';
    const branchControls = [
        'basicConditional',
        'isControl',
        'isEmptyControl',
        'gtControl',
        'ltControl',
        'gteControl',
        'lteControl',
        'betweenControl',
    ];
    if (branchControls.includes(src.type ?? '') && (sourceHandle === 'true' || sourceHandle === 'false')) return 'boolean';
    if (src.type === 'basicConditional') return 'basic_conditional';
    if (src.type === 'isControl') return 'is_control';
    if (src.type === 'isEmptyControl') return 'is_empty';
    if (['gtControl', 'ltControl', 'gteControl', 'lteControl'].includes(src.type ?? '')) return 'gt_control';
    if (['andControl', 'orControl', 'xorControl', 'notControl'].includes(src.type ?? '')) return 'and_control';
    if (src.type === 'simpleLLMCall') {
        const d = src.data as any;
        const hasStructureId = d?.structure_id != null && d?.structure_id !== '';
        const hasStructureEdge = edges?.some(e => e.target === sourceId && e.targetHandle === 'structure');
        return (hasStructureId || hasStructureEdge) ? 'dictionary' : 'string';
    }
    if (src.type === 'multimodalLLMCall') {
        const d = src.data as any;
        const hasStructureId = d?.structure_id != null && d?.structure_id !== '';
        const hasStructureEdge = edges?.some(e => e.target === sourceId && e.targetHandle === 'structure');
        return (hasStructureId || hasStructureEdge) ? 'dictionary' : 'string';
    }
    if (src.type === 'textToSpeech') return 'audio';
    if (src.type === 'transcribeAudio') return 'string';
    if (src.type === 'audioFileInput') return 'string';
    if (src.type === 'transcribeFile') return 'dictionary';
    if (src.type === 'gmailListMessages') return 'list';
    if (src.type === 'calendarListEvents') return 'dictionary';
    if (src.type === 'fetchUrl') return 'dictionary';
    if (src.type === 'captureUrlSnapshot') return 'dictionary';
    if (src.type === 'workflowRef') {
        const d = src.data as any;
        const outputs = d?.subWorkflowRequiredOutputs ?? [{ key: 'output', type: 'string' as const }];
        const out = outputs.find((r: { key?: string }) => r?.key === (sourceHandle ?? 'output'));
        return out?.type ?? 'any';
    }
    if (src.type === 'start') {
        const d = src.data as any;
        const inputs = d?.required_inputs ?? [{ key: 'output', type: 'string' as const }];
        const inp = inputs.find((r: { key?: string }) => r?.key === (sourceHandle ?? 'output'));
        return inp?.type ?? 'string';
    }
    return 'any';
}

export function appEdgeToFlow(e: AppGraphEdge, idx: number, nodes: Node[], paletteColors: Record<string, string>, edges?: AppGraphEdge[]): Edge {
    const type = getSourceOutputType(nodes, e.source, e.source_handle ?? undefined, edges as Edge[]);
    const color = resolveWorkflowPaletteColor(paletteColors, type);
    let sourceHandle = e.source_handle ?? undefined;
    let targetHandle = e.target_handle ?? undefined;
    const targetNode = nodes.find(n => n.id === e.target);
    if (targetNode && (targetNode.type === 'stringPrimitive' || targetNode.type === 'decisionActionPrimitive' || targetNode.type === 'sandboxTickPrimitive' || targetNode.type === 'listPrimitive' || targetNode.type === 'dictionaryPrimitive' || targetNode.type === 'booleanPrimitive' || targetNode.type === 'intPrimitive' || targetNode.type === 'dateTimePrimitive' || targetNode.type === 'listToString' || targetNode.type === 'stringToList' || targetNode.type === 'intToString') && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'input';
    }
    if (targetNode && targetNode.type === 'lenFromList' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'list';
    }
    if (targetNode && targetNode.type === 'randomItemFromList' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'list';
    }
    if (targetNode && targetNode.type === 'listItemByIndex' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'list';
    }
    if (
        targetNode &&
        (targetNode.type === 'sandboxTickItems' ||
            targetNode.type === 'sandboxAvailableCells' ||
            targetNode.type === 'sandboxWorldGrid' ||
            targetNode.type === 'sandboxTickPet' ||
            targetNode.type === 'sandboxStarterDecision' ||
            targetNode.type === 'sandboxPetHunger' ||
            targetNode.type === 'sandboxPetEnergy' ||
            targetNode.type === 'sandboxPetCell' ||
            targetNode.type === 'sandboxFirstNearbyFood' ||
            targetNode.type === 'sandboxFirstFoodWorldOrder') &&
        (targetHandle == null || targetHandle === '')
    ) {
        targetHandle = 'input';
    }
    if (targetNode && targetNode.type === 'sandboxNearestItemByType' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'sandbox_tick';
    }
    if (targetNode && targetNode.type === 'sandboxClosestItem' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'sandbox_tick';
    }
    if (targetNode && targetNode.type === 'sandboxDecisionMoveTo' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'target_item_id';
    }
    if (targetNode && targetNode.type === 'sandboxIsNearby8' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'cell_a';
    }
    if (targetNode && targetNode.type === 'sandboxFilterItemsByType' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'items';
    }
    if (targetNode && targetNode.type === 'sandboxDecisionIntent' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'action';
    }
    if (targetNode && targetNode.type === 'dictionaryValueByKey' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'dictionary';
    }
    if (targetNode && targetNode.type === 'dictionarySetValueByKey' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'dictionary';
    }
    if (targetNode && targetNode.type === 'readDocumentProperty' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'document';
    }
    if (targetNode && targetNode.type === 'loadDocument' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'document_id';
    }
    if (targetNode && targetNode.type === 'upsertDocument' && (targetHandle == null || targetHandle === '')) {
        // Legacy graphs stored null/missing target_handle. Defaulting to `name` caused the next save
        // to persist `target_handle: "name"`, so body wires overwrote Explorer title and body stayed empty.
        // Prefer `content` when the title is authored inline and the body slot is empty (typical Save text flow).
        const requiredInputs = normalizeUpsertDocumentRequiredInputs(
            (targetNode.data as { required_inputs?: RequiredInput[] })?.required_inputs,
        );
        const rawName = requiredInputs.find(r => r.key === 'name')?.value;
        const rawContent = requiredInputs.find(r => r.key === 'content')?.value;
        const nameFilled =
            typeof rawName === 'string'
                ? rawName.trim().length > 0
                : rawName !== null &&
                  rawName !== undefined &&
                  String(rawName).trim().length > 0;
        const contentUnset =
            rawContent === null ||
            rawContent === undefined ||
            rawContent === '' ||
            (typeof rawContent === 'string' && rawContent.trim().length === 0);
        if (nameFilled && contentUnset) {
            targetHandle = 'content';
        } else if (!nameFilled && !contentUnset) {
            targetHandle = 'name';
        } else {
            targetHandle = 'content';
        }
    }
    if (
        targetNode &&
        targetNode.type === 'upsertDocument' &&
        typeof targetHandle === 'string' &&
        targetHandle.trim() !== '' &&
        UPSERT_DOCUMENT_CONTENT_TARGET_ALIASES.has(targetHandle.trim())
    ) {
        targetHandle = 'content';
    }
    if (targetNode && targetNode.type === 'parseDocumentBody' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'document';
    }
    if (targetNode && targetNode.type === 'htmlParseBasic' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'html';
    }
    if (targetNode && targetNode.type === 'writeObjectToDocumentBody' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'value';
    }
    if (targetNode && targetNode.type === 'appendValueToDocument' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'document';
    }
    if (targetNode && targetNode.type === 'validateAgainstStructure' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'value';
    }
    if (targetNode && targetNode.type === 'addToList') {
        if (targetHandle == null || targetHandle === '') {
            targetHandle = 'list';
        } else if (targetHandle === 'output') {
            // Legacy / mistaken persistence: "output" is a source handle on this node, not an input.
            targetHandle = 'value';
        }
    }
    if (targetNode && targetNode.type === 'addDays' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'input';
    }
    if (
        targetNode &&
        [
            'addInts',
            'subtractInts',
            'multiplyInts',
            'divideInts',
            'moduloInts',
            'minInts',
            'maxInts',
        ].includes(targetNode.type ?? '') &&
        (targetHandle == null || targetHandle === '')
    ) {
        targetHandle = 'input_a';
    }
    if (targetNode && targetNode.type === 'notControl' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'input';
    }
    if (targetNode && targetNode.type === 'betweenControl' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'low';
    }
    if (targetNode && targetNode.type === 'forLoopControl' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'input';
    }
    if (targetNode && targetNode.type === 'tryCatchControl' && (targetHandle == null || targetHandle === '')) {
        const srcN = nodes.find(n => n.id === e.source);
        const shEarly = sourceHandle ?? (e.source_handle as string | null | undefined) ?? '';
        const branchControlsTrig = [
            'basicConditional',
            'isControl',
            'isEmptyControl',
            'gtControl',
            'ltControl',
            'gteControl',
            'lteControl',
            'betweenControl',
        ].includes(srcN?.type ?? '');
        const fromBranchTf = branchControlsTrig && (shEarly === 'true' || shEarly === 'false');
        if (
            shEarly === 'signal_out' ||
            shEarly === 'try' ||
            shEarly === 'catch' ||
            fromBranchTf ||
            srcN?.type === 'tryCatchControl' ||
            srcN?.type === 'start'
        ) {
            targetHandle = 'trigger';
        } else {
            targetHandle = 'value';
        }
    }
    if (targetNode && targetNode.type === 'forLoopEndControl' && (targetHandle == null || targetHandle === '')) {
        const srcN = nodes.find(n => n.id === e.source);
        const fromFlSignal =
            srcN?.type === 'forLoopControl' && (e.source_handle === 'signal_out' || sourceHandle === 'signal_out');
        if (fromFlSignal) {
            targetHandle = 'trigger';
        } else {
            const ex = (targetNode.data as any)?.exports;
            targetHandle = Array.isArray(ex) && ex.length > 0 ? ex[0] : 'odds';
        }
    }
    if (targetNode && targetNode.type === 'basicConditional' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'condition';
    }
    if (targetNode && targetNode.type === 'isEmptyControl' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'value';
    }
    if (
        targetNode &&
        ['isControl', 'gtControl', 'ltControl', 'gteControl', 'lteControl', 'andControl', 'orControl', 'xorControl'].includes(
            targetNode.type ?? '',
        ) &&
        (targetHandle == null || targetHandle === '')
    ) {
        targetHandle = 'input_a';
    }
    if (targetNode && targetNode.type === 'simpleLLMCall' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'user_prompt';
    }
    if (targetNode && targetNode.type === 'multimodalLLMCall' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'user_prompt';
    }
    if (targetNode && targetNode.type === 'textToSpeech' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'text';
    }
    if (
        targetNode &&
        (targetNode.type === 'transcribeAudio' ||
            targetNode.type === 'audioFileInput' ||
            targetNode.type === 'transcribeFile') &&
        (targetHandle == null || targetHandle === '')
    ) {
        targetHandle = 'trigger';
    }
    if (targetNode && targetNode.type === 'gmailListMessages' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'after';
    }
    if (targetNode && targetNode.type === 'gmailPrimitive' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'gmail';
    }
    if (targetNode && targetNode.type === 'imagePrimitive' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'image';
    }
    if (targetNode && targetNode.type === 'calendarListEvents' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'time_min';
    }
    if (targetNode && targetNode.type === 'fetchUrl' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'url';
    }
    if (targetNode && targetNode.type === 'captureUrlSnapshot' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'url';
    }
    if (targetNode && targetNode.type === 'messageUtility' && (targetHandle == null || targetHandle === '')) {
        targetHandle = 'message';
    }
    const sourceNode = nodes.find(n => n.id === e.source);
    const nodesWithTrigger = ['stop', 'simpleLLMCall', 'multimodalLLMCall', 'textToSpeech', 'transcribeAudio', 'audioFileInput', 'transcribeFile', 'gmailListMessages', 'calendarListEvents', 'fetchUrl', 'captureUrlSnapshot', 'listToString', 'stringToList', 'prependText', 'stringTrunc', 'messageUtility', 'lenFromList', 'randomItemFromList', 'intToString', 'listItemByIndex', 'dictionaryValueByKey', 'dictionarySetValueByKey', 'readDocumentProperty', 'loadDocument', 'upsertDocument', 'parseDocumentBody', 'htmlParseBasic', 'writeObjectToDocumentBody', 'appendValueToDocument', 'validateAgainstStructure', 'addToList', 'addDays', 'addInts', 'subtractInts', 'multiplyInts', 'divideInts', 'moduloInts', 'minInts', 'maxInts', 'basicConditional', 'isControl', 'isEmptyControl', 'gtControl', 'ltControl', 'gteControl', 'lteControl', 'betweenControl', 'andControl', 'orControl', 'xorControl', 'notControl', 'tryCatchControl', 'forLoopControl', 'forLoopEndControl', 'stringPrimitive', 'decisionActionPrimitive', 'sandboxTickPrimitive', 'listPrimitive', 'dictionaryPrimitive', 'booleanPrimitive', 'intPrimitive', 'dateTimePrimitive', 'structurePrimitive', 'documentPrimitive', 'imagePrimitive', 'gmailPrimitive', 'sandboxBehaviorPrimitive', 'sandboxTickItems', 'sandboxAvailableCells', 'sandboxWorldGrid', 'sandboxTickPet', 'sandboxFilterItemsByType', 'sandboxNearestItemByType', 'sandboxClosestItem', 'sandboxDecisionIntent', 'sandboxDecisionMoveTo', 'sandboxStarterDecision', 'sandboxPetHunger', 'sandboxPetEnergy', 'sandboxPetCell', 'sandboxIsNearby8', 'sandboxFirstNearbyFood', 'sandboxFirstFoodWorldOrder', 'workflowRef'];
    if (sourceNode && targetNode && nodesWithTrigger.includes(targetNode.type ?? '') && (targetHandle == null || targetHandle === '') &&
        ((['basicConditional', 'isControl', 'isEmptyControl', 'gtControl', 'ltControl', 'gteControl', 'lteControl', 'betweenControl'].includes(sourceNode.type ?? '') && (sourceHandle === 'true' || sourceHandle === 'false')) ||
            (sourceNode.type === 'tryCatchControl' && (sourceHandle === 'try' || sourceHandle === 'catch')))) {
        targetHandle = 'trigger';
    }
    if (sourceNode && (sourceHandle == null || sourceHandle === '') &&
        (sourceNode.type === 'stringPrimitive' || sourceNode.type === 'decisionActionPrimitive' || sourceNode.type === 'sandboxTickPrimitive' || sourceNode.type === 'listPrimitive' || sourceNode.type === 'dictionaryPrimitive' || sourceNode.type === 'booleanPrimitive' || sourceNode.type === 'intPrimitive' || sourceNode.type === 'dateTimePrimitive' || sourceNode.type === 'structurePrimitive' || sourceNode.type === 'documentPrimitive' || sourceNode.type === 'imagePrimitive' || sourceNode.type === 'gmailPrimitive' || sourceNode.type === 'sandboxBehaviorPrimitive' || sourceNode.type === 'sandboxTickItems' || sourceNode.type === 'sandboxAvailableCells' || sourceNode.type === 'sandboxWorldGrid' || sourceNode.type === 'sandboxTickPet' || sourceNode.type === 'sandboxFilterItemsByType' || sourceNode.type === 'sandboxNearestItemByType' || sourceNode.type === 'sandboxClosestItem' || sourceNode.type === 'sandboxDecisionIntent' || sourceNode.type === 'sandboxDecisionMoveTo' || sourceNode.type === 'sandboxStarterDecision' || sourceNode.type === 'sandboxPetHunger' || sourceNode.type === 'sandboxPetEnergy' || sourceNode.type === 'sandboxPetCell' || sourceNode.type === 'sandboxIsNearby8' || sourceNode.type === 'sandboxFirstNearbyFood' || sourceNode.type === 'sandboxFirstFoodWorldOrder' || sourceNode.type === 'listToString' || sourceNode.type === 'stringToList' || sourceNode.type === 'prependText' || sourceNode.type === 'stringTrunc' || sourceNode.type === 'lenFromList' || sourceNode.type === 'randomItemFromList' || sourceNode.type === 'intToString' || sourceNode.type === 'listItemByIndex' || sourceNode.type === 'dictionaryValueByKey' || sourceNode.type === 'dictionarySetValueByKey' || sourceNode.type === 'readDocumentProperty' || sourceNode.type === 'loadDocument' || sourceNode.type === 'upsertDocument' || sourceNode.type === 'parseDocumentBody' || sourceNode.type === 'htmlParseBasic' || sourceNode.type === 'writeObjectToDocumentBody' || sourceNode.type === 'appendValueToDocument' || sourceNode.type === 'validateAgainstStructure' || sourceNode.type === 'addToList' || sourceNode.type === 'addDays' || sourceNode.type === 'addInts' || sourceNode.type === 'subtractInts' || sourceNode.type === 'multiplyInts' || sourceNode.type === 'divideInts' || sourceNode.type === 'moduloInts' || sourceNode.type === 'minInts' || sourceNode.type === 'maxInts' || sourceNode.type === 'andControl' || sourceNode.type === 'orControl' || sourceNode.type === 'xorControl' || sourceNode.type === 'notControl')) {
        sourceHandle = (sourceNode.type === 'prependText' || sourceNode.type === 'stringTrunc' ? 'output_string' : 'output');
    }
    if (sourceNode && sourceNode.type === 'forLoopControl' && (sourceHandle == null || sourceHandle === '')) {
        sourceHandle = 'item';
    }
    if (sourceNode && sourceNode.type === 'tryCatchControl' && (sourceHandle == null || sourceHandle === '')) {
        sourceHandle = 'output';
    }
    if (sourceNode && sourceNode.type === 'forLoopEndControl' && (sourceHandle == null || sourceHandle === '')) {
        sourceHandle = 'output';
    }
    if (sourceNode && sourceNode.type === 'start' && (sourceHandle == null || sourceHandle === '')) {
        const inputs = (sourceNode.data as any)?.required_inputs;
        if (Array.isArray(inputs) && inputs.length > 0) {
            sourceHandle = inputs[0]?.key ?? 'user_input';
        } else {
            sourceHandle = 'output';
        }
    }
    if (targetNode && targetNode.type === 'stop') {
        const outs = (targetNode.data as { required_outputs?: { key: string }[] })?.required_outputs ?? [
            { key: 'output', type: 'string' },
        ];
        const dataKey = outs[0]?.key ?? 'output';
        if (targetHandle !== 'trigger') {
            targetHandle = dataKey;
        }
    }
    return { 
        id: `e_${idx}`, 
        source: e.source, 
        target: e.target, 
        sourceHandle,
        targetHandle,
        style: { strokeWidth: 3, stroke: color },
        markerEnd: { type: MarkerType.ArrowClosed, color },
        zIndex: 1000
    };
}

export function flowNodeToApp(n: Node): AppGraphNode {
    const pos = { x: n.position.x, y: n.position.y };
    if (n.type === 'prependText') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'target_string' || r?.key === 'text_to_prepend')
            : [{ key: 'target_string', type: 'string' as const, value: null }, { key: 'text_to_prepend', type: 'string' as const, value: null }];
        const hasTarget = requiredInputs.some((r: { key?: string }) => r?.key === 'target_string');
        const hasPrepend = requiredInputs.some((r: { key?: string }) => r?.key === 'text_to_prepend');
        if (!hasTarget) requiredInputs.push({ key: 'target_string', type: 'string' as const, value: null });
        if (!hasPrepend) requiredInputs.push({ key: 'text_to_prepend', type: 'string' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'prepend_text',
            label: d?.label ?? 'Prepend Text',
            data: { required_inputs: requiredInputs, add_additional_line: d?.add_additional_line ?? false },
            position: pos,
        };
    }
    if (n.type === 'stringTrunc') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'target_string' || r?.key === 'start_index' || r?.key === 'end_index',
              )
            : [
                  { key: 'target_string', type: 'string' as const, value: null },
                  { key: 'start_index', type: 'int' as const, value: 0 },
                  { key: 'end_index', type: 'int' as const, value: -1 },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'target_string')) {
            requiredInputs.push({ key: 'target_string', type: 'string' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'start_index')) {
            requiredInputs.push({ key: 'start_index', type: 'int' as const, value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'end_index')) {
            requiredInputs.push({ key: 'end_index', type: 'int' as const, value: -1 });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'string_trunc',
            label: d?.label ?? 'String Trunc',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'messageUtility') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'message')
            : [{ key: 'message', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'message')) {
            requiredInputs.push({ key: 'message', type: 'string' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'message',
            label: d?.label ?? 'Message',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'basicConditional') {
        const d = n.data as any;
        let requiredInputs: RequiredInput[] = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'condition')
            : [{ key: 'condition', type: 'boolean' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'condition')) {
            requiredInputs.push({ key: 'condition', type: 'boolean' as const, value: null });
        }
        requiredInputs = requiredInputs.map(r => r.key === 'condition' ? { ...r, type: 'boolean' as const } : r);
        return {
            id: n.id,
            kind: 'control',
            control_type: 'basic_conditional',
            label: d?.label ?? 'Conditional',
            data: { required_inputs: requiredInputs, condition: d?.condition ?? null },
            position: pos,
        };
    }
    if (n.type === 'isControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
            : [{ key: 'input_a', type: 'string' as const, value: null }, { key: 'input_b', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'string' as const, value: null });
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'string' as const, value: null });
        return { id: n.id, kind: 'control', control_type: 'is', label: d?.label ?? 'Is?', data: { required_inputs: requiredInputs }, position: pos };
    }
    if (n.type === 'isEmptyControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
            : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'control',
            control_type: 'is_empty',
            label: d?.label ?? 'Is Empty?',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    const comparisonFlowToApp: { flowType: string; ctype: string; defaultLabel: string }[] = [
        { flowType: 'gtControl', ctype: 'gt', defaultLabel: 'Gt?' },
        { flowType: 'ltControl', ctype: 'lt', defaultLabel: 'Lt?' },
        { flowType: 'gteControl', ctype: 'gte', defaultLabel: 'Gte?' },
        { flowType: 'lteControl', ctype: 'lte', defaultLabel: 'Lte?' },
    ];
    for (const { flowType, ctype, defaultLabel } of comparisonFlowToApp) {
        if (n.type === flowType) {
            const d = n.data as any;
            const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
                : [{ key: 'input_a', type: 'string' as const, value: null }, { key: 'input_b', type: 'string' as const, value: null }];
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'string' as const, value: null });
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'string' as const, value: null });
            return { id: n.id, kind: 'control', control_type: ctype as 'gt' | 'lt' | 'gte' | 'lte', label: d?.label ?? defaultLabel, data: { required_inputs: requiredInputs }, position: pos };
        }
    }
    const logicalFlowToApp: { flowType: string; ctype: string; defaultLabel: string }[] = [
        { flowType: 'andControl', ctype: 'and', defaultLabel: 'And' },
        { flowType: 'orControl', ctype: 'or', defaultLabel: 'Or' },
        { flowType: 'xorControl', ctype: 'xor', defaultLabel: 'Xor' },
    ];
    for (const { flowType, ctype, defaultLabel } of logicalFlowToApp) {
        if (n.type === flowType) {
            const d = n.data as any;
            const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b')
                : [{ key: 'input_a', type: 'boolean' as const, value: null }, { key: 'input_b', type: 'boolean' as const, value: null }];
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) requiredInputs.push({ key: 'input_a', type: 'boolean' as const, value: null });
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) requiredInputs.push({ key: 'input_b', type: 'boolean' as const, value: null });
            return { id: n.id, kind: 'control', control_type: ctype as 'and' | 'or' | 'xor', label: d?.label ?? defaultLabel, data: { required_inputs: requiredInputs }, position: pos };
        }
    }
    if (n.type === 'notControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input')
            : [{ key: 'input', type: 'boolean' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'boolean' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'control',
            control_type: 'not',
            label: d?.label ?? 'Not',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'betweenControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) => r?.key === 'low' || r?.key === 'value' || r?.key === 'high',
              )
            : [
                  { key: 'low', type: 'int' as const, value: 0 },
                  { key: 'value', type: 'int' as const, value: 0 },
                  { key: 'high', type: 'int' as const, value: 0 },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'low')) {
            requiredInputs.push({ key: 'low', type: 'int', value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'int', value: 0 });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'high')) {
            requiredInputs.push({ key: 'high', type: 'int', value: 0 });
        }
        return {
            id: n.id,
            kind: 'control',
            control_type: 'between',
            label: d?.label ?? 'Between',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'tryCatchControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
            : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'control',
            control_type: 'try_catch',
            label: d?.label ?? 'Try / Catch',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'forLoopControl') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input')
            : [{ key: 'input', type: 'list' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'list' as const, value: null });
        }
        const dm =
            typeof d?.iteration_mode === 'string' && (d.iteration_mode === 'parallel' || d.iteration_mode === 'batched')
                ? d.iteration_mode
                : typeof d?.iteration_mode === 'string' && d.iteration_mode === 'sequential'
                  ? 'sequential'
                  : d?.parallel_iterations === true
                    ? 'parallel'
                    : 'sequential';
        const apiData: ForLoopControlNode['data'] = {
            required_inputs: requiredInputs,
        };
        if (dm === 'parallel' || dm === 'batched') {
            apiData.iteration_mode = dm;
        }
        if (dm === 'parallel') {
            apiData.parallel_iterations = true;
        }
        if (dm === 'batched' && typeof d?.batch_size === 'number' && Number.isFinite(d.batch_size)) {
            apiData.batch_size = Math.floor(d.batch_size);
        }
        if (d?.continue_on_error === true) apiData.continue_on_error = true;
        if (typeof d?.max_iterations === 'number' && Number.isFinite(d.max_iterations)) {
            apiData.max_iterations = Math.floor(d.max_iterations);
        }
        return {
            id: n.id,
            kind: 'control',
            control_type: 'for_loop',
            label: d?.label ?? 'For Loop',
            data: apiData,
            position: pos,
        };
    }
    if (n.type === 'forLoopEndControl') {
        const d = n.data as any;
        const exports =
            Array.isArray(d?.exports) && d.exports.length > 0 ? d.exports : ['odds', 'evens'];
        return {
            id: n.id,
            kind: 'control',
            control_type: 'for_loop_end',
            label: d?.label ?? 'For Loop End',
            data: {
                for_loop_id: d?.for_loop_id ?? '',
                exports,
            },
            position: pos,
        };
    }
    if (n.type === 'listToString') {
        const d = n.data as {
            label?: string;
            use_text_join?: boolean;
            add_line_breaks_between_items?: boolean;
        };
        const apiData: Record<string, unknown> = {};
        if (d?.use_text_join === true) {
            apiData.use_text_join = true;
            apiData.add_line_breaks_between_items = d.add_line_breaks_between_items !== false;
        } else if (d?.use_text_join === false) {
            apiData.use_text_join = false;
            if (d.add_line_breaks_between_items !== undefined) {
                apiData.add_line_breaks_between_items = Boolean(d.add_line_breaks_between_items);
            }
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'list_to_string',
            label: d?.label ?? 'List to String',
            data: apiData,
            position: pos,
        };
    }
    if (n.type === 'stringToList') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'string_to_list',
            label: d?.label ?? 'String to List',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'lenFromList') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'len_from_list',
            label: d?.label ?? 'Len from List',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'randomItemFromList') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'random_item_from_list',
            label: d?.label ?? 'Random item from list',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'intToString') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'int_to_string',
            label: d?.label ?? 'Int to String',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxTickItems') {
        const d = n.data as any;
        const item_type = d?.item_type === 'food' ? 'food' : 'all';
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_tick_items',
            label: d?.label ?? 'Sandbox get items',
            data: { item_type },
            position: pos,
        };
    }
    if (n.type === 'sandboxWorldGrid') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_world_grid',
            label: d?.label ?? 'Sandbox world grid',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxAvailableCells') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_available_cells',
            label: d?.label ?? 'Sandbox available cells',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxTickPet') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_tick_pet',
            label: d?.label ?? 'Sandbox tick pet',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxNearestItemByType') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) => r?.key === 'sandbox_tick' || r?.key === 'item_type',
              )
            : [
                  { key: 'sandbox_tick', type: 'dictionary' as const, value: null },
                  { key: 'item_type', type: 'string' as const, value: 'food' },
              ];
        const hasTick = requiredInputs.some((r: { key?: string }) => r?.key === 'sandbox_tick');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasTick) requiredInputs.push({ key: 'sandbox_tick', type: 'dictionary' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_nearest_item_by_type',
            label: d?.label ?? 'Sandbox nearest item by type',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxClosestItem') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) => r?.key === 'sandbox_tick' || r?.key === 'item_type',
              )
            : [
                  { key: 'sandbox_tick', type: 'dictionary' as const, value: null },
                  { key: 'item_type', type: 'string' as const, value: 'food' },
              ];
        const hasTick = requiredInputs.some((r: { key?: string }) => r?.key === 'sandbox_tick');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasTick) requiredInputs.push({ key: 'sandbox_tick', type: 'dictionary' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_closest_item',
            label: d?.label ?? 'Get Closest Item',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxDecisionMoveTo') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'target_item_id' || r?.key === 'target_cell' || r?.key === 'reason',
              )
            : [
                  { key: 'target_item_id', type: 'string' as const, value: null },
                  { key: 'target_cell', type: 'dictionary' as const, value: null },
                  { key: 'reason', type: 'string' as const, value: null },
              ];
        const keys = ['target_item_id', 'target_cell', 'reason'] as const;
        for (const k of keys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === k)) {
                if (k === 'target_item_id') {
                    requiredInputs.push({ key: 'target_item_id', type: 'string' as const, value: null });
                } else if (k === 'target_cell') {
                    requiredInputs.push({ key: 'target_cell', type: 'dictionary' as const, value: null });
                } else {
                    requiredInputs.push({ key: 'reason', type: 'string' as const, value: null });
                }
            }
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_decision_move_to',
            label: d?.label ?? 'Sandbox decision move_to',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxStarterDecision') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_starter_decision',
            label: d?.label ?? 'Starter sandbox decision',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxFilterItemsByType') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'items' || r?.key === 'item_type')
            : [{ key: 'items', type: 'list' as const, value: null }, { key: 'item_type', type: 'string' as const, value: 'food' }];
        const hasItems = requiredInputs.some((r: { key?: string }) => r?.key === 'items');
        const hasType = requiredInputs.some((r: { key?: string }) => r?.key === 'item_type');
        if (!hasItems) requiredInputs.push({ key: 'items', type: 'list' as const, value: null });
        if (!hasType) requiredInputs.push({ key: 'item_type', type: 'string' as const, value: 'food' });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_filter_items_by_type',
            label: d?.label ?? 'Sandbox filter items by type',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxDecisionIntent') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'action' ||
                      r?.key === 'target_item_id' ||
                      r?.key === 'target_cell' ||
                      r?.key === 'reason',
              )
            : [
                  { key: 'action', type: 'string' as const, value: 'wander' },
                  { key: 'target_item_id', type: 'string' as const, value: null },
                  { key: 'target_cell', type: 'dictionary' as const, value: null },
                  { key: 'reason', type: 'string' as const, value: null },
              ];
        const keys = ['action', 'target_item_id', 'target_cell', 'reason'] as const;
        for (const k of keys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === k)) {
                if (k === 'action') requiredInputs.push({ key: 'action', type: 'string' as const, value: 'wander' });
                else if (k === 'target_item_id') {
                    requiredInputs.push({ key: 'target_item_id', type: 'string' as const, value: null });
                } else if (k === 'target_cell') {
                    requiredInputs.push({ key: 'target_cell', type: 'dictionary' as const, value: null });
                } else {
                    requiredInputs.push({ key: 'reason', type: 'string' as const, value: null });
                }
            }
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_decision_intent',
            label: d?.label ?? 'Sandbox decision intent',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxPetHunger') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_pet_hunger',
            label: d?.label ?? 'Sandbox pet hunger',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxPetEnergy') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_pet_energy',
            label: d?.label ?? 'Sandbox pet energy',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxPetCell') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_pet_cell',
            label: d?.label ?? 'Sandbox pet cell',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxIsNearby8') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'cell_a' || r?.key === 'cell_b')
            : [
                  { key: 'cell_a', type: 'dictionary' as const, value: null },
                  { key: 'cell_b', type: 'dictionary' as const, value: null },
              ];
        const hasA = requiredInputs.some((r: { key?: string }) => r?.key === 'cell_a');
        const hasB = requiredInputs.some((r: { key?: string }) => r?.key === 'cell_b');
        if (!hasA) requiredInputs.push({ key: 'cell_a', type: 'dictionary' as const, value: null });
        if (!hasB) requiredInputs.push({ key: 'cell_b', type: 'dictionary' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_is_nearby8',
            label: d?.label ?? 'Sandbox is nearby8',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'sandboxFirstNearbyFood') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_first_nearby_food',
            label: d?.label ?? 'Sandbox first nearby food',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'sandboxFirstFoodWorldOrder') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'sandbox_first_food_world_order',
            label: d?.label ?? 'Sandbox first food (world order)',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'listItemByIndex') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'index' || r?.key === 'list')
            : [{ key: 'index', type: 'int' as const, value: 0 }, { key: 'list', type: 'list' as const, value: null }];
        const hasIndex = requiredInputs.some((r: { key?: string }) => r?.key === 'index');
        const hasList = requiredInputs.some((r: { key?: string }) => r?.key === 'list');
        if (!hasIndex) requiredInputs.push({ key: 'index', type: 'int' as const, value: 0 });
        if (!hasList) requiredInputs.push({ key: 'list', type: 'list' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'list_item_by_index',
            label: d?.label ?? 'List Item by Index',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'dictionaryValueByKey') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter(
                  (r: { key?: string }) =>
                      r?.key === 'key' || r?.key === 'dictionary' || r?.key === 'fallback',
              )
            : [
                  { key: 'key', type: 'string' as const, value: '' },
                  { key: 'dictionary', type: 'dictionary' as const, value: null },
                  { key: 'fallback', type: 'any' as const, value: null },
              ];
        const hasKey = requiredInputs.some((r: { key?: string }) => r?.key === 'key');
        const hasDict = requiredInputs.some((r: { key?: string }) => r?.key === 'dictionary');
        const hasFb = requiredInputs.some((r: { key?: string }) => r?.key === 'fallback');
        if (!hasKey) requiredInputs.push({ key: 'key', type: 'string' as const, value: '' });
        if (!hasDict) requiredInputs.push({ key: 'dictionary', type: 'dictionary' as const, value: null });
        if (!hasFb) requiredInputs.push({ key: 'fallback', type: 'any' as const, value: null });
        const ovt = d?.output_value_type;
        const output_value_type =
            ovt === 'string' || ovt === 'list' || ovt === 'dictionary' || ovt === 'boolean' || ovt === 'int' || ovt === 'datetime'
                ? ovt
                : 'list';
        const appData: Record<string, unknown> = {
            required_inputs: requiredInputs,
            output_value_type,
        };
        if (d != null && Object.prototype.hasOwnProperty.call(d, 'fallback_value')) {
            appData.fallback_value = d.fallback_value;
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'dictionary_value_by_key',
            label: d?.label ?? 'Dictionary Value by Key',
            data: appData,
            position: pos,
        };
    }
    if (n.type === 'dictionarySetValueByKey') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) =>
                r?.key === 'dictionary' || r?.key === 'key' || r?.key === 'value',
            )
            : [
                  { key: 'dictionary', type: 'dictionary' as const, value: null },
                  { key: 'key', type: 'string' as const, value: '' },
                  { key: 'value', type: 'any' as const, value: null },
              ];
        const hasDict = requiredInputs.some((r: { key?: string }) => r?.key === 'dictionary');
        const hasKey = requiredInputs.some((r: { key?: string }) => r?.key === 'key');
        const hasVal = requiredInputs.some((r: { key?: string }) => r?.key === 'value');
        if (!hasDict) requiredInputs.push({ key: 'dictionary', type: 'dictionary' as const, value: null });
        if (!hasKey) requiredInputs.push({ key: 'key', type: 'string' as const, value: '' });
        if (!hasVal) requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'dictionary_set_value_by_key',
            label: d?.label ?? 'Dictionary Set Value by Key',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'readDocumentProperty') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'target_property' || r?.key === 'document')
            : [
                  { key: 'target_property', type: 'string' as const, value: '' },
                  { key: 'document', type: 'document' as const, value: null },
              ];
        const hasTp = requiredInputs.some((r: { key?: string }) => r?.key === 'target_property');
        const hasDoc = requiredInputs.some((r: { key?: string }) => r?.key === 'document');
        if (!hasTp) requiredInputs.push({ key: 'target_property', type: 'string' as const, value: '' });
        if (!hasDoc) requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        const ovt = d?.output_value_type;
        const output_value_type =
            ovt === 'string' || ovt === 'list' || ovt === 'dictionary' || ovt === 'boolean' || ovt === 'int' ? ovt : 'string';
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'read_document_property',
            label: d?.label ?? 'Read Document Property',
            data: { required_inputs: requiredInputs, output_value_type },
            position: pos,
        };
    }
    if (n.type === 'loadDocument') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document_id' || r?.key === 'document_name')
            : [
                  { key: 'document_id', type: 'string' as const, value: null },
                  { key: 'document_name', type: 'string' as const, value: null },
              ];
        const hasId = requiredInputs.some((r: { key?: string }) => r?.key === 'document_id');
        const hasName = requiredInputs.some((r: { key?: string }) => r?.key === 'document_name');
        if (!hasId) requiredInputs.push({ key: 'document_id', type: 'string' as const, value: null });
        if (!hasName) requiredInputs.push({ key: 'document_name', type: 'string' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'load_document',
            label: d?.label ?? 'Load Document',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'upsertDocument') {
        const d = n.data as any;
        const requiredInputs = normalizeUpsertDocumentRequiredInputs(d?.required_inputs);
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'upsert_document',
            label: d?.label ?? 'Upsert Document',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'parseDocumentBody') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document')
            : [{ key: 'document', type: 'document' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'document')) {
            requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'parse_document_body',
            label: d?.label ?? 'Parse Document Body',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'htmlParseBasic') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'html')
            : [{ key: 'html', type: 'string' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'html')) {
            requiredInputs.push({ key: 'html', type: 'string' as const, value: null });
        }
        const dataOut: Record<string, unknown> = { required_inputs: requiredInputs };
        if (d && Object.prototype.hasOwnProperty.call(d, 'granularity')) {
            dataOut.granularity = d.granularity;
        }
        if (d && Object.prototype.hasOwnProperty.call(d, 'content_root_css')) {
            dataOut.content_root_css = d.content_root_css;
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'html_parse_basic',
            label: d?.label ?? 'HTML Parse (basic)',
            data: dataOut,
            position: pos,
        };
    }
    if (n.type === 'writeObjectToDocumentBody') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value')
            : [{ key: 'value', type: 'any' as const, value: null }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'write_object_to_document_body',
            label: d?.label ?? 'Write Object to Document Body',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'appendValueToDocument') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'document' || r?.key === 'value')
            : [
                  { key: 'document', type: 'document' as const, value: null },
                  { key: 'value', type: 'any' as const, value: null },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'document')) {
            requiredInputs.push({ key: 'document', type: 'document' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'append_value_to_document',
            label: d?.label ?? 'Append Value to Document',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'validateAgainstStructure') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'value' || r?.key === 'structure')
            : [
                  { key: 'value', type: 'any' as const, value: null },
                  { key: 'structure', type: 'structure' as const, value: null },
              ];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'value')) {
            requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'structure')) {
            requiredInputs.push({ key: 'structure', type: 'structure' as const, value: null });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'validate_against_structure',
            label: d?.label ?? 'Validate Against Structure',
            data: {
                required_inputs: requiredInputs,
                structure_id: d?.structure_id ?? null,
            },
            position: pos,
        };
    }
    if (n.type === 'addToList') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'list' || r?.key === 'value')
            : [{ key: 'list', type: 'list' as const, value: null }, { key: 'value', type: 'any' as const, value: null }];
        const hasList = requiredInputs.some((r: { key?: string }) => r?.key === 'list');
        const hasVal = requiredInputs.some((r: { key?: string }) => r?.key === 'value');
        if (!hasList) requiredInputs.push({ key: 'list', type: 'list' as const, value: null });
        if (!hasVal) requiredInputs.push({ key: 'value', type: 'any' as const, value: null });
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'add_to_list',
            label: d?.label ?? 'Add to List',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    if (n.type === 'addDays') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'input' || r?.key === 'days')
            : [{ key: 'input', type: 'datetime' as const, value: null }, { key: 'days', type: 'int' as const, value: 0 }];
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input')) {
            requiredInputs.push({ key: 'input', type: 'datetime' as const, value: null });
        }
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'days')) {
            requiredInputs.push({ key: 'days', type: 'int' as const, value: 0 });
        }
        return {
            id: n.id,
            kind: 'utility',
            utility_type: 'add_days',
            label: d?.label ?? 'Add days',
            data: { required_inputs: requiredInputs },
            position: pos,
        };
    }
    const binaryIntFlowToApp: { flowType: string; utype: BinaryIntUtilityType; defaultLabel: string }[] = [
        { flowType: 'addInts', utype: 'add_ints', defaultLabel: 'Add' },
        { flowType: 'subtractInts', utype: 'subtract_ints', defaultLabel: 'Subtract' },
        { flowType: 'multiplyInts', utype: 'multiply_ints', defaultLabel: 'Multiply' },
        { flowType: 'divideInts', utype: 'divide_ints', defaultLabel: 'Divide' },
        { flowType: 'moduloInts', utype: 'modulo_ints', defaultLabel: 'Modulo' },
        { flowType: 'minInts', utype: 'min_ints', defaultLabel: 'Min' },
        { flowType: 'maxInts', utype: 'max_ints', defaultLabel: 'Max' },
    ];
    for (const { flowType, utype, defaultLabel } of binaryIntFlowToApp) {
        if (n.type === flowType) {
            const d = n.data as any;
            const requiredInputs =
                Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
                    ? d.required_inputs.filter(
                          (r: { key?: string }) => r?.key === 'input_a' || r?.key === 'input_b',
                      )
                    : defaultBinaryIntRequiredInputs();
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_a')) {
                requiredInputs.push({ key: 'input_a', type: 'int', value: 0 });
            }
            if (!requiredInputs.some((r: { key?: string }) => r?.key === 'input_b')) {
                requiredInputs.push({ key: 'input_b', type: 'int', value: 0 });
            }
            return {
                id: n.id,
                kind: 'utility',
                utility_type: utype,
                label: d?.label ?? defaultLabel,
                data: { required_inputs: requiredInputs },
                position: pos,
            };
        }
    }
    if (n.type === 'simpleLLMCall') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.some((r: { key?: string }) => r?.key === 'user_prompt')
            ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'user_prompt')
            : [{ key: 'user_prompt', type: 'string' as const, value: null }];
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'simple_llm_call',
            label: d?.label ?? 'LLM Call',
            data: {
                required_inputs: requiredInputs,
                persona_id: d?.persona_id ?? null,
                structure_id: d?.structure_id ?? null,
                additional_system_prompt_context: d?.additional_system_prompt_context ?? null,
            },
            position: pos,
        };
    }
    if (n.type === 'multimodalLLMCall') {
        const d = n.data as any;
        const mmKeys = ['user_prompt', 'images', 'additional_context', 'structure'] as const;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        if (
            !requiredInputs.some((r: { key?: string }) => r?.key === 'user_prompt') ||
            !requiredInputs.some((r: { key?: string }) => r?.key === 'images')
        ) {
            requiredInputs = [
                { key: 'user_prompt', type: 'string' as const, value: null },
                { key: 'images', type: 'list' as const, value: null },
            ];
        }
        requiredInputs = requiredInputs.filter((r: { key?: string }) => mmKeys.includes(r?.key as (typeof mmKeys)[number]));
        const data: Record<string, unknown> = {
            required_inputs: requiredInputs,
            persona_id: d?.persona_id ?? null,
            structure_id: d?.structure_id ?? null,
            additional_system_prompt_context: d?.additional_system_prompt_context ?? null,
        };
        if (typeof d?.model === 'string' && d.model.trim() !== '') {
            data.model = d.model.trim();
        }
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'multimodal_llm',
            label: d?.label ?? 'Multimodal LLM',
            data: data as MultimodalLLMCallSkillNode['data'],
            position: pos,
        };
    }
    if (n.type === 'textToSpeech') {
        const d = n.data as any;
        const requiredInputs =
            Array.isArray(d?.required_inputs) && d.required_inputs.some((r: { key?: string }) => r?.key === 'text')
                ? d.required_inputs.filter((r: { key?: string }) => r?.key === 'text')
                : [{ key: 'text', type: 'string' as const, value: null }];
        const rawOpts = d?.tts_options;
        const tts_options =
            rawOpts != null && typeof rawOpts === 'object' && !Array.isArray(rawOpts) ? { ...rawOpts } : {};
        const tw = d?.tts_playback_when;
        const hasTw = tw === 'inline' || tw === 'manual' || tw === 'after_workflow';
        const ap = d?.auto_play_tts_on_node_end;
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'text_to_speech',
            label: d?.label ?? 'Text-to-Speech',
            data: {
                required_inputs: requiredInputs,
                tts_model_id: d?.tts_model_id ?? null,
                voice_sample_id: d?.voice_sample_id ?? null,
                engine: d?.engine ?? null,
                tts_options,
                ...(hasTw ? { tts_playback_when: tw } : {}),
                ...(!hasTw && (ap === true || ap === false) ? { auto_play_tts_on_node_end: ap } : {}),
            },
            position: pos,
        };
    }
    if (n.type === 'transcribeAudio') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const data: {
            language: string | null;
            task: 'transcribe' | 'translate';
            model?: string;
        } = {
            language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
            task: task === 'translate' ? 'translate' : 'transcribe',
        };
        if (typeof d?.model === 'string' && d.model.trim() !== '') {
            data.model = d.model.trim();
        }
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'transcribe_audio',
            label: typeof d?.label === 'string' && d.label ? d.label : 'Voice input',
            data,
            position: pos,
        };
    }
    if (n.type === 'audioFileInput') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const data: {
            audio_artifact_id: string | null;
            language: string | null;
            task: 'transcribe' | 'translate';
            model?: string;
        } = {
            audio_artifact_id:
                typeof d?.audio_artifact_id === 'string' && d.audio_artifact_id.trim() !== ''
                    ? d.audio_artifact_id.trim()
                    : null,
            language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
            task: task === 'translate' ? 'translate' : 'transcribe',
        };
        if (typeof d?.model === 'string' && d.model.trim() !== '') {
            data.model = d.model.trim();
        }
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'audio_file_input',
            label: typeof d?.label === 'string' && d.label ? d.label : 'Audio File Input',
            data,
            position: pos,
        };
    }
    if (n.type === 'transcribeFile') {
        const d = n.data as Record<string, unknown>;
        const task = d?.task;
        const provider =
            typeof d?.provider === 'string' && d.provider.trim() !== '' ? d.provider.trim() : 'local_whisper';
        const data: {
            provider: string;
            audio_artifact_id: string | null;
            language: string | null;
            task: 'transcribe' | 'translate';
            prompt: string | null;
            diarization_enabled: boolean;
            include_word_timestamps: boolean;
            provider_model_id: string | null;
        } = {
            provider,
            audio_artifact_id:
                typeof d?.audio_artifact_id === 'string' && d.audio_artifact_id.trim() !== ''
                    ? d.audio_artifact_id.trim()
                    : null,
            language: typeof d?.language === 'string' && d.language.trim() !== '' ? d.language.trim() : null,
            task: task === 'translate' ? 'translate' : 'transcribe',
            prompt: typeof d?.prompt === 'string' && d.prompt.trim() !== '' ? d.prompt.trim() : null,
            diarization_enabled: Boolean(d?.diarization_enabled),
            include_word_timestamps: Boolean(d?.include_word_timestamps),
            provider_model_id:
                typeof d?.provider_model_id === 'string' && d.provider_model_id.trim() !== ''
                    ? d.provider_model_id.trim()
                    : null,
        };
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'transcribe_file',
            label: typeof d?.label === 'string' && d.label ? d.label : 'Transcribe File',
            data,
            position: pos,
        };
    }
    if (n.type === 'gmailListMessages') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        const gmailKeys = ['after', 'before', 'unread_only', 'query', 'max_results'] as const;
        requiredInputs = requiredInputs.filter((r: { key?: string }) =>
            gmailKeys.includes(r?.key as (typeof gmailKeys)[number]),
        );
        for (const key of gmailKeys) {
            if (!requiredInputs.some((r: { key?: string }) => r?.key === key)) {
                if (key === 'max_results') {
                    requiredInputs.push({ key: 'max_results', type: 'int' as const, value: d?.max_results ?? 10 });
                } else if (key === 'unread_only') {
                    requiredInputs.push({
                        key: 'unread_only',
                        type: 'boolean' as const,
                        value: d?.unread_only ?? false,
                    });
                } else {
                    requiredInputs.push({
                        key,
                        type: 'string' as const,
                        value:
                            key === 'after'
                                ? (d?.after ?? null)
                                : key === 'before'
                                  ? (d?.before ?? null)
                                  : key === 'query'
                                    ? (d?.query ?? null)
                                    : null,
                    });
                }
            }
        }
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'gmail_list_messages',
            label: d?.label ?? 'Gmail List Messages',
            data: {
                required_inputs: requiredInputs,
                google_connection_id: d?.google_connection_id ?? null,
                max_results: d?.max_results ?? 10,
                unread_only: d?.unread_only ?? false,
                after: d?.after ?? null,
                before: d?.before ?? null,
                query:
                    (requiredInputs.find((r: { key?: string }) => r?.key === 'query')?.value as string | null | undefined) ??
                    d?.query ??
                    null,
            },
            position: pos,
        };
    }
    if (n.type === 'calendarListEvents') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        requiredInputs = requiredInputs.filter(
            (r: { key?: string }) => r?.key === 'time_min' || r?.key === 'time_max',
        );
        const hasA = requiredInputs.some((r: { key?: string }) => r?.key === 'time_min');
        const hasB = requiredInputs.some((r: { key?: string }) => r?.key === 'time_max');
        if (!hasA) requiredInputs.push({ key: 'time_min', type: 'string' as const, value: null });
        if (!hasB) requiredInputs.push({ key: 'time_max', type: 'string' as const, value: null });
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'calendar_list_events',
            label: d?.label ?? 'Calendar List Events',
            data: {
                required_inputs: requiredInputs,
                google_connection_id: d?.google_connection_id ?? null,
                calendar_id: d?.calendar_id ?? 'primary',
            },
            position: pos,
        };
    }
    if (n.type === 'fetchUrl') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        requiredInputs = requiredInputs.filter((r: { key?: string }) => r?.key === 'url');
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'url')) {
            requiredInputs.push({ key: 'url', type: 'string' as const, value: null });
        }
        const pol = d?.cache_policy;
        const cachePolicy =
            pol === 'refresh' || pol === 'bypass' || pol === 'default' ? pol : 'default';
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'fetch_url',
            label: d?.label ?? 'Fetch URL',
            data: {
                required_inputs: requiredInputs,
                url: d?.url ?? '',
                method: d?.method ?? 'GET',
                headers: d?.headers && typeof d.headers === 'object' && !Array.isArray(d.headers) ? d.headers : {},
                timeout_ms: d?.timeout_ms ?? null,
                cache_policy: cachePolicy,
            },
            position: pos,
        };
    }
    if (n.type === 'captureUrlSnapshot') {
        const d = n.data as any;
        let requiredInputs = Array.isArray(d?.required_inputs) ? [...d.required_inputs] : [];
        requiredInputs = requiredInputs.filter((r: { key?: string }) => r?.key === 'url');
        if (!requiredInputs.some((r: { key?: string }) => r?.key === 'url')) {
            requiredInputs.push({ key: 'url', type: 'string' as const, value: null });
        }
        const pol = d?.cache_policy;
        const cachePolicy =
            pol === 'refresh' || pol === 'bypass' || pol === 'default' ? pol : 'default';
        const wu = d?.wait_until;
        const waitUntil =
            wu === 'domcontentloaded' || wu === 'networkidle' || wu === 'load' ? wu : 'load';
        const fp = d?.full_page;
        const fullPage = fp === undefined || fp === null ? true : Boolean(fp);
        const vw = d?.viewport_width;
        const vh = d?.viewport_height;
        const toPosInt = (v: unknown): number | null => {
            if (v === '' || v === undefined || v === null) return null;
            const n = Number(v);
            return Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
        };
        return {
            id: n.id,
            kind: 'skill',
            skill_type: 'capture_url_snapshot',
            label: d?.label ?? 'URL snapshot',
            data: {
                required_inputs: requiredInputs,
                url: d?.url ?? '',
                full_page: fullPage,
                viewport_width: toPosInt(vw),
                viewport_height: toPosInt(vh),
                wait_until: waitUntil,
                timeout_ms: d?.timeout_ms ?? null,
                cache_policy: cachePolicy,
            },
            position: pos,
        };
    }
    if (n.type === 'structurePrimitive') {
        const d = n.data as any;
        return { id: n.id, kind: 'primitive', primitive_type: 'structure', label: d?.label ?? 'Structure', data: { structure_id: d?.structure_id ?? '' }, position: pos };
    }
    if (n.type === 'documentPrimitive') {
        const d = n.data as any;
        return { id: n.id, kind: 'primitive', primitive_type: 'document', label: d?.label ?? 'Document', data: { document_id: d?.document_id ?? '' }, position: pos };
    }
    if (n.type === 'imagePrimitive') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs
            : [{ key: 'image', type: 'dictionary' as const, value: null }];
        const data: Record<string, unknown> = {
            required_inputs: requiredInputs,
        };
        if (d?.artifact_id != null && String(d.artifact_id).trim() !== '') {
            data.artifact_id = d.artifact_id;
        }
        return {
            id: n.id,
            kind: 'primitive',
            primitive_type: 'image',
            label: d?.label ?? 'Image',
            data,
            position: pos,
        };
    }
    if (n.type === 'gmailPrimitive') {
        const d = n.data as any;
        const requiredInputs = Array.isArray(d?.required_inputs) && d.required_inputs.length > 0
            ? d.required_inputs
            : [{ key: 'gmail', type: 'gmail' as const, value: null }];
        return {
            id: n.id,
            kind: 'primitive',
            primitive_type: 'gmail',
            label: d?.label ?? 'Gmail',
            data: {
                message: d?.message && typeof d.message === 'object' && !Array.isArray(d.message) ? d.message : {},
                required_inputs: requiredInputs,
            },
            position: pos,
        };
    }
    if (n.type === 'sandboxBehaviorPrimitive') {
        return { id: n.id, kind: 'primitive', primitive_type: 'sandbox_behavior', label: (n.data as any).label ?? 'Sandbox behavior', data: {}, position: pos };
    }
    if (n.type === 'decisionActionPrimitive') {
        const d = n.data as any;
        const raw = d?.action;
        const action =
            typeof raw === 'string' && isSandboxDecisionAction(raw) ? raw : DEFAULT_SANDBOX_DECISION_ACTION;
        return {
            id: n.id,
            kind: 'primitive',
            primitive_type: 'decision_action',
            label: d?.label ?? 'Decision action',
            data: { action },
            position: pos,
        };
    }
    if (n.type === 'sandboxTickPrimitive') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'primitive',
            primitive_type: 'sandbox_tick',
            label: d?.label ?? 'Sandbox tick',
            data: {},
            position: pos,
        };
    }
    if (n.type === 'stringPrimitive') return { id: n.id, kind: 'primitive', primitive_type: 'string', label: (n.data as any).label, data: { text: (n.data as any).text ?? '' }, position: pos };
    if (n.type === 'listPrimitive') return { id: n.id, kind: 'primitive', primitive_type: 'list', label: (n.data as any).label, data: (n.data as any).data ?? [], position: pos };
    if (n.type === 'dictionaryPrimitive') return { id: n.id, kind: 'primitive', primitive_type: 'dictionary', label: (n.data as any).label, data: (n.data as any).data ?? {}, position: pos };
    if (n.type === 'booleanPrimitive') return { id: n.id, kind: 'primitive', primitive_type: 'boolean', label: (n.data as any).label, data: { value: (n.data as any).value ?? false }, position: pos };
    if (n.type === 'intPrimitive') return { id: n.id, kind: 'primitive', primitive_type: 'int', label: (n.data as any).label, data: { value: (n.data as any).value ?? 0 }, position: pos };
    if (n.type === 'dateTimePrimitive') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'primitive',
            primitive_type: 'datetime',
            label: d?.label ?? 'DateTime',
            data: { iso: d?.iso ?? null, use_now: coerceDatetimePrimitiveUseNow(d as Record<string, unknown>) },
            position: pos,
        };
    }
    if (n.type === 'start') {
        const d = n.data as any;
        const dataOut: { required_inputs?: RequiredInput[]; text?: string } = {};
        if (d?.required_inputs !== undefined) {
            dataOut.required_inputs = d.required_inputs;
        } else {
            dataOut.text = d?.text ?? '';
        }
        return {
            id: n.id,
            kind: 'start',
            label: d?.label ?? 'Start',
            data: dataOut,
            position: pos,
        };
    }
    if (n.type === 'workflowRef') {
        const d = n.data as any;
        return {
            id: n.id,
            kind: 'workflow',
            label: d?.label ?? 'Workflow',
            data: { workflow_id: d?.workflow_id ?? '' },
            position: pos,
        };
    }
    if (n.type === 'annotationNote') {
        const d = n.data as {
            label?: string;
            text?: string;
            color?: string | null;
            label_font_size_px?: number;
            content_font_size_px?: number;
            label_align?: string;
            content_align?: string;
            width?: number;
            height?: number;
            z_index?: number;
        };
        const cfs =
            typeof d?.content_font_size_px === 'number' && Number.isFinite(d.content_font_size_px)
                ? d.content_font_size_px
                : 12;
        const lfs =
            typeof d?.label_font_size_px === 'number' && Number.isFinite(d.label_font_size_px)
                ? d.label_font_size_px
                : ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX;
        const style = (n.style ?? {}) as { width?: unknown; height?: unknown };
        const w = parseStyleDimension(
            style.width,
            typeof d?.width === 'number' && Number.isFinite(d.width) ? d.width : ANNOTATION_NOTE_DEFAULT_WIDTH,
        );
        const h = parseStyleDimension(
            style.height,
            typeof d?.height === 'number' && Number.isFinite(d.height) ? d.height : ANNOTATION_NOTE_DEFAULT_HEIGHT,
        );
        const labelAlign = normalizeAnnotationTextAlign(d?.label_align);
        const contentAlign = normalizeAnnotationTextAlign(d?.content_align);
        const ziNote = clampAnnotationNoteZIndex(
            typeof n.zIndex === 'number' && Number.isFinite(n.zIndex) ? n.zIndex : d?.z_index,
        );
        return {
            id: n.id,
            kind: 'annotation',
            annotation_type: 'note',
            label: d?.label ?? 'Note',
            data: {
                text: typeof d?.text === 'string' ? d.text : '',
                color: d?.color ?? undefined,
                label_font_size_px: lfs,
                content_font_size_px: cfs,
                label_align: labelAlign,
                content_align: contentAlign,
                width: w,
                height: h,
                z_index: ziNote,
            },
            position: pos,
        };
    }
    if (n.type === 'annotationRegion') {
        const d = n.data as {
            label?: string;
            color?: string | null;
            width?: number;
            height?: number;
            label_font_size_px?: number;
            label_align?: string;
            z_index?: number;
        };
        const style = (n.style ?? {}) as { width?: unknown; height?: unknown };
        const w = parseStyleDimension(style.width, typeof d?.width === 'number' ? d.width : 400);
        const h = parseStyleDimension(style.height, typeof d?.height === 'number' ? d.height : 280);
        const lf =
            typeof d?.label_font_size_px === 'number' && Number.isFinite(d.label_font_size_px)
                ? d.label_font_size_px
                : 11;
        const zi = clampAnnotationRegionZIndex(
            typeof n.zIndex === 'number' && Number.isFinite(n.zIndex) ? n.zIndex : d?.z_index,
        );
        const labelAlign = normalizeAnnotationTextAlign(d?.label_align);
        return {
            id: n.id,
            kind: 'annotation',
            annotation_type: 'region',
            label: d?.label ?? 'Region',
            data: {
                color: d?.color ?? undefined,
                width: w,
                height: h,
                label_font_size_px: lf,
                label_align: labelAlign,
                z_index: zi,
            },
            position: pos,
        };
    }
    if (n.type === 'stop') {
        const d = n.data as any;
        const raw = d?.required_outputs ?? [{ key: 'output', type: 'string' as const }];
        const required_outputs =
            Array.isArray(raw) && raw.length > 0 ? raw : [{ key: 'output', type: 'string' as const }];
        const sp = d?.stop_priority;
        const stopPriority =
            typeof sp === 'number'
                ? sp
                : sp != null && String(sp).trim() !== '' && !Number.isNaN(Number(sp))
                  ? Number(sp)
                  : undefined;
        return {
            id: n.id,
            kind: 'stop',
            label: d?.label ?? 'Stop',
            data: {
                required_outputs,
                ...(stopPriority !== undefined ? { stop_priority: stopPriority } : {}),
            },
            position: pos,
        };
    }
    if (n.type === 'invalidStep') {
        const d = n.data as { rawNode?: AppGraphNode };
        if (d?.rawNode) {
            return d.rawNode;
        }
    }
    return { id: n.id, kind: 'stop', label: (n.data as any).label, position: pos };
}

export function flowEdgeToApp(e: Edge): AppGraphEdge {
    return {
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle ?? null,
        target_handle: e.targetHandle ?? null,
    };
}

export function resolveWorkflowRefLabels(nodes: Node[], workflows: WorkflowDefinitionListItemHydrated[]): Node[] {
    return nodes.map(n => {
        if (n.type === 'workflowRef') {
            const d = n.data as any;
            const refWf = workflows.find(w => w.id === d?.workflow_id);
            return { ...n, data: { ...d, label: d?.label ?? refWf?.name ?? 'Workflow' } };
        }
        return n;
    });
}