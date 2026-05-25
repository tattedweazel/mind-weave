/**
 * Detects edge handle mismatches that cause React Flow error #008 on the workflow canvas.
 */
import type { Edge, Node } from '@xyflow/react';
import type { RequiredInput } from '../../api/types';
import { normalizeUpsertDocumentRequiredInputs } from './graphConverters';
import { DEFAULT_FOR_LOOP_END_EXPORTS } from './forLoopEndPairing';
import { getCanvasNodeHandles } from './workflowNodeCanvasHandles';

export type WorkflowGraphWiringIssueKind =
    | 'missing_source_node'
    | 'missing_target_node'
    | 'invalid_source_handle'
    | 'invalid_target_handle'
    | 'annotation_edge';

/** Prefer committed React Flow edges; fall back to pending queue during deferred edge commit. */
export function resolveEdgesForWiringValidation(
    committedEdges: Edge[],
    pendingEdges: Edge[] | null,
): Edge[] {
    return committedEdges.length > 0 ? committedEdges : (pendingEdges ?? []);
}

export type WorkflowGraphWiringIssue = {
    edgeId: string;
    kind: WorkflowGraphWiringIssueKind;
    sourceNodeId: string;
    targetNodeId: string;
    sourceHandle: string | null;
    targetHandle: string | null;
    message: string;
    validSourceHandles?: string[];
    validTargetHandles?: string[];
};

function nodeLabel(node: Node | undefined, fallbackId: string): string {
    if (!node) return fallbackId;
    const label = (node.data as { label?: string } | undefined)?.label;
    return typeof label === 'string' && label.trim() ? label.trim() : fallbackId;
}

function formatHandleList(handles: string[]): string {
    return handles.map(h => `\`${h}\``).join(', ');
}

