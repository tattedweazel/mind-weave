/**
 * Shared node/edge enrichment for React Flow (palette colors, handle state, Explorer ring from `node.selected`).
 * Used by WorkflowEditor and read-only run replay.
 */
import type { CSSProperties } from 'react';
import { MarkerType, type Edge, type Node } from '@xyflow/react';
import type {
    RequiredInput,
    RequiredOutput,
    WorkflowDefinition,
    WorkflowDefinitionListItemHydrated,
} from '../../api/types';
import { resolveWorkflowPaletteColor } from '../../domain/paletteDefaults';
import { getSourceOutputType, normalizeUpsertDocumentRequiredInputs } from './graphConverters';
import { hasInputValue } from './nodeTypes';
import { canonicalStopFromGraph } from './workflowStopCanonical';
import { mergeCanvasSelectionIntoNodeData, flowEdgeSelectionClassName } from './workflowCanvasSelection';

export function enrichNodesForCanvasFlow(
    nodes: Node[],
    edges: Edge[],
    paletteColors: Record<string, string>,
    workflows: WorkflowDefinitionListItemHydrated[],
    structures: { id: string; name: string }[],
    documents: { id: string; name: string }[],
): Node[] {
    return nodes
        .map(n => {
            const baseData = { ...(n.data as object), paletteColors };
            if (n.type === 'textToSpeech') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const textVal = req.find((r: { key?: string }) => r?.key === 'text')?.value;
                const hasIncomingText = edges.some(e => e.target === n.id && e.targetHandle === 'text');
                const textHasValue = hasIncomingText || (textVal != null && String(textVal).trim() !== '');
                return { ...n, data: { ...baseData, textHasValue } };
            }
            if (n.type === 'simpleLLMCall') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const userVal = req.find((r: { key?: string }) => r?.key === 'user_prompt')?.value;
                const addlVal = d?.additional_system_prompt_context;
                const hasIncomingAddl = edges.some(
                    e => e.target === n.id && (e.targetHandle === 'additional_context' || e.targetHandle === 'system_prompt'),
                );
                const hasIncomingUser = edges.some(e => e.target === n.id && e.targetHandle === 'user_prompt');
                const hasIncomingStructure = edges.some(e => e.target === n.id && e.targetHandle === 'structure');
                const structureId = d?.structure_id;
                const structureHasValue = hasIncomingStructure || (structureId != null && structureId !== '');
                const additionalContextHasValue = hasIncomingAddl || (addlVal != null && String(addlVal).trim() !== '');
                const userPromptHasValue = hasIncomingUser || (userVal != null && userVal !== '');
                return { ...n, data: { ...baseData, additionalContextHasValue, userPromptHasValue, structureHasValue } };
            }
            if (n.type === 'multimodalLLMCall') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const userVal = req.find((r: { key?: string }) => r?.key === 'user_prompt')?.value;
                const imagesVal = req.find((r: { key?: string }) => r?.key === 'images')?.value;
                const addlVal = d?.additional_system_prompt_context;
                const hasIncomingAddl = edges.some(
                    e => e.target === n.id && (e.targetHandle === 'additional_context' || e.targetHandle === 'system_prompt'),
                );
                const hasIncomingUser = edges.some(e => e.target === n.id && e.targetHandle === 'user_prompt');
                const hasIncomingImages = edges.some(e => e.target === n.id && e.targetHandle === 'images');
                const hasIncomingStructure = edges.some(e => e.target === n.id && e.targetHandle === 'structure');
                const structureId = d?.structure_id;
                const structureHasValue = hasIncomingStructure || (structureId != null && structureId !== '');
                const additionalContextHasValue = hasIncomingAddl || (addlVal != null && String(addlVal).trim() !== '');
                const userPromptHasValue = hasIncomingUser || (userVal != null && userVal !== '');
                const imagesHasValue =
                    hasIncomingImages ||
                    (Array.isArray(imagesVal) && imagesVal.length > 0) ||
                    (imagesVal != null && typeof imagesVal === 'object' && !Array.isArray(imagesVal));
                return {
                    ...n,
                    data: { ...baseData, additionalContextHasValue, userPromptHasValue, structureHasValue, imagesHasValue },
                };
            }
            if (n.type === 'gmailListMessages') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const afterVal = req.find((r: { key?: string }) => r?.key === 'after')?.value;
                const beforeVal = req.find((r: { key?: string }) => r?.key === 'before')?.value;
                const unreadVal = req.find((r: { key?: string }) => r?.key === 'unread_only')?.value;
                const qVal = req.find((r: { key?: string }) => r?.key === 'query')?.value;
                const mVal = req.find((r: { key?: string }) => r?.key === 'max_results')?.value;
                const hasAIn = edges.some(e => e.target === n.id && e.targetHandle === 'after');
                const hasBIn = edges.some(e => e.target === n.id && e.targetHandle === 'before');
                const hasUIn = edges.some(e => e.target === n.id && e.targetHandle === 'unread_only');
                const hasQIn = edges.some(e => e.target === n.id && e.targetHandle === 'query');
                const hasMIn = edges.some(e => e.target === n.id && e.targetHandle === 'max_results');
                const afterHasValue =
                    hasAIn || (afterVal != null && String(afterVal).trim() !== '') || (d?.after != null && String(d.after).trim() !== '');
                const beforeHasValue =
                    hasBIn || (beforeVal != null && String(beforeVal).trim() !== '') || (d?.before != null && String(d.before).trim() !== '');
                const unreadOnlyHasValue = hasUIn || unreadVal === true || d?.unread_only === true;
                const queryHasValue =
                    hasQIn ||
                    (qVal != null && String(qVal).trim() !== '') ||
                    (d?.query != null && String(d.query).trim() !== '');
                const maxResultsHasValue =
                    hasMIn || (mVal != null && mVal !== '' && !(typeof mVal === 'number' && mVal === 0));
                return {
                    ...n,
                    data: {
                        ...baseData,
                        afterHasValue,
                        beforeHasValue,
                        unreadOnlyHasValue,
                        queryHasValue,
                        maxResultsHasValue,
                    },
                };
            }
            if (n.type === 'calendarListEvents') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const aVal = req.find((r: { key?: string }) => r?.key === 'time_min')?.value;
                const bVal = req.find((r: { key?: string }) => r?.key === 'time_max')?.value;
                const hasAIn = edges.some(e => e.target === n.id && e.targetHandle === 'time_min');
                const hasBIn = edges.some(e => e.target === n.id && e.targetHandle === 'time_max');
                const timeMinHasValue = hasAIn || (aVal != null && String(aVal).trim() !== '');
                const timeMaxHasValue = hasBIn || (bVal != null && String(bVal).trim() !== '');
                return { ...n, data: { ...baseData, timeMinHasValue, timeMaxHasValue } };
            }
            if (n.type === 'googleDocsGetDocument') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const uVal = req.find((r: { key?: string }) => r?.key === 'document_url_or_id')?.value;
                const hasIn = edges.some(e => e.target === n.id && e.targetHandle === 'document_url_or_id');
                const documentUrlOrIdHasValue =
                    hasIn ||
                    (uVal != null && String(uVal).trim() !== '') ||
                    (d?.document_url_or_id != null && String(d.document_url_or_id).trim() !== '');
                return { ...n, data: { ...baseData, documentUrlOrIdHasValue } };
            }
            if (n.type === 'googleDocsParseDocument') {
                const hasIn = edges.some(e => e.target === n.id && e.targetHandle === 'document');
                return { ...n, data: { ...baseData, documentHasValue: hasIn } };
            }
            if (n.type === 'fetchUrl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const uVal = req.find((r: { key?: string }) => r?.key === 'url')?.value;
                const hasUIn = edges.some(e => e.target === n.id && e.targetHandle === 'url');
                const staticUrl = d?.url != null && String(d.url).trim() !== '';
                const urlHasValue = hasUIn || staticUrl || (uVal != null && String(uVal).trim() !== '');
                return { ...n, data: { ...baseData, urlHasValue } };
            }
            if (n.type === 'captureUrlSnapshot') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const uVal = req.find((r: { key?: string }) => r?.key === 'url')?.value;
                const hasUIn = edges.some(e => e.target === n.id && e.targetHandle === 'url');
                const staticUrl = d?.url != null && String(d.url).trim() !== '';
                const urlHasValue = hasUIn || staticUrl || (uVal != null && String(uVal).trim() !== '');
                return { ...n, data: { ...baseData, urlHasValue } };
            }
            if (n.type === 'structurePrimitive') {
                const d = n.data as any;
                const structId = d?.structure_id;
                const s = structures.find(st => st.id === structId);
                return { ...n, data: { ...baseData, structureName: s?.name ?? d?.label ?? 'Structure' } };
            }
            if (n.type === 'documentPrimitive') {
                const d = n.data as any;
                const docId = d?.document_id;
                const doc = documents.find(x => x.id === docId);
                return { ...n, data: { ...baseData, documentName: doc?.name ?? d?.label ?? 'Document' } };
            }
            if (n.type === 'imagePrimitive') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const iv = req.find((r: { key?: string }) => r?.key === 'image')?.value;
                const hasIn = edges.some(e => e.target === n.id && e.targetHandle === 'image');
                const aid = d?.artifact_id;
                const hasStatic = typeof aid === 'string' && aid.trim() !== '';
                const inputHasValue =
                    hasIn ||
                    (iv != null && (typeof iv === 'object' ? Object.keys(iv as object).length > 0 : String(iv).trim() !== '')) ||
                    hasStatic;
                return { ...n, data: { ...baseData, inputHasValue } };
            }
            if (n.type === 'gmailPrimitive') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const gVal = req.find((r: { key?: string }) => r?.key === 'gmail')?.value;
                const hasGIn = edges.some(e => e.target === n.id && e.targetHandle === 'gmail');
                const msg = d?.message;
                const hasMsg =
                    msg != null &&
                    typeof msg === 'object' &&
                    !Array.isArray(msg) &&
                    Object.keys(msg as object).length > 0;
                const inputHasValue =
                    hasGIn ||
                    (gVal != null &&
                        typeof gVal === 'object' &&
                        !Array.isArray(gVal) &&
                        Object.keys(gVal as object).length > 0) ||
                    hasMsg;
                return { ...n, data: { ...baseData, inputHasValue } };
            }
            if (n.type === 'start') {
                const d = n.data as any;
                const rawInputs = d?.required_inputs;
                const displayInputs = rawInputs === undefined
                    ? [{ key: 'user_input', type: 'string' as const, value: d?.text ?? null }]
                    : rawInputs;
                const inputsForHandles = displayInputs.length === 0
                    ? [{ key: 'output', type: 'string' as const, value: '' }]
                    : displayInputs;
                const outputsHaveValue = inputsForHandles.map((inp: RequiredInput) => hasInputValue(inp));
                return { ...n, data: { ...baseData, outputsHaveValue } };
            }
            if (n.type === 'workflowRef') {
                const d = n.data as any;
                const wfId = d?.workflow_id;
                const refWf = workflows.find(w => w.id === wfId);
                const graphNodes = refWf?.graph?.nodes as
                    | { kind?: string; data?: { required_inputs?: RequiredInput[]; required_outputs?: RequiredOutput[] } }[]
                    | undefined;
                const startNode = graphNodes?.find((nd: { kind?: string }) => nd?.kind === 'start');
                const stopNode = canonicalStopFromGraph(refWf?.graph as WorkflowDefinition['graph'] | undefined);
                const rawInputs = startNode?.data?.required_inputs;
                const rawOutputs = stopNode?.data?.required_outputs;
                const subWorkflowRequiredInputs: RequiredInput[] = (() => {
                    if (!startNode) {
                        return [{ key: 'user_input', type: 'string' as const, value: null }];
                    }
                    if (rawInputs === undefined) {
                        return [{ key: 'user_input', type: 'string' as const, value: null }];
                    }
                    if (Array.isArray(rawInputs) && rawInputs.length === 0) {
                        return [{ key: 'output', type: 'string' as const, value: '' }];
                    }
                    return rawInputs;
                })();
                const subWorkflowRequiredOutputs =
                    Array.isArray(rawOutputs) && rawOutputs.length > 0
                        ? rawOutputs
                        : [{ key: 'output', type: 'string' as const }];
                const stepTypeLabel = refWf?.expose_as_custom_skill ? 'Custom Skill' : 'Workflow';
                return {
                    ...n,
                    data: {
                        ...baseData,
                        label: d?.label ?? refWf?.name ?? 'Workflow',
                        stepTypeLabel,
                        subWorkflowRequiredInputs,
                        subWorkflowRequiredOutputs,
                    },
                };
            }
            if (
                n.type === 'stringPrimitive' ||
                n.type === 'sandboxTickPrimitive' ||
                n.type === 'listPrimitive' ||
                n.type === 'dictionaryPrimitive' ||
                n.type === 'listToString' ||
                n.type === 'stringToList' ||
                n.type === 'intToString'
            ) {
                const inputHasValue = edges.some(e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null));
                return { ...n, data: { ...baseData, inputHasValue } };
            }
            if (n.type === 'booleanPrimitive') {
                const d = n.data as any;
                const valueHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null)) ||
                    (d?.value != null && typeof d?.value === 'boolean');
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            if (n.type === 'intPrimitive') {
                const d = n.data as any;
                const valueHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null)) ||
                    (d?.value != null && typeof d?.value === 'number');
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            if (n.type === 'dateTimePrimitive') {
                const d = n.data as any;
                const iso = d?.iso;
                const useNow = Boolean(d?.use_now ?? d?.useNow);
                const valueHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null)) ||
                    (typeof iso === 'string' && iso.trim() !== '') ||
                    useNow;
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            if (n.type === 'lenFromList' || n.type === 'randomItemFromList') {
                const listHasValue = edges.some(e => e.target === n.id && e.targetHandle === 'list');
                return { ...n, data: { ...baseData, listHasValue } };
            }
            if (n.type === 'forLoopControl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const listVal = req.find((r: { key?: string }) => r?.key === 'input')?.value;
                const inputHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null)) ||
                    (Array.isArray(listVal) && listVal.length > 0);
                return { ...n, data: { ...baseData, inputHasValue } };
            }
            if (n.type === 'tryCatchControl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [{ key: 'value', type: 'any', value: null }];
                const v = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const valueHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'value' || e.targetHandle == null)) ||
                    !(v === null || v === undefined || v === '');
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            if (n.type === 'listItemByIndex') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const indexVal = req.find((r: { key?: string }) => r?.key === 'index')?.value;
                const listVal = req.find((r: { key?: string }) => r?.key === 'list')?.value;
                const indexHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'index') || (indexVal != null && typeof indexVal === 'number');
                const listHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'list') || (listVal != null && Array.isArray(listVal));
                return { ...n, data: { ...baseData, indexHasValue, listHasValue } };
            }
            if (
                n.type === 'sandboxGetPosition' ||
                n.type === 'sandboxGetFacing' ||
                n.type === 'sandboxGetNearby' ||
                n.type === 'sandboxGetInventory' ||
                n.type === 'sandboxGetCellItems' ||
                n.type === 'sandboxPromptUserAction'
            ) {
                const tickHasValue = edges.some(
                    e => e.target === n.id && (e.targetHandle === 'input' || e.targetHandle == null),
                );
                const dataKey = n.type === 'sandboxGetCellItems' ? 'fixtureHasValue' : 'tickHasValue';
                return { ...n, data: { ...baseData, [dataKey]: tickHasValue } };
            }
            if (n.type === 'sandboxRemoveItemAtCell') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const itemId = req.find((r: { key?: string }) => r?.key === 'item_id')?.value;
                const itemIdHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'item_id') ||
                    (itemId != null && String(itemId).trim() !== '');
                return { ...n, data: { ...baseData, itemIdHasValue } };
            }
            if (n.type === 'sandboxSpawnItemAtCell') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const defId = req.find((r: { key?: string }) => r?.key === 'definition_id')?.value;
                const target = req.find((r: { key?: string }) => r?.key === 'target')?.value;
                const energy = req.find((r: { key?: string }) => r?.key === 'energy')?.value;
                const color = req.find((r: { key?: string }) => r?.key === 'color')?.value;
                const definitionIdHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'definition_id') ||
                    (defId != null && String(defId).trim() !== '');
                const targetHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'target') ||
                    (target != null && String(target).trim() !== '');
                const energyHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'energy') ||
                    (energy != null && typeof energy === 'number');
                const colorHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'color') ||
                    (color != null && String(color).trim() !== '');
                return {
                    ...n,
                    data: { ...baseData, definitionIdHasValue, targetHasValue, energyHasValue, colorHasValue },
                };
            }
            if (
                n.type === 'sandboxMoveForward' ||
                n.type === 'sandboxTurnLeft' ||
                n.type === 'sandboxTurnRight' ||
                n.type === 'sandboxIdle' ||
                n.type === 'sandboxPickUpItem'
            ) {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const rsn = req.find((r: { key?: string }) => r?.key === 'reason')?.value;
                const reasonHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'reason') ||
                    (rsn != null && String(rsn).trim() !== '');
                return { ...n, data: { ...baseData, reasonHasValue } };
            }
            if (n.type === 'sandboxPlaceItem') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const rsn = req.find((r: { key?: string }) => r?.key === 'reason')?.value;
                const it = req.find((r: { key?: string }) => r?.key === 'item_type')?.value;
                const reasonHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'reason') ||
                    (rsn != null && String(rsn).trim() !== '');
                const itemTypeHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'item_type') ||
                    (it != null && String(it).trim() !== '');
                return { ...n, data: { ...baseData, reasonHasValue, itemTypeHasValue } };
            }
            if (n.type === 'dictionaryValueByKey') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const keyVal = req.find((r: { key?: string }) => r?.key === 'key')?.value;
                const dictVal = req.find((r: { key?: string }) => r?.key === 'dictionary')?.value;
                const fbIn = req.find((r: { key?: string }) => r?.key === 'fallback')?.value;
                const keyHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'key') ||
                    (keyVal != null && String(keyVal).trim() !== '');
                const dictionaryHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'dictionary') ||
                    (dictVal != null && typeof dictVal === 'object' && !Array.isArray(dictVal));
                const hasStaticFallback = Object.prototype.hasOwnProperty.call(d, 'fallback_value');
                const fallbackHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'fallback') ||
                    hasStaticFallback ||
                    (fbIn !== null && fbIn !== undefined);
                return { ...n, data: { ...baseData, keyHasValue, dictionaryHasValue, fallbackHasValue } };
            }
            if (n.type === 'dictionarySetValueByKey') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const keyVal = req.find((r: { key?: string }) => r?.key === 'key')?.value;
                const dictVal = req.find((r: { key?: string }) => r?.key === 'dictionary')?.value;
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const keyHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'key') ||
                    (keyVal != null && String(keyVal).trim() !== '');
                const dictionaryHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'dictionary') ||
                    (dictVal != null && typeof dictVal === 'object' && !Array.isArray(dictVal));
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal !== null && valueVal !== undefined);
                return { ...n, data: { ...baseData, keyHasValue, dictionaryHasValue, valueHasValue } };
            }
            if (n.type === 'readDocumentProperty') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const tpVal = req.find((r: { key?: string }) => r?.key === 'target_property')?.value;
                const docVal = req.find((r: { key?: string }) => r?.key === 'document')?.value;
                const targetPropertyHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'target_property') ||
                    (tpVal != null && String(tpVal).trim() !== '');
                const documentHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'document') ||
                    (docVal != null && typeof docVal === 'object' && !Array.isArray(docVal));
                return { ...n, data: { ...baseData, targetPropertyHasValue, documentHasValue } };
            }
            if (n.type === 'loadDocument') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const idVal = req.find((r: { key?: string }) => r?.key === 'document_id')?.value;
                const nameVal = req.find((r: { key?: string }) => r?.key === 'document_name')?.value;
                const documentIdHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'document_id') ||
                    (idVal != null && String(idVal).trim() !== '');
                const documentNameHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'document_name') ||
                    (nameVal != null && String(nameVal).trim() !== '');
                return { ...n, data: { ...baseData, documentIdHasValue, documentNameHasValue } };
            }
            if (n.type === 'upsertDocument') {
                const d = n.data as any;
                const req = normalizeUpsertDocumentRequiredInputs(d?.required_inputs ?? null);
                const upsertInputHasValue: Record<string, boolean> = {};
                for (const ri of req) {
                    const key = String(ri?.key ?? '');
                    if (!key) continue;
                    const wired = edges.some(e => e.target === n.id && e.targetHandle === key);
                    const v = (ri as RequiredInput)?.value;
                    const inlineFilled = v != null && String(v).trim() !== '';
                    upsertInputHasValue[key] = wired || inlineFilled;
                }
                return { ...n, data: { ...baseData, upsertInputHasValue } };
            }
            if (n.type === 'parseDocumentBody') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const docVal = req.find((r: { key?: string }) => r?.key === 'document')?.value;
                const documentHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'document') ||
                    (docVal != null && typeof docVal === 'object' && !Array.isArray(docVal));
                return { ...n, data: { ...baseData, documentHasValue } };
            }
            if (n.type === 'htmlParseBasic') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const htmlVal = req.find((r: { key?: string }) => r?.key === 'html')?.value;
                const htmlHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'html') ||
                    (htmlVal != null && String(htmlVal).trim() !== '');
                return { ...n, data: { ...baseData, htmlHasValue } };
            }
            if (n.type === 'writeObjectToDocumentBody') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal !== null && valueVal !== undefined);
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            if (n.type === 'appendValueToDocument') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const docVal = req.find((r: { key?: string }) => r?.key === 'document')?.value;
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const documentHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'document') ||
                    (docVal != null && typeof docVal === 'object' && !Array.isArray(docVal));
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal !== null && valueVal !== undefined);
                return { ...n, data: { ...baseData, documentHasValue, valueHasValue } };
            }
            if (n.type === 'validateAgainstStructure') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const structureVal = req.find((r: { key?: string }) => r?.key === 'structure')?.value;
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal !== null && valueVal !== undefined);
                const structureHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'structure') ||
                    (structureVal != null && typeof structureVal === 'object' && !Array.isArray(structureVal));
                return { ...n, data: { ...baseData, valueHasValue, structureHasValue } };
            }
            if (n.type === 'addToList') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const listVal = req.find((r: { key?: string }) => r?.key === 'list')?.value;
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const listHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'list') ||
                    (listVal != null && Array.isArray(listVal));
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal !== null && valueVal !== undefined);
                return { ...n, data: { ...baseData, listHasValue, valueHasValue } };
            }
            if (n.type === 'prependText') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const targetVal = req.find((r: { key?: string }) => r?.key === 'target_string')?.value;
                const prependVal = req.find((r: { key?: string }) => r?.key === 'text_to_prepend')?.value;
                const targetStringHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'target_string') ||
                    (targetVal != null && String(targetVal).trim() !== '');
                const textToPrependHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'text_to_prepend') ||
                    (prependVal != null && String(prependVal).trim() !== '');
                return { ...n, data: { ...baseData, targetStringHasValue, textToPrependHasValue } };
            }
            if (n.type === 'stringTrunc') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const targetVal = req.find((r: { key?: string }) => r?.key === 'target_string')?.value;
                const startVal = req.find((r: { key?: string }) => r?.key === 'start_index')?.value;
                const endVal = req.find((r: { key?: string }) => r?.key === 'end_index')?.value;
                const targetStringHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'target_string') ||
                    (targetVal != null && String(targetVal).trim() !== '');
                const startIndexHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'start_index') ||
                    (typeof startVal === 'number' && !Number.isNaN(startVal));
                const endIndexHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'end_index') ||
                    (typeof endVal === 'number' && !Number.isNaN(endVal));
                return {
                    ...n,
                    data: { ...baseData, targetStringHasValue, startIndexHasValue, endIndexHasValue },
                };
            }
            if (n.type === 'broadcastMessage' || n.type === 'messageUtility') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const messageVal = req.find((r: { key?: string }) => r?.key === 'message')?.value;
                const titleVal = req.find((r: { key?: string }) => r?.key === 'title')?.value;
                const messageHasValue =
                    edges.some(e => e.target === n.id && (e.targetHandle === 'message' || e.targetHandle == null)) ||
                    messageVal != null;
                const titleHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'title') ||
                    (titleVal != null && String(titleVal).trim() !== '');
                return { ...n, data: { ...baseData, messageHasValue, titleHasValue } };
            }
            if (n.type === 'basicConditional') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const conditionVal = req.find((r: { key?: string }) => r?.key === 'condition')?.value ?? d?.condition;
                const conditionHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'condition') ||
                    (conditionVal != null && (typeof conditionVal === 'boolean' || String(conditionVal).trim() !== ''));
                return { ...n, data: { ...baseData, conditionHasValue } };
            }
            if (n.type === 'addDays') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const inputVal = req.find((r: { key?: string }) => r?.key === 'input')?.value;
                const daysVal = req.find((r: { key?: string }) => r?.key === 'days')?.value;
                const inputHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input') ||
                    (typeof inputVal === 'string' && inputVal.trim() !== '');
                const daysHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'days') ||
                    (daysVal != null && typeof daysVal === 'number');
                return { ...n, data: { ...baseData, inputHasValue, daysHasValue } };
            }
            const binaryIntUtilityTypes = [
                'addInts',
                'subtractInts',
                'multiplyInts',
                'divideInts',
                'moduloInts',
                'minInts',
                'maxInts',
            ];
            if (binaryIntUtilityTypes.includes(n.type ?? '')) {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const inputAVal = req.find((r: { key?: string }) => r?.key === 'input_a')?.value;
                const inputBVal = req.find((r: { key?: string }) => r?.key === 'input_b')?.value;
                const inputAHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input_a') ||
                    (inputAVal != null && typeof inputAVal === 'number');
                const inputBHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input_b') ||
                    (inputBVal != null && typeof inputBVal === 'number');
                return { ...n, data: { ...baseData, inputAHasValue, inputBHasValue } };
            }
            if (n.type === 'notControl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const inputVal = req.find((r: { key?: string }) => r?.key === 'input')?.value;
                const inputHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input') ||
                    (inputVal != null && (typeof inputVal === 'boolean' || String(inputVal).trim() !== ''));
                return { ...n, data: { ...baseData, inputHasValue } };
            }
            if (n.type === 'betweenControl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const lowVal = req.find((r: { key?: string }) => r?.key === 'low')?.value;
                const valueVal = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const highVal = req.find((r: { key?: string }) => r?.key === 'high')?.value;
                const lowHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'low') ||
                    (lowVal != null && typeof lowVal === 'number');
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (valueVal != null && typeof valueVal === 'number');
                const highHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'high') ||
                    (highVal != null && typeof highVal === 'number');
                return { ...n, data: { ...baseData, lowHasValue, valueHasValue, highHasValue } };
            }
            if (n.type === 'isEmptyControl') {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const v = req.find((r: { key?: string }) => r?.key === 'value')?.value;
                const valueHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'value') ||
                    (v != null && (Array.isArray(v) || (typeof v === 'object' && v !== null)));
                return { ...n, data: { ...baseData, valueHasValue } };
            }
            const twoInputControls = ['isControl', 'gtControl', 'ltControl', 'gteControl', 'lteControl', 'andControl', 'orControl', 'xorControl'];
            if (twoInputControls.includes(n.type ?? '')) {
                const d = n.data as any;
                const req = d?.required_inputs ?? [];
                const inputAVal = req.find((r: { key?: string }) => r?.key === 'input_a')?.value;
                const inputBVal = req.find((r: { key?: string }) => r?.key === 'input_b')?.value;
                const inputAHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input_a') || (inputAVal != null && String(inputAVal).trim() !== '');
                const inputBHasValue =
                    edges.some(e => e.target === n.id && e.targetHandle === 'input_b') || (inputBVal != null && String(inputBVal).trim() !== '');
                return { ...n, data: { ...baseData, inputAHasValue, inputBHasValue } };
            }
            return { ...n, data: baseData };
        })
        .map(n => ({
            ...n,
            data: mergeCanvasSelectionIntoNodeData(n.data as Record<string, unknown>, Boolean(n.selected)),
        }));
}

export function styleEdgesForCanvas(
    edges: Edge[],
    nodesForFlow: Node[],
    paletteColors: Record<string, string>,
    selectedEdgeId: string | null,
): Edge[] {
    return edges.map(e => {
        const type = getSourceOutputType(nodesForFlow, e.source, e.sourceHandle ?? undefined, edges);
        const color = resolveWorkflowPaletteColor(paletteColors, type);
        const selected = selectedEdgeId === e.id;
        const className = flowEdgeSelectionClassName(e.className, e.id, selectedEdgeId);
        const baseStyle: CSSProperties = {
            strokeWidth: selected ? 4 : 3,
            stroke: color,
            ...(selected ? { ['--mw-edge-glow' as string]: color } : {}),
        };
        return {
            ...e,
            className,
            style: baseStyle,
            markerEnd: { type: MarkerType.ArrowClosed, color },
        };
    });
}
