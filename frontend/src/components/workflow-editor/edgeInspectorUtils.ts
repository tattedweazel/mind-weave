import type { Edge } from '@xyflow/react';
import type { NodeRunResult } from '../../api/types';

/** Short labels for palette / graph output-type keys (matches getSourceOutputType). */
export function workflowEdgeDataTypeLabel(typeKey: string): string {
    const m: Record<string, string> = {
        string: 'String',
        list: 'List',
        dictionary: 'Dictionary',
        structure: 'Structure',
        document: 'Document',
        gmail: 'Gmail message',
        audio: 'Audio (WAV)',
        boolean: 'Boolean',
        int: 'Int',
        datetime: 'DateTime',
        any: 'Any',
        trigger: 'Trigger (control-flow)',
        signal: 'Signal (control-flow)',
        basic_conditional: 'Conditional branch',
        is_control: 'Comparison (is)',
        is_empty: 'Empty test (is_empty)',
        gt_control: 'Comparison (gt)',
        workflow: 'Sub-workflow output',
        simple_llm_call: 'LLM / structured output',
        multimodal_llm: 'Multimodal LLM / structured output',
        text_to_speech: 'Text-to-Speech (audio)',
        transcribe_audio: 'Voice input (text)',
        audio_file_input: 'Audio File Input (text)',
        gmail_list_messages: 'Gmail list (list)',
        calendar_list_events: 'Calendar events (dictionary)',
        primitive: 'Primitive',
        skill: 'Skill',
        utility: 'Utility',
        control: 'Control',
    };
    return m[typeKey] ?? typeKey.replace(/_/g, ' ');
}

const FLOW_TYPE_LABELS: Record<string, string> = {
    simpleLLMCall: 'Simple LLM Call',
    multimodalLLMCall: 'Multimodal LLM',
    textToSpeech: 'Text-to-Speech',
    transcribeAudio: 'Voice input',
    audioFileInput: 'Audio File Input',
    gmailListMessages: 'Gmail List',
    calendarListEvents: 'Calendar List',
    googleDocsGetDocument: 'Google Docs Get',
    googleDocsParseDocument: 'Google Docs Parse',
    fetchUrl: 'Fetch URL',
    stringPrimitive: 'String',
    listPrimitive: 'List',
    dictionaryPrimitive: 'Dictionary',
    booleanPrimitive: 'Boolean',
    intPrimitive: 'Int',
    dateTimePrimitive: 'DateTime',
    gmailPrimitive: 'Gmail',
    structurePrimitive: 'Structure',
    documentPrimitive: 'Document',
    imagePrimitive: 'Image',
    listToString: 'List to String',
    stringToList: 'String to List',
    prependText: 'Prepend Text',
    stringTrunc: 'String Trunc',
    messageUtility: 'Message',
    lenFromList: 'Len from List',
    randomItemFromList: 'Random item from list',
    sandboxGetPosition: 'Get position',
    sandboxGetFacing: 'Get facing',
    sandboxGetNearby: 'Get nearby',
    sandboxPromptUserAction: 'Prompt for User Action',
    sandboxMoveForward: 'Move forward',
    sandboxTurnLeft: 'Turn left',
    sandboxTurnRight: 'Turn right',
    sandboxIdle: 'Idle',
    sandboxTickPrimitive: 'Tick input',
    intToString: 'Int to String',
    listItemByIndex: 'List Item by Index',
    dictionaryValueByKey: 'Dictionary Value by Key',
    dictionarySetValueByKey: 'Dictionary Set Value by Key',
    readDocumentProperty: 'Read Document Property',
    loadDocument: 'Load Document',
    upsertDocument: 'Upsert / save document',
    parseDocumentBody: 'Parse Document Body',
    htmlParseBasic: 'HTML Parse (basic)',
    writeObjectToDocumentBody: 'Write Object to Document Body',
    appendValueToDocument: 'Append Value to Document',
    validateAgainstStructure: 'Validate Against Structure',
    addToList: 'Add to List',
    addDays: 'Add days',
    addInts: 'Add (ints)',
    subtractInts: 'Subtract (ints)',
    multiplyInts: 'Multiply (ints)',
    divideInts: 'Divide (ints)',
    moduloInts: 'Modulo',
    minInts: 'Min (ints)',
    maxInts: 'Max (ints)',
    basicConditional: 'Basic Conditional',
    isControl: 'Is?',
    isEmptyControl: 'Is Empty?',
    gtControl: 'Gt?',
    ltControl: 'Lt?',
    gteControl: 'Gte?',
    lteControl: 'Lte?',
    andControl: 'And',
    orControl: 'Or',
    xorControl: 'Xor',
    notControl: 'Not',
    betweenControl: 'Between',
    tryCatchControl: 'Try / Catch',
    forLoopControl: 'For Loop',
    forLoopEndControl: 'For Loop End',
    start: 'Start',
    stop: 'Stop',
    workflowRef: 'Workflow',
};