/** Mirrors key defaults from appEdgeToFlow so legacy graphs are not false-positive. */
export function normalizeEdgeHandlesForValidation(
    edge: Pick<Edge, 'sourceHandle' | 'targetHandle'>,
    sourceNode: Node | undefined,
    targetNode: Node | undefined,
): { sourceHandle: string | null; targetHandle: string | null } {
    let sourceHandle = edge.sourceHandle ?? null;
    let targetHandle = edge.targetHandle ?? null;

    if (targetNode) {
        const t = targetNode.type ?? '';
        if (
            (t === 'stringPrimitive' ||
                t === 'sandboxTickPrimitive' ||
                t === 'listPrimitive' ||
                t === 'dictionaryPrimitive' ||
                t === 'booleanPrimitive' ||
                t === 'intPrimitive' ||
                t === 'dateTimePrimitive' ||
                t === 'listToString' ||
                t === 'stringToList' ||
                t === 'intToString') &&
            (targetHandle == null || targetHandle === '')
        ) {
            targetHandle = 'input';
        }
        if (t === 'lenFromList' || t === 'randomItemFromList' || t === 'listItemByIndex') {
            if (targetHandle == null || targetHandle === '') targetHandle = 'list';
        }
        if (
            (t === 'sandboxGetPosition' ||
                t === 'sandboxGetFacing' ||
                t === 'sandboxGetNearby' ||
                t === 'sandboxGetInventory' ||
                t === 'sandboxGetCellItems') &&
            (targetHandle == null || targetHandle === '')
        ) {
            targetHandle = 'input';
        }
        if (
            (t === 'sandboxMoveForward' ||
                t === 'sandboxTurnLeft' ||
                t === 'sandboxTurnRight' ||
                t === 'sandboxIdle' ||
                t === 'sandboxPickUpItem') &&
            (targetHandle == null || targetHandle === '')
        ) {
            targetHandle = 'reason';
        }
        if (t === 'sandboxPlaceItem' && (targetHandle == null || targetHandle === '')) {
            targetHandle = 'item_type';
        }
        if (t === 'sandboxRemoveItemAtCell' && (targetHandle == null || targetHandle === '')) {
            targetHandle = 'item_id';
        }
        if (t === 'sandboxSpawnItemAtCell' && (targetHandle == null || targetHandle === '')) {
            targetHandle = 'definition_id';
        }
        if (t === 'dictionaryValueByKey' || t === 'dictionarySetValueByKey') {
            if (targetHandle == null || targetHandle === '') targetHandle = 'dictionary';
        }
        if (t === 'readDocumentProperty' && (targetHandle == null || targetHandle === '')) {
            targetHandle = 'document';
        }
        if (t === 'loadDocument' && (targetHandle == null || targetHandle === '')) {
            targetHandle = 'document_id';
        }
        if (t === 'stop') {
            const outs = (targetNode.data as { required_outputs?: { key: string }[] })?.required_outputs ?? [
                { key: 'output', type: 'string' },
            ];
            const dataKey = outs[0]?.key ?? 'output';
            if (targetHandle !== 'trigger' && (targetHandle == null || targetHandle === '')) {
                targetHandle = dataKey;
            }
        }
    }

    if (sourceNode) {
        const s = sourceNode.type ?? '';
        if (
            (sourceHandle == null || sourceHandle === '') &&
            (s === 'stringPrimitive' ||
                s === 'sandboxTickPrimitive' ||
                s === 'listPrimitive' ||
                s === 'dictionaryPrimitive' ||
                s === 'booleanPrimitive' ||
                s === 'intPrimitive' ||
                s === 'dateTimePrimitive' ||
                s === 'structurePrimitive' ||
                s === 'documentPrimitive' ||
                s === 'imagePrimitive' ||
                s === 'gmailPrimitive' ||
                s === 'listToString' ||
                s === 'stringToList' ||
                s === 'prependText' ||
                s === 'stringTrunc' ||
                s === 'lenFromList' ||
                s === 'randomItemFromList' ||
                s === 'intToString' ||
                s === 'listItemByIndex' ||
                s === 'dictionaryValueByKey' ||
                s === 'dictionarySetValueByKey' ||
                s === 'readDocumentProperty' ||
                s === 'loadDocument' ||
                s === 'upsertDocument' ||
                s === 'parseDocumentBody' ||
                s === 'htmlParseBasic' ||
                s === 'writeObjectToDocumentBody' ||
                s === 'appendValueToDocument' ||
                s === 'validateAgainstStructure' ||
                s === 'addToList' ||
                s === 'addDays' ||
                s === 'addInts' ||
                s === 'subtractInts' ||
                s === 'multiplyInts' ||
                s === 'divideInts' ||
                s === 'moduloInts' ||
                s === 'minInts' ||
                s === 'maxInts' ||
                s === 'andControl' ||
                s === 'orControl' ||
                s === 'xorControl' ||
                s === 'notControl' ||
                s === 'sandboxGetPosition' ||
                s === 'sandboxGetFacing' ||
                s === 'sandboxGetNearby' ||
                s === 'sandboxGetInventory' ||
                s === 'sandboxGetCellItems' ||
                s === 'sandboxMoveForward' ||
                s === 'sandboxTurnLeft' ||
                s === 'sandboxTurnRight' ||
                s === 'sandboxIdle' ||
                s === 'sandboxPickUpItem' ||
                s === 'sandboxPlaceItem' ||
                s === 'sandboxRemoveItemAtCell' ||
                s === 'sandboxSpawnItemAtCell' ||
                s === 'sandboxPromptUserAction' ||
                s === 'sandboxForceSimulationPause')
        ) {
            sourceHandle = s === 'prependText' || s === 'stringTrunc' ? 'output_string' : 'output';
        }
        if (s === 'forLoopControl' && (sourceHandle == null || sourceHandle === '')) {
            sourceHandle = 'item';
        }
        if (s === 'tryCatchControl' && (sourceHandle == null || sourceHandle === '')) {
            sourceHandle = 'output';
        }
        if (s === 'forLoopEndControl' && (sourceHandle == null || sourceHandle === '')) {
            sourceHandle = 'output';
        }
        if (s === 'start' && (sourceHandle == null || sourceHandle === '')) {
            const inputs = (sourceNode.data as { required_inputs?: RequiredInput[] })?.required_inputs;
            if (Array.isArray(inputs) && inputs.length > 0) {
                sourceHandle = inputs[0]?.key ?? 'user_input';
            } else {
                sourceHandle = 'output';
            }
        }
    }

    if (
        sourceNode &&
        targetNode &&
        (targetHandle == null || targetHandle === '') &&
        [
            'basicConditional',
            'isControl',
            'isEmptyControl',
            'gtControl',
            'ltControl',
            'gteControl',
            'lteControl',
            'betweenControl',
            'tryCatchControl',
            'forLoopControl',
            'forLoopEndControl',
            'simpleLLMCall',
            'multimodalLLMCall',
            'textToSpeech',
            'transcribeAudio',
            'audioFileInput',
            'transcribeFile',
            'gmailListMessages',
            'calendarListEvents',
            'googleDocsGetDocument',
            'googleDocsParseDocument',
            'fetchUrl',
            'captureUrlSnapshot',
            'broadcastMessage',
            'workflowRef',
            'stop',
        ].includes(targetNode.type ?? '') &&
        ((['basicConditional', 'isControl', 'isEmptyControl', 'gtControl', 'ltControl', 'gteControl', 'lteControl', 'betweenControl'].includes(
            sourceNode.type ?? '',
        ) &&
            (sourceHandle === 'true' || sourceHandle === 'false')) ||
            (sourceNode.type === 'tryCatchControl' && (sourceHandle === 'try' || sourceHandle === 'catch')))
    ) {
        targetHandle = 'trigger';
    }

    if (targetNode?.type === 'forLoopEndControl' && (targetHandle == null || targetHandle === '')) {
        const ex = (targetNode.data as { exports?: string[] })?.exports;
        targetHandle = Array.isArray(ex) && ex.length > 0 ? ex[0] : DEFAULT_FOR_LOOP_END_EXPORTS[0];
    }

    if (targetNode?.type === 'upsertDocument' && (targetHandle == null || targetHandle === '')) {
        const requiredInputs = normalizeUpsertDocumentRequiredInputs(
            (targetNode.data as { required_inputs?: RequiredInput[] })?.required_inputs,
        );
        targetHandle = requiredInputs.find(r => r.key === 'content')?.key ?? requiredInputs[0]?.key ?? 'content';
    }

    return { sourceHandle, targetHandle };
}

