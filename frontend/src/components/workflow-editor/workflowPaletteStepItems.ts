/**
 * Data-only definitions for the workflow editor step palette (Primitives, Skills, Utilities, Sandbox Utilities, Controls, Annotation).
 * Icons are rendered in WorkflowPaletteStepSections.
 */

import {
    ANNOTATION_NOTE_DEFAULT_HEIGHT,
    ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
    ANNOTATION_NOTE_DEFAULT_WIDTH,
    ANNOTATION_NOTE_DEFAULT_Z_INDEX,
    ANNOTATION_REGION_DEFAULT_Z_INDEX,
} from './graphConverters';

/** Start/Stop and other flow endpoints (placed on canvas like primitives). */
export const WORKFLOW_PALETTE_FLOW_ITEMS: readonly WorkflowPaletteStepItem[] = [
    { type: 'stop', label: 'Stop', extra: { label: 'Stop' }, paletteType: 'stop' },
];

export interface WorkflowPaletteStepItem {
    /** React Flow node `type` string */
    type: string;
    label: string;
    extra: Record<string, unknown>;
    /** Key passed to `getHandleColor` / palette resolution */
    paletteType: string;
}

export const WORKFLOW_PALETTE_PRIMITIVE_ITEMS: readonly WorkflowPaletteStepItem[] = [
    { type: 'stringPrimitive', label: 'String', extra: {}, paletteType: 'string' },
    { type: 'listPrimitive', label: 'List', extra: {}, paletteType: 'list' },
    { type: 'dictionaryPrimitive', label: 'Dictionary', extra: {}, paletteType: 'dictionary' },
    { type: 'booleanPrimitive', label: 'Boolean', extra: {}, paletteType: 'boolean' },
    { type: 'intPrimitive', label: 'Int', extra: {}, paletteType: 'int' },
    { type: 'dateTimePrimitive', label: 'DateTime', extra: {}, paletteType: 'datetime' },
    { type: 'structurePrimitive', label: 'Structure', extra: {}, paletteType: 'structure' },
    { type: 'documentPrimitive', label: 'Document', extra: {}, paletteType: 'document' },
    { type: 'imagePrimitive', label: 'Image', extra: {}, paletteType: 'image' },
    { type: 'gmailPrimitive', label: 'Gmail', extra: { label: 'Gmail' }, paletteType: 'gmail' },
];

export const WORKFLOW_PALETTE_SKILL_ITEMS: readonly WorkflowPaletteStepItem[] = [
    { type: 'simpleLLMCall', label: 'Simple LLM Call', extra: { label: 'LLM Call' }, paletteType: 'simple_llm_call' },
    {
        type: 'multimodalLLMCall',
        label: 'Multimodal LLM',
        extra: { label: 'Multimodal LLM' },
        paletteType: 'multimodal_llm',
    },
    { type: 'textToSpeech', label: 'Text-to-Speech', extra: { label: 'TTS' }, paletteType: 'text_to_speech' },
    { type: 'transcribeAudio', label: 'Voice input', extra: { label: 'Voice input' }, paletteType: 'transcribe_audio' },
    {
        type: 'audioFileInput',
        label: 'Audio File Input',
        extra: { label: 'Audio File Input' },
        paletteType: 'audio_file_input',
    },
    {
        type: 'transcribeFile',
        label: 'Transcribe File',
        extra: {
            label: 'Transcribe File',
            provider: 'local_whisper',
            diarization_enabled: false,
            include_word_timestamps: false,
        },
        paletteType: 'transcribe_file',
    },
    { type: 'gmailListMessages', label: 'Gmail List Messages', extra: { label: 'Gmail List' }, paletteType: 'gmail_list_messages' },
    { type: 'calendarListEvents', label: 'Calendar List Events', extra: { label: 'Calendar Events' }, paletteType: 'calendar_list_events' },
    { type: 'googleDocsGetDocument', label: 'Google Docs Get Document', extra: { label: 'Google Docs Get' }, paletteType: 'google_docs_get_document' },
    { type: 'fetchUrl', label: 'Fetch URL', extra: { label: 'Fetch URL' }, paletteType: 'fetch_url' },
    {
        type: 'captureUrlSnapshot',
        label: 'URL snapshot',
        extra: { label: 'URL snapshot' },
        paletteType: 'capture_url_snapshot',
    },
];