export function workflowNodeFlowTypeLabel(flowType: string | undefined): string {
    if (!flowType) return 'Node';
    return FLOW_TYPE_LABELS[flowType] ?? flowType;
}

export function resolveLatestNodeRun(
    nodeId: string,
    lastRunMap: Record<string, NodeRunResult>,
    runResult: { node_results?: NodeRunResult[] } | null,
): NodeRunResult | undefined {
    const fromStream = lastRunMap[nodeId];
    if (fromStream) return fromStream;
    const list = runResult?.node_results?.filter((r) => r.node_id === nodeId);
    if (!list?.length) return undefined;
    return list.reduce((a, b) => (a.step_number ?? 0) >= (b.step_number ?? 0) ? a : b);
}

/** Match backend `_get_slot_value` + resolution coercions where JSON is a plain object. */
export function extractPayloadFromSourceOutput(output: unknown, sourceHandle: string | undefined): unknown {
    if (output == null) return output;
    if (typeof output !== 'object') return output;
    const o = output as Record<string, unknown>;
    const kind = o.kind;
    if (kind === 'start') {
        const outputs = o.outputs as Record<string, unknown> | undefined;
        if (!outputs || typeof outputs !== 'object') return output;
        if (sourceHandle && sourceHandle in outputs) return outputs[sourceHandle];
        const first = Object.keys(outputs)[0];
        return first !== undefined ? outputs[first] : output;
    }
    if (kind === 'string' || kind === 'response') return o.text;
    if (kind === 'list') return o.data;
    if (kind === 'dictionary') return o.data;
    if (kind === 'boolean' || kind === 'int') return o.value;
    if (kind === 'structure') return o.schema_dict;
    if (kind === 'conditional') return o.branch;
    if (kind === 'stop') return o.text;
    return output;
}

export type EdgePayloadResolution =
    | { kind: 'payload'; value: unknown; via: 'resolved_inputs' | 'source_output' }
    | { kind: 'control_flow'; message: string }
    | { kind: 'none'; message: string };

/**
 * Best-effort value that traveled this edge into the target's input (last run).
 * Prefer target `details.resolved_inputs[targetHandle]` when present; else derive from source output.
 */
export function resolveEdgeDeliveredPayload(
    edge: Pick<Edge, 'source' | 'target' | 'sourceHandle' | 'targetHandle'>,
    targetNodeType: string | undefined,
    sourceRun: NodeRunResult | undefined,
    targetRun: NodeRunResult | undefined,
): EdgePayloadResolution {
    const th = edge.targetHandle ?? null;
    if (th === 'trigger') {
        return {
            kind: 'control_flow',
            message:
                'Control-flow connection (trigger). No data payload is carried on this wire—the downstream step runs when its branch fires.',
        };
    }

    const resolved = targetRun?.details?.resolved_inputs;
    if (resolved && typeof resolved === 'object' && !Array.isArray(resolved)) {
        const ri = resolved as Record<string, unknown>;
        const keysToTry: string[] = [];
        if (th) keysToTry.push(th);
        if (!th && targetNodeType === 'simpleLLMCall') keysToTry.push('user_prompt');
        if (!th && targetNodeType === 'multimodalLLMCall') keysToTry.push('user_prompt');
        if (!th && targetNodeType === 'textToSpeech') keysToTry.push('text');
        if (!th && (targetNodeType === 'transcribeAudio' || targetNodeType === 'audioFileInput')) keysToTry.push('trigger');
        for (const k of keysToTry) {
            if (k in ri) {
                return { kind: 'payload', value: ri[k], via: 'resolved_inputs' };
            }
        }
    }

    if (sourceRun?.output != null) {
        const v = extractPayloadFromSourceOutput(sourceRun.output, edge.sourceHandle ?? undefined);
        return { kind: 'payload', value: v, via: 'source_output' };
    }

    return {
        kind: 'none',
        message:
            'No last-run payload found for this connection. Run the workflow with **Last run** / **Run logs** available, or the target step may not have executed yet.',
    };
}