export function findWorkflowGraphWiringIssues(nodes: Node[], edges: Edge[]): WorkflowGraphWiringIssue[] {
    const nodeById = new Map(nodes.map(n => [n.id, n]));
    const issues: WorkflowGraphWiringIssue[] = [];

    for (const edge of edges) {
        const sourceNode = nodeById.get(edge.source);
        const targetNode = nodeById.get(edge.target);
        const edgeLabel = edge.id;

        if (!sourceNode) {
            issues.push({
                edgeId: edge.id,
                kind: 'missing_source_node',
                sourceNodeId: edge.source,
                targetNodeId: edge.target,
                sourceHandle: edge.sourceHandle ?? null,
                targetHandle: edge.targetHandle ?? null,
                message: `Edge ${edgeLabel}: source node ${edge.source} is missing from the graph. Delete this connection or restore the node.`,
            });
            continue;
        }

        if (!targetNode) {
            issues.push({
                edgeId: edge.id,
                kind: 'missing_target_node',
                sourceNodeId: edge.source,
                targetNodeId: edge.target,
                sourceHandle: edge.sourceHandle ?? null,
                targetHandle: edge.targetHandle ?? null,
                message: `Edge ${edgeLabel}: target node ${edge.target} is missing from the graph. Delete this connection or restore the node.`,
            });
            continue;
        }

        const sourceHandles = getCanvasNodeHandles(sourceNode);
        const targetHandles = getCanvasNodeHandles(targetNode);

        if (sourceHandles.rejectsEdges || targetHandles.rejectsEdges) {
            issues.push({
                edgeId: edge.id,
                kind: 'annotation_edge',
                sourceNodeId: edge.source,
                targetNodeId: edge.target,
                sourceHandle: edge.sourceHandle ?? null,
                targetHandle: edge.targetHandle ?? null,
                message: `Edge ${edgeLabel}: connections to or from layout annotations (notes/regions) are not supported. Delete this connection.`,
            });
            continue;
        }

        const { sourceHandle, targetHandle } = normalizeEdgeHandlesForValidation(edge, sourceNode, targetNode);

        if (sourceHandle != null && sourceHandle !== '' && !sourceHandles.sourceHandles.includes(sourceHandle)) {
            const srcLabel = nodeLabel(sourceNode, edge.source);
            issues.push({
                edgeId: edge.id,
                kind: 'invalid_source_handle',
                sourceNodeId: edge.source,
                targetNodeId: edge.target,
                sourceHandle,
                targetHandle,
                validSourceHandles: sourceHandles.sourceHandles,
                message:
                    `Edge ${edgeLabel}: ${srcLabel} has no output ${formatHandleList([sourceHandle])}. ` +
                    `Valid outputs: ${formatHandleList(sourceHandles.sourceHandles)}. ` +
                    'Delete this connection or add/rename a Start output (or nested workflow Stop output) to match.',
            });
        }

        if (targetHandle != null && targetHandle !== '' && !targetHandles.targetHandles.includes(targetHandle)) {
            const tgtLabel = nodeLabel(targetNode, edge.target);
            issues.push({
                edgeId: edge.id,
                kind: 'invalid_target_handle',
                sourceNodeId: edge.source,
                targetNodeId: edge.target,
                sourceHandle,
                targetHandle,
                validTargetHandles: targetHandles.targetHandles,
                message:
                    `Edge ${edgeLabel}: ${tgtLabel} has no input ${formatHandleList([targetHandle])}. ` +
                    `Valid inputs: ${formatHandleList(targetHandles.targetHandles)}. ` +
                    'Delete this connection or rename the target slot in the Explorer.',
            });
        }
    }

    return issues;
}

export { getCanvasNodeHandles } from './workflowNodeCanvasHandles';