export const WORKFLOW_PALETTE_UTILITY_ITEMS: readonly WorkflowPaletteStepItem[] = [
    { type: 'listToString', label: 'List to String', extra: { label: 'List to String' }, paletteType: 'list_to_string' },
    { type: 'stringToList', label: 'String to List', extra: { label: 'String to List' }, paletteType: 'string_to_list' },
    { type: 'prependText', label: 'Prepend Text', extra: { label: 'Prepend Text' }, paletteType: 'prepend_text' },
    { type: 'stringTrunc', label: 'String Trunc', extra: { label: 'String Trunc' }, paletteType: 'string_trunc' },
    { type: 'broadcastMessage', label: 'Broadcast Message', extra: { label: 'Broadcast Message' }, paletteType: 'broadcast_message' },
    { type: 'lenFromList', label: 'Len from List', extra: { label: 'Len from List' }, paletteType: 'len_from_list' },
    {
        type: 'randomItemFromList',
        label: 'Random item from list',
        extra: { label: 'Random item from list' },
        paletteType: 'random_item_from_list',
    },
    { type: 'intToString', label: 'Int to String', extra: { label: 'Int to String' }, paletteType: 'int_to_string' },
    { type: 'listItemByIndex', label: 'List Item by Index', extra: { label: 'List Item by Index' }, paletteType: 'list_item_by_index' },
    {
        type: 'dictionaryValueByKey',
        label: 'Dictionary Value by Key',
        extra: { label: 'Dictionary Value by Key' },
        paletteType: 'dictionary_value_by_key',
    },
    {
        type: 'dictionarySetValueByKey',
        label: 'Dictionary Set Value by Key',
        extra: { label: 'Dictionary Set Value by Key' },
        paletteType: 'dictionary_set_value_by_key',
    },
    {
        type: 'readDocumentProperty',
        label: 'Read Document Property',
        extra: { label: 'Read Document Property' },
        paletteType: 'read_document_property',
    },
    { type: 'loadDocument', label: 'Load Document', extra: { label: 'Load Document' }, paletteType: 'load_document' },
    { type: 'upsertDocument', label: 'Upsert Document', extra: { label: 'Upsert Document' }, paletteType: 'upsert_document' },
    {
        type: 'upsertDocument',
        label: 'Save text as Document',
        extra: { label: 'Save text as Document', template: 'text_only' },
        paletteType: 'upsert_document',
    },
    {
        type: 'parseDocumentBody',
        label: 'Parse Document Body',
        extra: { label: 'Parse Document Body' },
        paletteType: 'parse_document_body',
    },
    {
        type: 'htmlParseBasic',
        label: 'HTML Parse (basic)',
        extra: { label: 'HTML Parse (basic)' },
        paletteType: 'html_parse_basic',
    },
    {
        type: 'googleDocsParseDocument',
        label: 'Google Docs Parse Document',
        extra: { label: 'Google Docs Parse' },
        paletteType: 'google_docs_parse_document',
    },
    {
        type: 'writeObjectToDocumentBody',
        label: 'Write Object to Document Body',
        extra: { label: 'Write Object to Document Body' },
        paletteType: 'write_object_to_document_body',
    },
    {
        type: 'appendValueToDocument',
        label: 'Append Value to Document',
        extra: { label: 'Append Value to Document' },
        paletteType: 'append_value_to_document',
    },
    {
        type: 'validateAgainstStructure',
        label: 'Validate Against Structure',
        extra: { label: 'Validate Against Structure' },
        paletteType: 'validate_against_structure',
    },
    { type: 'addToList', label: 'Add to List', extra: { label: 'Add to List' }, paletteType: 'add_to_list' },
    { type: 'addDays', label: 'Add days', extra: { label: 'Add days' }, paletteType: 'add_days' },
    { type: 'addInts', label: 'Add', extra: { label: 'Add' }, paletteType: 'add_ints' },
    { type: 'subtractInts', label: 'Subtract', extra: { label: 'Subtract' }, paletteType: 'subtract_ints' },
    { type: 'multiplyInts', label: 'Multiply', extra: { label: 'Multiply' }, paletteType: 'multiply_ints' },
    { type: 'divideInts', label: 'Divide', extra: { label: 'Divide' }, paletteType: 'divide_ints' },
    { type: 'moduloInts', label: 'Modulo', extra: { label: 'Modulo' }, paletteType: 'modulo_ints' },
    { type: 'minInts', label: 'Min', extra: { label: 'Min' }, paletteType: 'min_ints' },
    { type: 'maxInts', label: 'Max', extra: { label: 'Max' }, paletteType: 'max_ints' },
];

