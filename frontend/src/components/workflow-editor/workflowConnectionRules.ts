/**
 * Pure rules for whether React Flow may create a workflow edge.
 * Kept separate from WorkflowEditor for unit testing and to mirror appEdgeToFlow Stop normalization.
 */
import type { Connection, Edge, Node } from '@xyflow/react';

import type { RequiredInput, RequiredOutput } from '../../api/types';
import { getSourceOutputType, isAnnotationFlowNodeType } from './graphConverters';

function stopPrimaryOutput(targetNode: Node): RequiredOutput {
    const raw = (targetNode.data as { required_outputs?: RequiredOutput[] })?.required_outputs;
    return Array.isArray(raw) && raw.length > 0 ? raw[0] : { key: 'output', type: 'string' as const };
}

/** Exported for tests that assert normalization matches {@link appEdgeToFlow} behavior. */
export function stopDataHandleKeyForConnection(targetNode: Node): string {
    return stopPrimaryOutput(targetNode).key ?? 'output';
}

/** Resolves a target handle's declared `required_inputs` type for connection gating (e.g. Document → string slots). */
export function getTargetHandleType(node: Node, handle: string | null | undefined): RequiredInput['type'] | undefined {
    if (handle == null || handle === '') return undefined;
    const raw = (node.data as { required_inputs?: RequiredInput[] })?.required_inputs;
    if (!Array.isArray(raw)) return undefined;
    const item = raw.find(
        (r): r is RequiredInput => Boolean(r && typeof r === 'object' && 'key' in r && (r as RequiredInput).key === handle),
    );
    return item?.type;
}

function documentSourceAllowsNonStopTarget(targetNode: Node, targetHandle: string | null | undefined): boolean {
    const t = getTargetHandleType(targetNode, targetHandle);
    return t === 'string' || t === 'any';
}

export function isValidWorkflowConnection(nodes: Node[], edges: Edge[], connection: Connection | Edge): boolean {
    const targetNode = nodes.find(n => n.id === connection.target);
    const sourceNode = nodes.find(n => n.id === connection.source);
    if (!targetNode || !sourceNode) return false;
    if (isAnnotationFlowNodeType(sourceNode.type) || isAnnotationFlowNodeType(targetNode.type)) return false;

    const sourceHandle = 'sourceHandle' in connection ? connection.sourceHandle : (connection as Edge).sourceHandle;
    let targetHandle = 'targetHandle' in connection ? connection.targetHandle : (connection as Edge).targetHandle;

    if (targetNode.type === 'stop') {
        const dataKey = stopDataHandleKeyForConnection(targetNode);
        if (targetHandle !== 'trigger' && (targetHandle == null || targetHandle === '')) {
            targetHandle = dataKey;
        }
    }

    if (targetHandle === 'trigger') {
        if (
            targetNode.type === 'transcribeAudio' ||
            targetNode.type === 'audioFileInput' ||
            targetNode.type === 'transcribeFile'
        ) {
            if (sourceHandle === 'signal_out') return true;
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
            if (branchControls.includes(sourceNode.type ?? '') && (sourceHandle === 'true' || sourceHandle === 'false')) {
                return true;
            }
            if (
                sourceNode.type === 'tryCatchControl' &&
                (sourceHandle === 'try' || sourceHandle === 'catch')
            )
                return true;
            return true;
        }
        if (sourceHandle === 'signal_out') return true;
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
        if (branchControls.includes(sourceNode.type ?? '') && (sourceHandle === 'true' || sourceHandle === 'false')) return true;
        if (
            sourceNode.type === 'tryCatchControl' &&
            (sourceHandle === 'try' || sourceHandle === 'catch')
        )
            return true;
        return false;
    }
    if (sourceHandle === 'signal_out') return false;
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
    if ((sourceHandle === 'true' || sourceHandle === 'false') && branchControls.includes(sourceNode.type ?? '')) return false;

    if (sourceNode.type === 'structurePrimitive') {
        if (targetNode.type === 'simpleLLMCall' && targetHandle === 'structure') return true;
        if (targetNode.type === 'multimodalLLMCall' && targetHandle === 'structure') return true;
        if (targetNode.type === 'stop') {
            const out = stopPrimaryOutput(targetNode);
            return out.type === 'structure' && targetHandle === out.key;
        }
        return false;
    }
    if (targetNode.type === 'simpleLLMCall' && targetHandle === 'structure') {
        return sourceNode.type === 'structurePrimitive';
    }
    if (targetNode.type === 'multimodalLLMCall' && targetHandle === 'structure') {
        return sourceNode.type === 'structurePrimitive';
    }
    if (sourceNode.type === 'captureUrlSnapshot' && targetNode.type === 'imagePrimitive' && targetHandle === 'image') {
        return true;
    }
    if (sourceNode.type === 'imagePrimitive' && targetNode.type === 'multimodalLLMCall' && targetHandle === 'images') {
        return true;
    }
    if (sourceNode.type === 'documentPrimitive') {
        if (targetNode.type === 'readDocumentProperty' && targetHandle === 'document') return true;
        if (targetNode.type === 'parseDocumentBody' && targetHandle === 'document') return true;
        if (targetNode.type === 'appendValueToDocument' && targetHandle === 'document') return true;
        if (targetNode.type !== 'stop') {
            if (documentSourceAllowsNonStopTarget(targetNode, targetHandle)) return true;
            return false;
        }
    }
    if (sourceNode.type === 'loadDocument' || sourceNode.type === 'upsertDocument') {
        if (targetNode.type === 'readDocumentProperty' && targetHandle === 'document') return true;
        if (targetNode.type === 'parseDocumentBody' && targetHandle === 'document') return true;
        if (targetNode.type === 'appendValueToDocument' && targetHandle === 'document') return true;
        if (targetNode.type !== 'stop') {
            if (documentSourceAllowsNonStopTarget(targetNode, targetHandle)) return true;
            return false;
        }
    }
    if (targetNode.type === 'readDocumentProperty' && targetHandle === 'document') {
        return sourceNode.type === 'documentPrimitive' || sourceNode.type === 'loadDocument' || sourceNode.type === 'upsertDocument';
    }
    if (targetNode.type === 'parseDocumentBody' && targetHandle === 'document') {
        return sourceNode.type === 'documentPrimitive' || sourceNode.type === 'loadDocument' || sourceNode.type === 'upsertDocument';
    }
    if (targetNode.type === 'appendValueToDocument' && targetHandle === 'document') {
        return sourceNode.type === 'documentPrimitive' || sourceNode.type === 'loadDocument' || sourceNode.type === 'upsertDocument';
    }
    if (targetNode.type === 'stop') {
        const out = stopPrimaryOutput(targetNode);
        if (targetHandle !== out.key) return false;
        const expectedType = out.type;
        if (
            expectedType === 'document' ||
            expectedType === 'gmail' ||
            expectedType === 'structure' ||
            expectedType === 'audio'
        ) {
            const sourceType = getSourceOutputType(nodes, connection.source ?? '', sourceHandle ?? undefined, edges);
            if (expectedType === 'document') return sourceType === 'document';
            if (expectedType === 'audio') return sourceType === 'audio';
            return sourceType === 'structure';
        }
    }
    return true;
}
