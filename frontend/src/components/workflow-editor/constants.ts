import { resolveWorkflowPaletteColor } from '../../domain/paletteDefaults';

export const HANDLE_INSET = 14;
export const HANDLE_SIZE = 16;
const LABEL_GAP = 4;
export const INPUT_LABEL_OFFSET = HANDLE_INSET + HANDLE_SIZE + LABEL_GAP;
export const OUTPUT_LABEL_OFFSET = HANDLE_INSET + HANDLE_SIZE + LABEL_GAP;
export const STRIP_TO_CONTENT_GAP = 24;
export const LABEL_STRIP_WIDTH = 72;
export const STOP_LABEL_STRIP_WIDTH = 100;

/** Centralized node dimensions. minHeight is derived from slot count when not overridden. */
export const NODE_MIN_HEIGHT = { single: 64, double: 72, triple: 80, quad: 96, quintuple: 112 } as const;
export const NODE_MIN_WIDTH = { small: 140, medium: 160, large: 200 } as const;
export const NODE_STRIP_PADDING_Y = 12;
/** Extra bottom inset on the output handle strip so the lowest port stays clear of rounded corners / hit targets. */
export const NODE_OUTPUT_STRIP_EXTRA_BOTTOM_PX = 4;
/** Top padding band when session output override is active so the “Overridden” chip does not cover `signal_out` / output ports. Paired min-height bump in `StyledNodeBase`. */
export const NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX = 22;

export function getNodeMinHeight(inputCount: number, outputCount: number): number {
    const slots = Math.max(inputCount, outputCount, 1);
    if (slots <= 1) return NODE_MIN_HEIGHT.single;
    if (slots <= 2) return NODE_MIN_HEIGHT.double;
    if (slots <= 3) return NODE_MIN_HEIGHT.triple;
    if (slots <= 4) return NODE_MIN_HEIGHT.quad;
    return NODE_MIN_HEIGHT.quintuple;
}

export const SIMPLE_LLM_HANDLES = [
    { id: 'additional_context', label: 'Add context' },
    { id: 'user_prompt', label: 'User Prompt' },
    { id: 'structure', label: 'Structure' },
] as const;

export const MULTIMODAL_LLM_HANDLES = [
    { id: 'additional_context', label: 'Add context' },
    { id: 'user_prompt', label: 'User Prompt' },
    { id: 'structure', label: 'Structure' },
    { id: 'images', label: 'Images' },
] as const;

export const PREPEND_TEXT_HANDLES = [
    { id: 'target_string', label: 'Target' },
    { id: 'text_to_prepend', label: 'Prepend' },
] as const;

export const STRING_TRUNC_HANDLES = [
    { id: 'target_string', label: 'Target', type: 'string' as const },
    { id: 'start_index', label: 'Start', type: 'int' as const },
    { id: 'end_index', label: 'End', type: 'int' as const },
] as const;

export const TEXT_TO_SPEECH_HANDLES = [{ id: 'text', label: 'Text' }] as const;

export const GMAIL_LIST_MESSAGES_HANDLES = [
    { id: 'after', label: 'After' },
    { id: 'before', label: 'Before' },
    { id: 'unread_only', label: 'Unread' },
    { id: 'query', label: 'Query' },
    { id: 'max_results', label: 'Max' },
] as const;

export const CALENDAR_LIST_EVENTS_HANDLES = [
    { id: 'time_min', label: 'time_min' },
    { id: 'time_max', label: 'time_max' },
] as const;

export const FETCH_URL_HANDLES = [{ id: 'url', label: 'url' }] as const;
export const CAPTURE_URL_SNAPSHOT_HANDLES = [{ id: 'url', label: 'url' }] as const;

export const getHandleColor = (paletteColors: Record<string, string> | undefined, type: string): string =>
    resolveWorkflowPaletteColor(paletteColors, type);