/** Sandbox tick primitive + navigation utilities (separate palette section in the editor). */
export const WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS: readonly WorkflowPaletteStepItem[] = [
    {
        type: 'sandboxTickPrimitive',
        label: 'Tick Input',
        extra: { label: 'Tick Input' },
        paletteType: 'sandbox_tick',
    },
    {
        type: 'sandboxGetPosition',
        label: 'Get Position',
        extra: { label: 'Get Position' },
        paletteType: 'sandbox_get_position',
    },
    {
        type: 'sandboxGetFacing',
        label: 'Get Facing',
        extra: { label: 'Get Facing' },
        paletteType: 'sandbox_get_facing',
    },
    {
        type: 'sandboxGetNearby',
        label: 'Get Nearby',
        extra: { label: 'Get Nearby' },
        paletteType: 'sandbox_get_nearby',
    },
    {
        type: 'sandboxMoveForward',
        label: 'Move Forward',
        extra: { label: 'Move Forward' },
        paletteType: 'sandbox_move_forward',
    },
    {
        type: 'sandboxTurnLeft',
        label: 'Turn Left',
        extra: { label: 'Turn Left' },
        paletteType: 'sandbox_turn_left',
    },
    {
        type: 'sandboxTurnRight',
        label: 'Turn Right',
        extra: { label: 'Turn Right' },
        paletteType: 'sandbox_turn_right',
    },
    {
        type: 'sandboxIdle',
        label: 'Idle',
        extra: { label: 'Idle' },
        paletteType: 'sandbox_idle',
    },
    {
        type: 'sandboxPickUpItem',
        label: 'Pick Up Item',
        extra: { label: 'Pick Up Item' },
        paletteType: 'sandbox_pick_up_item',
    },
    {
        type: 'sandboxPlaceItem',
        label: 'Place Item',
        extra: { label: 'Place Item' },
        paletteType: 'sandbox_place_item',
    },
    {
        type: 'sandboxGetInventory',
        label: 'Get Inventory',
        extra: { label: 'Get Inventory' },
        paletteType: 'sandbox_get_inventory',
    },
    {
        type: 'sandboxGetCellItems',
        label: 'Get Cell Items',
        extra: { label: 'Get Cell Items' },
        paletteType: 'sandbox_get_cell_items',
    },
    {
        type: 'sandboxRemoveItemAtCell',
        label: 'Remove Item',
        extra: { label: 'Remove Item' },
        paletteType: 'sandbox_remove_item_at_cell',
    },
    {
        type: 'sandboxSpawnItemAtCell',
        label: 'Spawn Item',
        extra: {
            label: 'Spawn Item',
            required_inputs: [
                { key: 'definition_id', type: 'string', value: null },
                { key: 'target', type: 'string', value: 'self' },
            ],
        },
        paletteType: 'sandbox_spawn_item_at_cell',
    },
    {
        type: 'sandboxPromptUserAction',
        label: 'Prompt for User Action',
        extra: { label: 'Prompt for User Action' },
        paletteType: 'sandbox_prompt_user_action',
    },
    {
        type: 'sandboxForceSimulationPause',
        label: 'Force Simulation Pause',
        extra: { label: 'Force Simulation Pause' },
        paletteType: 'sandbox_force_simulation_pause',
    },
];

