/**
 * Canvas handle ids rendered by workflow editor node components (mirrors nodeTypes.tsx).
 * Used by graph wiring validation — keep in sync when node handle layouts change.
 */
import type { Node } from '@xyflow/react';
import type { RequiredInput, RequiredOutput } from '../../api/types';
import { normalizeUpsertDocumentRequiredInputs } from './graphConverters';
import { DEFAULT_FOR_LOOP_END_EXPORTS } from './forLoopEndPairing';
import {
    CALENDAR_LIST_EVENTS_HANDLES,
    CAPTURE_URL_SNAPSHOT_HANDLES,
    FETCH_URL_HANDLES,
    GMAIL_LIST_MESSAGES_HANDLES,
    MULTIMODAL_LLM_HANDLES,
    PREPEND_TEXT_HANDLES,
    SIMPLE_LLM_HANDLES,
    STRING_TRUNC_HANDLES,
    TEXT_TO_SPEECH_HANDLES,
} from './constants';

export type CanvasNodeHandles = {
    sourceHandles: string[];
    targetHandles: string[];
    /** When true, any edge touching this node is a wiring issue. */
    rejectsEdges?: boolean;
};

const TRIGGER = 'trigger';
const SIGNAL = 'signal_out';

function withTrigger(keys: string[]): string[] {
    return keys.length > 0 ? [TRIGGER, ...keys] : [TRIGGER];
}

function withSignal(keys: string[]): string[] {
    return keys.length > 0 ? [SIGNAL, ...keys] : [SIGNAL];
}

function startOutputKeys(data: Record<string, unknown>): string[] {
    const rawInputs = data.required_inputs as RequiredInput[] | undefined;
    if (rawInputs === undefined) {
        return ['user_input'];
    }
    if (Array.isArray(rawInputs) && rawInputs.length === 0) {
        return ['output'];
    }
    return rawInputs.map(r => r.key).filter(Boolean);
}

function stopTargetKeys(data: Record<string, unknown>): string[] {
    const outs = (data.required_outputs as RequiredOutput[] | undefined) ?? [{ key: 'output', type: 'string' }];
    const dataKey = outs[0]?.key ?? 'output';
    return [TRIGGER, dataKey];
}

function workflowRefHandles(data: Record<string, unknown>): { inputs: string[]; outputs: string[] } {
    const rawInputs = (data.subWorkflowRequiredInputs as RequiredInput[] | undefined) ?? [
        { key: 'user_input', type: 'string' as const },
    ];
    const rawOutputs = (data.subWorkflowRequiredOutputs as RequiredOutput[] | undefined) ?? [
        { key: 'output', type: 'string' as const },
    ];
    return {
        inputs: rawInputs.map(r => r.key),
        outputs: rawOutputs.map(r => r.key),
    };
}

function forLoopEndInputKeys(data: Record<string, unknown>): string[] {
    const exports = Array.isArray(data.exports) && (data.exports as string[]).length > 0
        ? (data.exports as string[])
        : [...DEFAULT_FOR_LOOP_END_EXPORTS];
    return exports;
}

const BRANCH_OUTPUTS = ['true', 'false'] as const;
const COMPARE_INPUTS = ['input_a', 'input_b'] as const;