export const WORKFLOW_PALETTE_CONTROL_ITEMS: readonly WorkflowPaletteStepItem[] = [
    { type: 'basicConditional', label: 'Basic Conditional', extra: { label: 'Conditional' }, paletteType: 'basic_conditional' },
    { type: 'isControl', label: 'Is?', extra: { label: 'Is?' }, paletteType: 'is_control' },
    { type: 'isEmptyControl', label: 'Is Empty?', extra: { label: 'Is Empty?' }, paletteType: 'is_empty' },
    { type: 'gtControl', label: 'Gt?', extra: { label: 'Gt?' }, paletteType: 'gt_control' },
    { type: 'ltControl', label: 'Lt?', extra: { label: 'Lt?' }, paletteType: 'lt_control' },
    { type: 'gteControl', label: 'Gte?', extra: { label: 'Gte?' }, paletteType: 'gte_control' },
    { type: 'lteControl', label: 'Lte?', extra: { label: 'Lte?' }, paletteType: 'lte_control' },
    { type: 'andControl', label: 'And', extra: { label: 'And' }, paletteType: 'and_control' },
    { type: 'orControl', label: 'Or', extra: { label: 'Or' }, paletteType: 'or_control' },
    { type: 'xorControl', label: 'Xor', extra: { label: 'Xor' }, paletteType: 'xor_control' },
    { type: 'notControl', label: 'Not', extra: { label: 'Not' }, paletteType: 'not_control' },
    { type: 'betweenControl', label: 'Between', extra: { label: 'Between' }, paletteType: 'between_control' },
    { type: 'tryCatchControl', label: 'Try / Catch', extra: { label: 'Try / Catch' }, paletteType: 'try_catch_control' },
    { type: 'forLoopControl', label: 'For Loop', extra: { label: 'For Loop' }, paletteType: 'for_loop_control' },
    {
        type: 'forLoopEndControl',
        label: 'For Loop End',
        extra: { label: 'For Loop End', for_loop_id: '', exports: ['export'] },
        paletteType: 'for_loop_end_control',
    },
];

/** Editor-only canvas annotations (not executed; see `kind: "annotation"` in stored graph JSON). */
export const WORKFLOW_PALETTE_ANNOTATION_ITEMS: readonly WorkflowPaletteStepItem[] = [
    {
        type: 'annotationNote',
        label: 'Note',
        extra: {
            label: 'Note',
            text: '',
            color: null,
            label_font_size_px: ANNOTATION_NOTE_DEFAULT_LABEL_FONT_PX,
            content_font_size_px: 12,
            width: ANNOTATION_NOTE_DEFAULT_WIDTH,
            height: ANNOTATION_NOTE_DEFAULT_HEIGHT,
            z_index: ANNOTATION_NOTE_DEFAULT_Z_INDEX,
        },
        paletteType: 'annotation_note',
    },
    {
        type: 'annotationRegion',
        label: 'Region',
        extra: {
            label: 'Region',
            width: 400,
            height: 280,
            color: null,
            label_font_size_px: 11,
            z_index: ANNOTATION_REGION_DEFAULT_Z_INDEX,
        },
        paletteType: 'annotation_region',
    },
];

/** Types that exist on the canvas but are not palette tiles (template-only, legacy, or structural). */
const EXTRA_REACT_FLOW_TYPE_LABELS: Record<string, string> = {
    start: 'Start',
    workflowRef: 'Workflow',
    invalidStep: 'Invalid step',
};

let paletteLabelByReactFlowType: ReadonlyMap<string, string> | null = null;

function buildPaletteLabelByReactFlowType(): ReadonlyMap<string, string> {
    const m = new Map<string, string>();
    const all: readonly WorkflowPaletteStepItem[] = [
        ...WORKFLOW_PALETTE_FLOW_ITEMS,
        ...WORKFLOW_PALETTE_PRIMITIVE_ITEMS,
        ...WORKFLOW_PALETTE_SKILL_ITEMS,
        ...WORKFLOW_PALETTE_UTILITY_ITEMS,
        ...WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS,
        ...WORKFLOW_PALETTE_CONTROL_ITEMS,
        ...WORKFLOW_PALETTE_ANNOTATION_ITEMS,
    ];
    for (const item of all) {
        m.set(item.type, item.label);
    }
    return m;
}

/**
 * Display name for a React Flow node `type`, matching the left palette tile label (e.g. "Len from List").
 * For types not in the palette (Start, legacy Sandbox behavior, invalid step), returns a fixed label.
 */
export function paletteDisplayNameForReactFlowType(reactFlowType: string): string {
    if (!paletteLabelByReactFlowType) {
        paletteLabelByReactFlowType = buildPaletteLabelByReactFlowType();
    }
    const fromPalette = paletteLabelByReactFlowType.get(reactFlowType);
    if (fromPalette !== undefined) return fromPalette;
    const extra = EXTRA_REACT_FLOW_TYPE_LABELS[reactFlowType];
    if (extra !== undefined) return extra;
    return reactFlowType;
}