/** Returns handle ids that React Flow registers on the node card. */
export function getCanvasNodeHandles(node: Node): CanvasNodeHandles {
    const type = node.type ?? '';
    const data = (node.data ?? {}) as Record<string, unknown>;

    if (type === 'annotationNote' || type === 'annotationRegion') {
        return { sourceHandles: [], targetHandles: [], rejectsEdges: true };
    }

    if (type === 'invalidStep') {
        return { sourceHandles: withSignal([]), targetHandles: withTrigger([]) };
    }

    if (type === 'start') {
        return { sourceHandles: withSignal(startOutputKeys(data)), targetHandles: [] };
    }

    if (type === 'stop') {
        return { sourceHandles: [], targetHandles: stopTargetKeys(data) };
    }

    if (type === 'workflowRef') {
        const { inputs, outputs } = workflowRefHandles(data);
        return { sourceHandles: withSignal(outputs), targetHandles: withTrigger(inputs) };
    }

    if (type === 'forLoopControl') {
        return { sourceHandles: withSignal(['item', 'summary']), targetHandles: withTrigger(['input']) };
    }

    if (type === 'forLoopEndControl') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(forLoopEndInputKeys(data)),
        };
    }

    if (type === 'tryCatchControl') {
        return {
            sourceHandles: withSignal(['try', 'catch', 'output', 'envelope']),
            targetHandles: withTrigger(['value']),
        };
    }

    if (
        type === 'basicConditional' ||
        type === 'isControl' ||
        type === 'isEmptyControl' ||
        type === 'gtControl' ||
        type === 'ltControl' ||
        type === 'gteControl' ||
        type === 'lteControl' ||
        type === 'betweenControl'
    ) {
        const inputs =
            type === 'basicConditional'
                ? ['condition']
                : type === 'isEmptyControl'
                  ? ['value']
                  : type === 'betweenControl'
                    ? ['low', 'value', 'high']
                    : [...COMPARE_INPUTS];
        return { sourceHandles: withSignal([...BRANCH_OUTPUTS]), targetHandles: withTrigger(inputs) };
    }

    if (type === 'andControl' || type === 'orControl' || type === 'xorControl') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([...COMPARE_INPUTS]) };
    }

    if (type === 'notControl') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['input']) };
    }

    if (type === 'simpleLLMCall') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(SIMPLE_LLM_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'multimodalLLMCall') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(MULTIMODAL_LLM_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'prependText') {
        return {
            sourceHandles: withSignal(['output_string']),
            targetHandles: withTrigger(PREPEND_TEXT_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'stringTrunc') {
        return {
            sourceHandles: withSignal(['output_string']),
            targetHandles: withTrigger(STRING_TRUNC_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'textToSpeech') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(TEXT_TO_SPEECH_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'gmailListMessages') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(GMAIL_LIST_MESSAGES_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'calendarListEvents') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(CALENDAR_LIST_EVENTS_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'fetchUrl') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(FETCH_URL_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'captureUrlSnapshot') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(CAPTURE_URL_SNAPSHOT_HANDLES.map(h => h.id)),
        };
    }

    if (type === 'googleDocsGetDocument') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['document_url_or_id']) };
    }

    if (type === 'googleDocsParseDocument') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['document']) };
    }

    if (type === 'transcribeAudio' || type === 'audioFileInput') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([]) };
    }

    if (type === 'transcribeFile') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([]) };
    }

    if (type === 'broadcastMessage') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['message', 'title']) };
    }

    if (
        type === 'stringPrimitive' ||
        type === 'sandboxTickPrimitive' ||
        type === 'listPrimitive' ||
        type === 'dictionaryPrimitive' ||
        type === 'booleanPrimitive' ||
        type === 'intPrimitive' ||
        type === 'dateTimePrimitive' ||
        type === 'structurePrimitive' ||
        type === 'documentPrimitive' ||
        type === 'imagePrimitive' ||
        type === 'gmailPrimitive' ||
        type === 'listToString' ||
        type === 'stringToList' ||
        type === 'intToString'
    ) {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['input']) };
    }

    if (type === 'sandboxRegionPrimitive') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([]) };
    }

    if (
        type === 'sandboxGetPosition' ||
        type === 'sandboxGetFacing' ||
        type === 'sandboxGetNearby' ||
        type === 'sandboxGetInventory' ||
        type === 'sandboxGetCellItems'
    ) {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['input']) };
    }

    if (
        type === 'sandboxMoveForward' ||
        type === 'sandboxTurnLeft' ||
        type === 'sandboxTurnRight' ||
        type === 'sandboxIdle' ||
        type === 'sandboxPickUpItem'
    ) {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['reason']) };
    }

    if (type === 'sandboxPlaceItem') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['reason', 'item_type']),
        };
    }

    if (type === 'sandboxRemoveItemAtCell') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['reason', 'item_id']),
        };
    }

    if (type === 'sandboxSpawnItemAtCell') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['reason', 'definition_id']),
        };
    }

    if (type === 'sandboxPromptUserAction' || type === 'sandboxForceSimulationPause') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['reason']) };
    }

    if (type === 'lenFromList' || type === 'randomItemFromList') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['list']) };
    }

    if (type === 'listItemByIndex') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['index', 'list']) };
    }

    if (type === 'dictionaryValueByKey') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['key', 'dictionary', 'fallback']),
        };
    }

    if (type === 'dictionarySetValueByKey') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['dictionary', 'key', 'value']),
        };
    }

    if (type === 'readDocumentProperty') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['target_property', 'document']),
        };
    }

    if (type === 'loadDocument') {
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(['document_id', 'document_name']),
        };
    }

    if (type === 'upsertDocument') {
        const normalized = normalizeUpsertDocumentRequiredInputs(
            (data.required_inputs as RequiredInput[] | undefined) ?? null,
        );
        return {
            sourceHandles: withSignal(['output']),
            targetHandles: withTrigger(normalized.map(r => r.key)),
        };
    }

    if (type === 'parseDocumentBody' || type === 'htmlParseBasic') {
        const inputKey = type === 'htmlParseBasic' ? 'html' : 'document';
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([inputKey]) };
    }

    if (type === 'writeObjectToDocumentBody') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['value']) };
    }

    if (type === 'appendValueToDocument') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['document', 'value']) };
    }

    if (type === 'validateAgainstStructure') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['value', 'structure']) };
    }

    if (type === 'addToList') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['list', 'value']) };
    }

    if (type === 'addDays') {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['input', 'days']) };
    }

    if (
        type === 'addInts' ||
        type === 'subtractInts' ||
        type === 'multiplyInts' ||
        type === 'divideInts' ||
        type === 'moduloInts' ||
        type === 'minInts' ||
        type === 'maxInts'
    ) {
        return { sourceHandles: withSignal(['output']), targetHandles: withTrigger([...COMPARE_INPUTS]) };
    }

    return { sourceHandles: withSignal(['output']), targetHandles: withTrigger(['input']) };
}
