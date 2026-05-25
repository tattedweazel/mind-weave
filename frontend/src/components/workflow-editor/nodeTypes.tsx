import React, { useLayoutEffect, useMemo } from 'react';
import { Handle, NodeResizer, Position, useNodeId, useReactFlow, useUpdateNodeInternals, type NodeProps } from '@xyflow/react';
import { useRecordGraphBeforeMutation, useWorkflowGraphUndo } from './workflowGraphUndoContext';
import { resolveWorkflowPaletteColor } from '../../domain/paletteDefaults';
import type { RequiredInput, RequiredOutput } from '../../api/types';
import { normalizeAnnotationTextAlign } from './annotationTextAlign';
import {
    HANDLE_INSET,
    INPUT_LABEL_OFFSET,
    OUTPUT_LABEL_OFFSET,
    STRIP_TO_CONTENT_GAP,
    LABEL_STRIP_WIDTH,
    STOP_LABEL_STRIP_WIDTH,
    NODE_MIN_HEIGHT,
    NODE_MIN_WIDTH,
    NODE_STRIP_PADDING_Y,
    NODE_OUTPUT_STRIP_EXTRA_BOTTOM_PX,
    NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX,
    getNodeMinHeight,
    SIMPLE_LLM_HANDLES,
    MULTIMODAL_LLM_HANDLES,
    PREPEND_TEXT_HANDLES,
    STRING_TRUNC_HANDLES,
    GMAIL_LIST_MESSAGES_HANDLES,
    TEXT_TO_SPEECH_HANDLES,
    CALENDAR_LIST_EVENTS_HANDLES,
    CAPTURE_URL_SNAPSHOT_HANDLES,
    FETCH_URL_HANDLES,
    getHandleColor,
} from './constants';
import { normalizeUpsertDocumentRequiredInputs } from './graphConverters';
import { DEFAULT_FOR_LOOP_END_EXPORTS } from './forLoopEndPairing';

function resolveAnnotationAccent(
    paletteColors: Record<string, string> | undefined,
    dataColor: string | null | undefined,
    paletteKey: string,
): string {
    const pal = paletteColors ?? {};
    if (dataColor && typeof dataColor === 'string') {
        const t = dataColor.trim();
        if (t.startsWith('#')) return t;
        if (t !== '') return resolveWorkflowPaletteColor(pal, t);
    }
    return resolveWorkflowPaletteColor(pal, paletteKey);
}

const NOTE_CONTENT_FONT_MIN = 8;
const NOTE_CONTENT_FONT_MAX = 32;
const NOTE_CONTENT_FONT_DEFAULT = 12;

function clampNoteContentFontSizePx(raw: unknown): number {
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return NOTE_CONTENT_FONT_DEFAULT;
    return Math.min(NOTE_CONTENT_FONT_MAX, Math.max(NOTE_CONTENT_FONT_MIN, Math.round(raw)));
}

const NOTE_LABEL_FONT_MIN = 8;
const NOTE_LABEL_FONT_MAX = 32;
/** Matches the previous `text-[10px]` chrome. */
const NOTE_LABEL_FONT_DEFAULT = 10;

function clampNoteLabelFontSizePx(raw: unknown): number {
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return NOTE_LABEL_FONT_DEFAULT;
    return Math.min(NOTE_LABEL_FONT_MAX, Math.max(NOTE_LABEL_FONT_MIN, Math.round(raw)));
}

const AnnotationNoteNodeComp: React.FC<NodeProps> = ({ id, data, selected }) => {
    const d = data as {
        label?: string;
        text?: string;
        color?: string | null;
        label_font_size_px?: number;
        content_font_size_px?: number;
        label_align?: string;
        content_align?: string;
        width?: number;
        height?: number;
        paletteColors?: Record<string, string>;
        isCanvasSelected?: boolean;
    };
    const { setNodes } = useReactFlow();
    const recordGraphUndo = useRecordGraphBeforeMutation();
    const graphUndo = useWorkflowGraphUndo();
    const borderColor = resolveAnnotationAccent(d.paletteColors, d.color, 'annotation_note');
    const labelFontPx = clampNoteLabelFontSizePx(d.label_font_size_px);
    const contentFontPx = clampNoteContentFontSizePx(d.content_font_size_px);
    const labelAlign = normalizeAnnotationTextAlign(d.label_align);
    const contentAlign = normalizeAnnotationTextAlign(d.content_align);
    const labelAlignClass =
        labelAlign === 'center' ? 'text-center' : labelAlign === 'right' ? 'text-right' : 'text-left';
    const selectedRing = d.isCanvasSelected ? ' ring-2 ring-violet-500 ring-offset-2 ring-offset-mw-page' : '';
    const headerLabel =
        typeof d.label === 'string' && d.label.trim() !== '' ? d.label.trim() : 'Note';

    return (
        <div
            className={`relative flex h-full w-full flex-col rounded-lg border-2 bg-mw-card/95 px-4 py-3 shadow-sm${selectedRing}`}
            style={{ borderColor }}
        >
            <NodeResizer
                minWidth={180}
                minHeight={100}
                isVisible={Boolean(selected)}
                lineClassName="!border-mw-border"
                handleClassName="!h-2.5 !w-2.5 !rounded-sm !border !border-mw-border !bg-mw-card"
                onResizeStart={() => {
                    recordGraphUndo();
                    if (graphUndo?.interactionRef) graphUndo.interactionRef.current.nodeResize = true;
                }}
                onResizeEnd={(_e, p) => {
                    if (graphUndo?.interactionRef) graphUndo.interactionRef.current.nodeResize = false;
                    const width = Math.round(p.width);
                    const height = Math.round(p.height);
                    setNodes(ns =>
                        ns.map(n =>
                            n.id === id
                                ? {
                                      ...n,
                                      style: { ...n.style, width, height },
                                      data: { ...(n.data as object), width, height },
                                  }
                                : n,
                        ),
                    );
                }}
            />
            <div
                className={`mb-2 shrink-0 font-semibold uppercase tracking-wide text-mw-text-secondary ${labelAlignClass}`}
                style={{ fontSize: labelFontPx }}
            >
                {headerLabel}
            </div>
            <textarea
                className="min-h-0 w-full flex-1 resize-none overflow-y-auto text-mw-text-primary bg-transparent outline-none placeholder:text-mw-text-secondary"
                style={{ fontSize: contentFontPx, textAlign: contentAlign }}
                value={d.text ?? ''}
                placeholder="Write a note…"
                onFocus={recordGraphUndo}
                onChange={e => {
                    const v = e.target.value;
                    setNodes(ns => ns.map(n => (n.id === id ? { ...n, data: { ...n.data, text: v } } : n)));
                }}
                spellCheck={false}
            />
        </div>
    );
};

const REGION_LABEL_FONT_MIN = 8;
const REGION_LABEL_FONT_MAX = 32;
const REGION_LABEL_FONT_DEFAULT = 11;

function clampRegionLabelFontSizePx(raw: unknown): number {
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return REGION_LABEL_FONT_DEFAULT;
    return Math.min(REGION_LABEL_FONT_MAX, Math.max(REGION_LABEL_FONT_MIN, Math.round(raw)));
}

const AnnotationRegionNodeComp: React.FC<NodeProps> = ({ id, data, selected }) => {
    const d = data as {
        label?: string;
        color?: string | null;
        width?: number;
        height?: number;
        label_font_size_px?: number;
        label_align?: string;
        paletteColors?: Record<string, string>;
        isCanvasSelected?: boolean;
    };
    const { setNodes } = useReactFlow();
    const recordGraphUndo = useRecordGraphBeforeMutation();
    const graphUndo = useWorkflowGraphUndo();
    const accent = resolveAnnotationAccent(d.paletteColors, d.color, 'annotation_region');
    const labelFontPx = clampRegionLabelFontSizePx(d.label_font_size_px);
    const labelAlign = normalizeAnnotationTextAlign(d.label_align);
    const badgePositionClass =
        labelAlign === 'center'
            ? 'left-1/2 top-2 -translate-x-1/2 text-center'
            : labelAlign === 'right'
              ? 'right-2 top-2 left-auto text-right'
              : 'left-2 top-2 text-left';
    const selectedRing = d.isCanvasSelected ? ' ring-2 ring-violet-500 ring-offset-1' : '';

    return (
        <div
            className={`relative h-full w-full rounded-lg border-2 border-dashed${selectedRing}`}
            style={{
                borderColor: accent,
                backgroundColor: `${accent}22`,
            }}
        >
            <NodeResizer
                minWidth={120}
                minHeight={96}
                isVisible={Boolean(selected)}
                lineClassName="!border-mw-border"
                handleClassName="!h-2.5 !w-2.5 !rounded-sm !border !border-mw-border !bg-mw-card"
                onResizeStart={() => {
                    recordGraphUndo();
                    if (graphUndo?.interactionRef) graphUndo.interactionRef.current.nodeResize = true;
                }}
                onResizeEnd={(_e, p) => {
                    if (graphUndo?.interactionRef) graphUndo.interactionRef.current.nodeResize = false;
                    const width = Math.round(p.width);
                    const height = Math.round(p.height);
                    setNodes(ns =>
                        ns.map(n =>
                            n.id === id
                                ? {
                                      ...n,
                                      style: { ...n.style, width, height },
                                      data: { ...(n.data as object), width, height },
                                  }
                                : n,
                        ),
                    );
                }}
            />
            <div
                className={`pointer-events-none absolute max-w-[calc(100%-1rem)] truncate rounded px-2 py-1 font-medium text-mw-text-primary ${badgePositionClass}`}
                style={{ backgroundColor: `${accent}55`, fontSize: labelFontPx }}
            >
                {d.label ?? 'Region'}
            </div>
        </div>
    );
};

interface NodeSlot {
    key: string;
    type: 'string' | 'list' | 'dictionary' | 'structure' | 'document' | 'gmail' | 'audio' | 'boolean' | 'int' | 'datetime' | 'any' | 'trigger' | 'signal';
    label?: string;
    hasValue?: boolean;
    colorOverride?: string;
}

interface StyledNodeBaseProps {
    typeLabel: string;
    nodeLabel: string;
    inputs: NodeSlot[];
    outputs: NodeSlot[];
    borderColor: string;
    nodeColor?: string;
    isRunning?: boolean;
    minWidth?: number;
    minHeight?: number;
    paletteColors?: Record<string, string>;
    labelStripWidth?: number;
    triggerInput?: boolean;
    signalOutput?: boolean;
    /** Set from WorkflowEditor when this node is selected on the canvas (Explorer target). */
    isCanvasSelected?: boolean;
    /** Forced output override active for this node (session). */
    outputOverrideActive?: boolean;
}

const StyledNodeBase: React.FC<StyledNodeBaseProps> = ({
    typeLabel,
    nodeLabel,
    inputs,
    outputs,
    borderColor,
    nodeColor: nodeColorProp,
    isRunning,
    isCanvasSelected,
    outputOverrideActive,
    minWidth = NODE_MIN_WIDTH.medium,
    minHeight: minHeightProp,
    paletteColors,
    labelStripWidth = LABEL_STRIP_WIDTH,
    triggerInput = false,
    signalOutput = false,
}) => {
    const nodeColor = nodeColorProp ?? borderColor;
    const getSlotColor = (slot: NodeSlot) =>
        slot.colorOverride ?? getHandleColor(paletteColors, slot.type);

    const triggerSlot: NodeSlot = { key: 'trigger', type: 'trigger', label: '▶' };
    const signalSlot: NodeSlot = { key: 'signal_out', type: 'signal', label: '▶' };
    const effectiveInputs = triggerInput ? [triggerSlot, ...inputs] : inputs;
    const effectiveOutputs = signalOutput ? [signalSlot, ...outputs] : outputs;

    const baseMinHeight = minHeightProp ?? getNodeMinHeight(effectiveInputs.length, effectiveOutputs.length);
    const overrideTopReservePx = outputOverrideActive ? NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX : 0;
    const minHeight = baseMinHeight + overrideTopReservePx;

    const leftStripWidth = effectiveInputs.length > 0 ? INPUT_LABEL_OFFSET + labelStripWidth + STRIP_TO_CONTENT_GAP : 0;
    const rightStripWidth = effectiveOutputs.length > 0 ? OUTPUT_LABEL_OFFSET + labelStripWidth + STRIP_TO_CONTENT_GAP : 0;

    const showSelectionGlow = Boolean(isCanvasSelected && !isRunning);

    return (
        <div
            className={`relative flex bg-mw-card border-2 rounded-xl shadow-md transition-all duration-300 ${isRunning ? 'border-mw-primary ring-2 ring-mw-primary/45 animate-pulse' : ''} ${showSelectionGlow ? 'mw-flow-node-selected' : ''}`}
            style={{
                minWidth,
                minHeight,
                ...(overrideTopReservePx > 0 ? { paddingTop: overrideTopReservePx } : undefined),
                ...(!isRunning ? { borderColor } : undefined),
                ...(showSelectionGlow
                    ? {
                        ['--mw-node-glow' as string]: borderColor,
                        ['--mw-node-glow-accent' as string]: 'color-mix(in srgb, var(--mw-primary) 55%, transparent)',
                    }
                    : undefined),
            }}
        >
            {outputOverrideActive ? (
                <span className="absolute top-1 right-1 z-10 text-[9px] font-semibold uppercase px-1 py-0.5 rounded bg-amber-500/25 text-amber-900 dark:text-amber-100 border border-amber-500/40">
                    Overridden
                </span>
            ) : null}
            {/* Left: input handle strip */}
            {effectiveInputs.length > 0 && (
                <div className="relative shrink-0 pr-0" style={{ width: leftStripWidth, paddingTop: NODE_STRIP_PADDING_Y, paddingBottom: NODE_STRIP_PADDING_Y }}>
                    {effectiveInputs.map((slot, i) => {
                        const color = getSlotColor(slot);
                        const n = effectiveInputs.length;
                        const topPct = n === 1 ? 50 : ((i + 1) / (n + 1)) * 100;
                        return (
                            <div
                                key={`in-${i}-${slot.key}`}
                                className="absolute left-0 flex items-center"
                                style={{
                                    top: `${topPct}%`,
                                    transform: 'translateY(-50%)',
                                    paddingLeft: INPUT_LABEL_OFFSET,
                                    paddingRight: STRIP_TO_CONTENT_GAP,
                                    width: '100%',
                                    zIndex: 10 + i,
                                }}
                            >
                                <Handle
                                    type="target"
                                    position={Position.Left}
                                    id={slot.key}
                                    style={{ left: HANDLE_INSET, boxShadow: `inset 0 0 0 2px ${color}`, backgroundColor: slot.hasValue ? undefined : color }}
                                    className={`w-4 h-4 shrink-0 rounded-full !border-0 ${slot.hasValue ? '!bg-mw-text-secondary' : ''}`}
                                />
                                <span
                                    className="text-[10px] truncate rounded border border-mw-border px-2 py-0.5 min-w-0 flex-1"
                                    style={{ color: nodeColor, maxWidth: labelStripWidth }}
                                >
                                    {slot.label ?? slot.key}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Center: type label + node label */}
            <div
                className="flex-1 flex flex-col justify-center items-center min-w-0 shrink"
                style={{
                    paddingLeft: effectiveInputs.length > 0 ? 4 : 12,
                    paddingRight: effectiveOutputs.length > 0 ? STRIP_TO_CONTENT_GAP : 12,
                    paddingTop: NODE_STRIP_PADDING_Y,
                    paddingBottom: NODE_STRIP_PADDING_Y,
                }}
            >
                <div className="text-xs font-semibold uppercase tracking-wide truncate max-w-full w-full text-center" style={{ color: nodeColor }}>
                    {typeLabel}
                </div>
                <div className="text-sm font-bold text-mw-text-primary truncate max-w-full w-full text-center">
                    {nodeLabel}
                </div>
            </div>

            {/* Right: output handle strip */}
            {effectiveOutputs.length > 0 && (
                <div
                    className="relative shrink-0"
                    style={{
                        width: rightStripWidth,
                        paddingTop: NODE_STRIP_PADDING_Y,
                        paddingBottom: NODE_STRIP_PADDING_Y + NODE_OUTPUT_STRIP_EXTRA_BOTTOM_PX,
                    }}
                >
                    {effectiveOutputs.map((slot, i) => {
                        const color = getSlotColor(slot);
                        const n = effectiveOutputs.length;
                        const topPct = n === 1 ? 50 : ((i + 1) / (n + 1)) * 100;
                        return (
                            <div
                                key={`out-${i}-${slot.key}`}
                                className="absolute right-0 flex items-center justify-end"
                                style={{
                                    top: `${topPct}%`,
                                    transform: 'translateY(-50%)',
                                    paddingLeft: STRIP_TO_CONTENT_GAP,
                                    paddingRight: OUTPUT_LABEL_OFFSET,
                                    zIndex: 10 + i,
                                }}
                            >
                                <span className="text-[10px] truncate rounded border border-mw-border px-2 py-0.5 min-w-[4rem]" style={{ color: nodeColor }}>
                                    {slot.label ?? slot.key ?? '\u00A0'}
                                </span>
                                <Handle
                                    type="source"
                                    position={Position.Right}
                                    id={slot.key}
                                    style={{ right: HANDLE_INSET, boxShadow: `inset 0 0 0 2px ${color}`, backgroundColor: slot.hasValue ? undefined : color }}
                                    className={`w-4 h-4 shrink-0 rounded-full !border-0 ${slot.hasValue ? '!bg-mw-text-secondary' : ''}`}
                                />
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

// ---------------------------------------------------------------------------
// Node components (use StyledNodeBase)
// ---------------------------------------------------------------------------

const GmailListMessagesNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        afterHasValue?: boolean;
        beforeHasValue?: boolean;
        unreadOnlyHasValue?: boolean;
        queryHasValue?: boolean;
        maxResultsHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const hasById: Record<string, boolean | undefined> = {
        after: data.afterHasValue,
        before: data.beforeHasValue,
        unread_only: data.unreadOnlyHasValue,
        query: data.queryHasValue,
        max_results: data.maxResultsHasValue,
    };
    const inputs: NodeSlot[] = GMAIL_LIST_MESSAGES_HANDLES.map(h => ({
        key: h.id,
        type: h.id === 'max_results' ? 'int' : h.id === 'unread_only' ? 'boolean' : 'string',
        label: h.label,
        hasValue: hasById[h.id] ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'gmail_list_messages')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.quintuple}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const GoogleDocsGetDocumentNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        documentUrlOrIdHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        {
            key: 'document_url_or_id',
            type: 'string',
            label: 'document URL or ID',
            hasValue: data.documentUrlOrIdHasValue,
        },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'google_docs_get_document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const GoogleDocsParseDocumentNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        documentHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'document', type: 'dictionary', label: 'document', hasValue: data.documentHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'google_docs_parse_document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const CalendarListEventsNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        timeMinHasValue?: boolean;
        timeMaxHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = CALENDAR_LIST_EVENTS_HANDLES.map((h, i) => ({
        key: h.id,
        type: 'string',
        label: h.label,
        hasValue: [data.timeMinHasValue, data.timeMaxHasValue][i] ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'calendar_list_events')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const FetchUrlNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        urlHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = FETCH_URL_HANDLES.map(h => ({
        key: h.id,
        type: 'string' as const,
        label: h.label,
        hasValue: data.urlHasValue ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'fetch_url')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const CaptureUrlSnapshotNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        urlHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = CAPTURE_URL_SNAPSHOT_HANDLES.map(h => ({
        key: h.id,
        type: 'string' as const,
        label: h.label,
        hasValue: data.urlHasValue ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'capture_url_snapshot')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const TextToSpeechNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        textHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = TEXT_TO_SPEECH_HANDLES.map(h => ({
        key: h.id,
        type: 'string' as const,
        label: h.label,
        hasValue: Boolean(data.textHasValue),
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'audio', label: 'audio' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'text_to_speech')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const TranscribeAudioNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'text' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'transcribe_audio')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const AudioFileInputNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'text' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'audio_file_input')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const TranscribeFileNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        outputOverrideActive?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'transcript' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'transcribe_file')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            minHeight={NODE_MIN_HEIGHT.double}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SimpleLLMCallNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; additionalContextHasValue?: boolean; userPromptHasValue?: boolean; structureHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const structureColor = getHandleColor(data.paletteColors, 'structure');
    const inputs: NodeSlot[] = SIMPLE_LLM_HANDLES.map((h, i) => ({
        key: h.id,
        type: h.id === 'structure' ? 'structure' as const : 'string' as const,
        label: h.label,
        hasValue: [data.additionalContextHasValue, data.userPromptHasValue, data.structureHasValue][i] ?? false,
        colorOverride: h.id === 'structure' ? structureColor : undefined,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'simple_llm_call')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.large}
            minHeight={NODE_MIN_HEIGHT.quad}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const MultimodalLLMCallNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        additionalContextHasValue?: boolean;
        userPromptHasValue?: boolean;
        structureHasValue?: boolean;
        imagesHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const structureColor = getHandleColor(data.paletteColors, 'structure');
    const listColor = getHandleColor(data.paletteColors, 'list');
    const inputs: NodeSlot[] = MULTIMODAL_LLM_HANDLES.map(h => {
        const typ =
            h.id === 'structure' ? ('structure' as const) : h.id === 'images' ? ('list' as const) : ('string' as const);
        let hasValue = false;
        let colorOverride: string | undefined;
        if (h.id === 'additional_context') hasValue = Boolean(data.additionalContextHasValue);
        else if (h.id === 'user_prompt') hasValue = Boolean(data.userPromptHasValue);
        else if (h.id === 'structure') {
            hasValue = Boolean(data.structureHasValue);
            colorOverride = structureColor;
        } else if (h.id === 'images') {
            hasValue = Boolean(data.imagesHasValue);
            colorOverride = listColor;
        }
        return { key: h.id, type: typ, label: h.label, hasValue, colorOverride };
    });
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Skill"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'multimodal_llm')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.large}
            minHeight={NODE_MIN_HEIGHT.quintuple}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const StringValueNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'string', label: 'value', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="String"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'string')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxTickPrimitiveNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'dictionary', label: 'override', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'sandbox_tick' }];
    return (
        <StyledNodeBase
            typeLabel="Tick input"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_tick')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxRegionPrimitiveNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'sandbox_region' }];
    return (
        <StyledNodeBase
            typeLabel="Region trigger input"
            nodeLabel={data.label}
            inputs={[]}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_region')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxTickInputUtilityNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
    paletteKey: string;
    outputType: string;
}> = ({ data, paletteKey, outputType }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'dictionary', label: 'sandbox_tick', hasValue: data.tickHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: outputType, label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, paletteKey)}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxGetPositionNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxTickInputUtilityNodeComp {...props} paletteKey="sandbox_get_position" outputType="dictionary" />;

const SandboxGetFacingNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxTickInputUtilityNodeComp {...props} paletteKey="sandbox_get_facing" outputType="string" />;

const SandboxGetNearbyNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxTickInputUtilityNodeComp {...props} paletteKey="sandbox_get_nearby" outputType="list" />;

const SandboxNavigationActionNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
    paletteKey: string;
}> = ({ data, paletteKey }) => {
    const inputs: NodeSlot[] = [{ key: 'reason', type: 'string', label: 'reason', hasValue: data.reasonHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, paletteKey)}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxPromptUserActionNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => (
    <SandboxTickInputUtilityNodeComp {...props} paletteKey="sandbox_prompt_user_action" outputType="dictionary" />
);

const SandboxForceSimulationPauseNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={[]}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_force_simulation_pause')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxGetCellItemsNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; fixtureHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'input', type: 'dictionary', label: 'sandbox_fixture', hasValue: data.fixtureHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_get_cell_items')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxRemoveItemAtCellNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; itemIdHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'item_id', type: 'string', label: 'item_id', hasValue: data.itemIdHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_remove_item_at_cell')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxSpawnItemAtCellNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        definitionIdHasValue?: boolean;
        targetHasValue?: boolean;
        energyHasValue?: boolean;
        colorHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'definition_id', type: 'string', label: 'definition_id', hasValue: data.definitionIdHasValue },
        { key: 'target', type: 'string', label: 'target', hasValue: data.targetHasValue },
        { key: 'energy', type: 'int', label: 'energy', hasValue: data.energyHasValue },
        { key: 'color', type: 'string', label: 'color', hasValue: data.colorHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_spawn_item_at_cell')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxMoveForwardNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxNavigationActionNodeComp {...props} paletteKey="sandbox_move_forward" />;

const SandboxTurnLeftNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxNavigationActionNodeComp {...props} paletteKey="sandbox_turn_left" />;

const SandboxTurnRightNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxNavigationActionNodeComp {...props} paletteKey="sandbox_turn_right" />;

const SandboxIdleNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxNavigationActionNodeComp {...props} paletteKey="sandbox_idle" />;

const SandboxPickUpItemNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; reasonHasValue?: boolean; paletteColors?: Record<string, string> };
}> = props => <SandboxNavigationActionNodeComp {...props} paletteKey="sandbox_pick_up_item" />;

const SandboxPlaceItemNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        reasonHasValue?: boolean;
        itemTypeHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'reason', type: 'string', label: 'reason', hasValue: data.reasonHasValue },
        { key: 'item_type', type: 'string', label: 'item_type', hasValue: data.itemTypeHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_place_item')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const SandboxGetInventoryNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; tickHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'dictionary', label: 'sandbox_tick', hasValue: data.tickHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'sandbox_get_inventory')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const StructureValueNodeComp: React.FC<{ data: { label: string; structureName?: string; isRunning?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const outputs: NodeSlot[] = [{ key: 'output', type: 'structure', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Structure"
            nodeLabel={data.structureName || data.label}
            inputs={[]}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'structure')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const DocumentValueNodeComp: React.FC<{ data: { label: string; documentName?: string; isRunning?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const outputs: NodeSlot[] = [{ key: 'output', type: 'document', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Document"
            nodeLabel={data.documentName || data.label}
            inputs={[]}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ImagePrimitiveNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        inputHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'image', type: 'dictionary', label: 'image', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Image"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'image')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const GmailPrimitiveNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        inputHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'gmail', type: 'gmail', label: 'gmail', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'gmail', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Gmail"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'gmail')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

export function hasInputValue(inp: RequiredInput): boolean {
    const v = inp.value;
    if (v == null) return false;
    if (inp.type === 'string') return typeof v === 'string' && v.trim() !== '';
    if (inp.type === 'list') return Array.isArray(v) && v.length > 0;
    if (inp.type === 'dictionary') return typeof v === 'object' && v !== null && !Array.isArray(v) && Object.keys(v).length > 0;
    return false;
}

export const StartNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; required_inputs?: RequiredInput[]; text?: string; outputsHaveValue?: boolean[]; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const updateNodeInternals = useUpdateNodeInternals();
    const nodeId = useNodeId();
    const rawInputs = data.required_inputs;
    const displayInputs = rawInputs === undefined
        ? [{ key: 'user_input', type: 'string' as const, value: data.text ?? null }]
        : rawInputs;
    const inputsForHandles = displayInputs.length === 0
        ? [{ key: 'output', type: 'string' as const, value: '' }]
        : displayInputs;
    const outputsHaveValue = data.outputsHaveValue ?? inputsForHandles.map(hasInputValue);
    const outputs: NodeSlot[] = inputsForHandles.map((inp, i) => ({
        key: inp.key,
        type: inp.type,
        label: inp.key || '\u00A0',
        hasValue: outputsHaveValue[i],
    }));

    const startHandlesSig = useMemo(
        () =>
            JSON.stringify({
                inputs: rawInputs ?? [],
                outputsHaveValue: data.outputsHaveValue ?? null,
            }),
        [rawInputs, data.outputsHaveValue],
    );
    useLayoutEffect(() => {
        if (nodeId != null && nodeId !== '') {
            updateNodeInternals(nodeId);
        }
    }, [nodeId, updateNodeInternals, startHandlesSig]);

    return (
        <StyledNodeBase
            typeLabel="Start"
            nodeLabel={data.label}
            inputs={[]}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'start')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            signalOutput
        />
    );
};

/** Shown when imported/LLM JSON is missing top-level step discriminators; previously mis-rendered as Stop. */
const InvalidStepNodeComp: React.FC<{
    data: {
        label: string;
        appKind?: string;
        hint?: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    return (
        <StyledNodeBase
            typeLabel="Invalid step"
            nodeLabel={data.label}
            inputs={[]}
            outputs={[]}
            borderColor="#d97706"
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const StopNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; paletteColors?: Record<string, string>; required_outputs?: RequiredOutput[] } }> = ({ data }) => {
    const outputs = data.required_outputs ?? [{ key: 'output', type: 'string' as const }];
    const out = outputs[0] ?? { key: 'output', type: 'string' as const };
    const inputs: NodeSlot[] = [{ key: out.key, type: out.type, label: out.key }];
    return (
        <StyledNodeBase
            typeLabel="Stop"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={[]}
            borderColor={getHandleColor(data.paletteColors, 'stop')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.large}
            paletteColors={data.paletteColors}
            labelStripWidth={STOP_LABEL_STRIP_WIDTH}
            triggerInput
        />
    );
};

const ListValueNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'list', label: 'items', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="List"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'list')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ListToStringNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'list', label: 'list', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="List to String"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'list_to_string')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const StringToListNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'string', label: 'text', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="String to List"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'string_to_list')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const PrependTextNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; targetStringHasValue?: boolean; textToPrependHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = PREPEND_TEXT_HANDLES.map((h, i) => ({
        key: h.id,
        type: 'string' as const,
        label: h.label,
        hasValue: [data.targetStringHasValue, data.textToPrependHasValue][i] ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output_string', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Prepend Text"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'prepend_text')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const StringTruncNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        targetStringHasValue?: boolean;
        startIndexHasValue?: boolean;
        endIndexHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = STRING_TRUNC_HANDLES.map((h, i) => ({
        key: h.id,
        type: h.type,
        label: h.label,
        hasValue: [data.targetStringHasValue, data.startIndexHasValue, data.endIndexHasValue][i] ?? false,
    }));
    const outputs: NodeSlot[] = [{ key: 'output_string', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="String Trunc"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'string_trunc')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const BroadcastMessageNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        messageHasValue?: boolean;
        titleHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'message', type: 'any', label: 'message', hasValue: data.messageHasValue },
        { key: 'title', type: 'string', label: 'title', hasValue: data.titleHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'broadcast_message')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const BasicConditionalNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; conditionHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'condition', type: 'boolean', label: 'Condition', hasValue: data.conditionHasValue }];
    const outputs: NodeSlot[] = [
        { key: 'true', type: 'boolean', label: 'True' },
        { key: 'false', type: 'boolean', label: 'False' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'basic_conditional')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const IsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'input_a', type: 'string', label: 'A', hasValue: data.inputAHasValue },
        { key: 'input_b', type: 'string', label: 'B', hasValue: data.inputBHasValue },
    ];
    const outputs: NodeSlot[] = [
        { key: 'true', type: 'boolean', label: 'True' },
        { key: 'false', type: 'boolean', label: 'False' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'is_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const IsEmptyNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; valueHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue }];
    const outputs: NodeSlot[] = [
        { key: 'true', type: 'boolean', label: 'True' },
        { key: 'false', type: 'boolean', label: 'False' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'is_empty')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ComparisonControlComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> }; paletteType: string }> = ({ data, paletteType }) => {
    const inputs: NodeSlot[] = [
        { key: 'input_a', type: 'string', label: 'A', hasValue: data.inputAHasValue },
        { key: 'input_b', type: 'string', label: 'B', hasValue: data.inputBHasValue },
    ];
    const outputs: NodeSlot[] = [
        { key: 'true', type: 'boolean', label: 'True' },
        { key: 'false', type: 'boolean', label: 'False' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, paletteType)}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const LogicalControlComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> }; paletteType: string }> = ({ data, paletteType }) => {
    const inputs: NodeSlot[] = [
        { key: 'input_a', type: 'boolean', label: 'A', hasValue: data.inputAHasValue },
        { key: 'input_b', type: 'boolean', label: 'B', hasValue: data.inputBHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'boolean', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, paletteType)}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const GtNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <ComparisonControlComp {...p} paletteType="gt_control" />;
const LtNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <ComparisonControlComp {...p} paletteType="lt_control" />;
const GteNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <ComparisonControlComp {...p} paletteType="gte_control" />;
const LteNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <ComparisonControlComp {...p} paletteType="lte_control" />;
const AndNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <LogicalControlComp {...p} paletteType="and_control" />;
const OrNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <LogicalControlComp {...p} paletteType="or_control" />;
const XorNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => <LogicalControlComp {...p} paletteType="xor_control" />;

const BinaryIntMathUtilityComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        inputAHasValue?: boolean;
        inputBHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
    paletteType: string;
}> = ({ data, paletteType }) => {
    const inputs: NodeSlot[] = [
        { key: 'input_a', type: 'int', label: 'A', hasValue: data.inputAHasValue },
        { key: 'input_b', type: 'int', label: 'B', hasValue: data.inputBHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'int', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, paletteType)}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const AddIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="add_ints" />
);
const SubtractIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="subtract_ints" />
);
const MultiplyIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="multiply_ints" />
);
const DivideIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="divide_ints" />
);
const ModuloIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="modulo_ints" />
);
const MinIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="min_ints" />
);
const MaxIntsNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputAHasValue?: boolean; inputBHasValue?: boolean; paletteColors?: Record<string, string> } }> = (p) => (
    <BinaryIntMathUtilityComp {...p} paletteType="max_ints" />
);

const AddDaysNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        inputHasValue?: boolean;
        daysHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'input', type: 'datetime', label: 'input', hasValue: data.inputHasValue },
        { key: 'days', type: 'int', label: 'days', hasValue: data.daysHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'datetime', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'add_days')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const NotControlComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'boolean', label: 'value', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'boolean', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'not_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const BetweenControlComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        lowHasValue?: boolean;
        valueHasValue?: boolean;
        highHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'low', type: 'int', label: 'low', hasValue: data.lowHasValue },
        { key: 'value', type: 'int', label: 'value', hasValue: data.valueHasValue },
        { key: 'high', type: 'int', label: 'high', hasValue: data.highHasValue },
    ];
    const outputs: NodeSlot[] = [
        { key: 'true', type: 'boolean', label: 'True' },
        { key: 'false', type: 'boolean', label: 'False' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'between_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const TryCatchControlComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        valueHasValue?: boolean;
        paletteColors?: Record<string, string>;
        required_inputs?: RequiredInput[];
    };
}> = ({ data }) => {
    const req = data.required_inputs ?? [{ key: 'value', type: 'any' as const, value: null }];
    const v = req.find(r => r.key === 'value')?.value;
    const valueHasValue = data.valueHasValue ?? !(v === null || v === undefined || v === '');
    const inputs: NodeSlot[] = [{ key: 'value', type: 'any', label: 'value', hasValue: valueHasValue }];
    const outputs: NodeSlot[] = [
        { key: 'try', type: 'signal', label: 'try' },
        { key: 'catch', type: 'signal', label: 'catch' },
        { key: 'output', type: 'any', label: 'output' },
        { key: 'envelope', type: 'dictionary', label: 'envelope' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'try_catch_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ForLoopControlComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string>; required_inputs?: RequiredInput[] } }> = ({ data }) => {
    const req = data.required_inputs ?? [{ key: 'input', type: 'list' as const, value: null }];
    const listVal = req.find(r => r.key === 'input')?.value;
    const inputHasValue = data.inputHasValue ?? (Array.isArray(listVal) && listVal.length > 0);
    const inputs: NodeSlot[] = [{ key: 'input', type: 'list', label: 'list', hasValue: inputHasValue }];
    const outputs: NodeSlot[] = [
        { key: 'item', type: 'any', label: 'item' },
        { key: 'summary', type: 'dictionary', label: 'summary' },
    ];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'for_loop_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ForLoopEndControlComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        for_loop_id?: string;
        exports?: string[];
    };
}> = ({ data }) => {
    const exports = Array.isArray(data.exports) && data.exports.length > 0 ? data.exports : [...DEFAULT_FOR_LOOP_END_EXPORTS];
    const inputs: NodeSlot[] = exports.map(key => ({
        key,
        type: 'any' as const,
        label: key,
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Control"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'for_loop_end_control')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const DictionaryValueNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'dictionary', label: 'items', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Dictionary"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'dictionary')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const BooleanValueNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; valueHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'boolean', label: 'value', hasValue: data.valueHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'boolean', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Boolean"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'boolean')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const IntValueNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; valueHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'int', label: 'value', hasValue: data.valueHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'int', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Int"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'int')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const DateTimeValueNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; valueHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'datetime', label: 'value', hasValue: data.valueHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'datetime', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="DateTime"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'datetime')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const LenFromListNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; listHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'list', type: 'list', label: 'list', hasValue: data.listHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'int', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'len_from_list')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const RandomItemFromListNodeComp: React.FC<{
    data: { label: string; isRunning?: boolean; listHasValue?: boolean; paletteColors?: Record<string, string> };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'list', type: 'list', label: 'list', hasValue: data.listHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'any', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'random_item_from_list')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const IntToStringNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; inputHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'input', type: 'int', label: 'value', hasValue: data.inputHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'int_to_string')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.small}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ListItemByIndexNodeComp: React.FC<{ data: { label: string; isRunning?: boolean; indexHasValue?: boolean; listHasValue?: boolean; paletteColors?: Record<string, string> } }> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'index', type: 'int', label: 'index', hasValue: data.indexHasValue },
        { key: 'list', type: 'list', label: 'list', hasValue: data.listHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'any', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'list_item_by_index')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const AddToListNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        listHasValue?: boolean;
        valueHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'list', type: 'list', label: 'list', hasValue: data.listHasValue },
        { key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'list', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'add_to_list')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const DictionaryValueByKeyNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        keyHasValue?: boolean;
        dictionaryHasValue?: boolean;
        fallbackHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'key', type: 'string', label: 'key', hasValue: data.keyHasValue },
        { key: 'dictionary', type: 'dictionary', label: 'dictionary', hasValue: data.dictionaryHasValue },
        { key: 'fallback', type: 'any', label: 'fallback (opt.)', hasValue: data.fallbackHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'any', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'dictionary_value_by_key')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const DictionarySetValueByKeyNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        keyHasValue?: boolean;
        dictionaryHasValue?: boolean;
        valueHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'dictionary', type: 'dictionary', label: 'dictionary', hasValue: data.dictionaryHasValue },
        { key: 'key', type: 'string', label: 'key', hasValue: data.keyHasValue },
        { key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'dictionary_set_value_by_key')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ReadDocumentPropertyNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        targetPropertyHasValue?: boolean;
        documentHasValue?: boolean;
        paletteColors?: Record<string, string>;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'target_property', type: 'string', label: 'target_property', hasValue: data.targetPropertyHasValue },
        { key: 'document', type: 'document', label: 'document', hasValue: data.documentHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'any', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'read_document_property')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const LoadDocumentNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        documentIdHasValue?: boolean;
        documentNameHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'document_id', type: 'string', label: 'document_id', hasValue: data.documentIdHasValue },
        { key: 'document_name', type: 'string', label: 'document_name', hasValue: data.documentNameHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'document', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'load_document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

function upsertRiTypeToNodeSlot(t: RequiredInput['type'] | undefined): NodeSlot['type'] {
    switch (t) {
        case 'string':
        case 'list':
        case 'dictionary':
        case 'structure':
        case 'document':
        case 'boolean':
        case 'int':
        case 'datetime':
        case 'gmail':
        case 'audio':
        case 'any':
            return t;
        default:
            return 'string';
    }
}

function upsertSlotFilled(
    key: string,
    data: {
        upsertInputHasValue?: Record<string, boolean>;
        nameHasValue?: boolean;
        contentHasValue?: boolean;
        existingIdHasValue?: boolean;
        writeModeHasValue?: boolean;
    },
): boolean {
    const m = data.upsertInputHasValue;
    if (m && typeof m[key] === 'boolean') return m[key];
    switch (key) {
        case 'name':
            return Boolean(data.nameHasValue);
        case 'content':
            return Boolean(data.contentHasValue);
        case 'existing_document_id':
            return Boolean(data.existingIdHasValue);
        case 'write_mode':
            return Boolean(data.writeModeHasValue);
        default:
            return false;
    }
}

const UpsertDocumentNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        required_inputs?: RequiredInput[];
        upsertInputHasValue?: Record<string, boolean>;
        nameHasValue?: boolean;
        contentHasValue?: boolean;
        existingIdHasValue?: boolean;
        writeModeHasValue?: boolean;
    };
}> = ({ data }) => {
    const normalized = normalizeUpsertDocumentRequiredInputs(data.required_inputs ?? null);
    const inputs: NodeSlot[] = normalized.map(ri => ({
        key: ri.key,
        type: upsertRiTypeToNodeSlot(ri.type),
        label: ri.key,
        hasValue: upsertSlotFilled(ri.key, data),
    }));
    const outputs: NodeSlot[] = [{ key: 'output', type: 'document', label: 'output' }];
    const cardWidth =
        normalized.length <= 2 ? NODE_MIN_WIDTH.medium : NODE_MIN_WIDTH.large;
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'upsert_document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={cardWidth}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ParseDocumentBodyNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        documentHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'document', type: 'document', label: 'document', hasValue: data.documentHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'parse_document_body')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const HtmlParseBasicNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        htmlHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'html', type: 'string', label: 'html', hasValue: data.htmlHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'dictionary', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'html_parse_basic')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const WriteObjectToDocumentBodyNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        valueHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [{ key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue }];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'write_object_to_document_body')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const AppendValueToDocumentNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        documentHasValue?: boolean;
        valueHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'document', type: 'document', label: 'document', hasValue: data.documentHasValue },
        { key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'string', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'append_value_to_document')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const ValidateAgainstStructureNodeComp: React.FC<{
    data: {
        label: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        valueHasValue?: boolean;
        structureHasValue?: boolean;
    };
}> = ({ data }) => {
    const inputs: NodeSlot[] = [
        { key: 'value', type: 'any', label: 'value', hasValue: data.valueHasValue },
        { key: 'structure', type: 'structure', label: 'structure', hasValue: data.structureHasValue },
    ];
    const outputs: NodeSlot[] = [{ key: 'output', type: 'any', label: 'output' }];
    return (
        <StyledNodeBase
            typeLabel="Utility"
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'validate_against_structure')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.medium}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

const WorkflowRefNodeComp: React.FC<{
    data: {
        label: string;
        stepTypeLabel?: string;
        isRunning?: boolean;
        paletteColors?: Record<string, string>;
        subWorkflowRequiredInputs?: RequiredInput[];
        subWorkflowRequiredOutputs?: RequiredOutput[];
    };
}> = ({ data }) => {
    const updateNodeInternals = useUpdateNodeInternals();
    const nodeId = useNodeId();
    const rawInputs = data.subWorkflowRequiredInputs ?? [{ key: 'user_input', type: 'string' as const }];
    const rawOutputs = data.subWorkflowRequiredOutputs ?? [{ key: 'output', type: 'string' as const }];
    const workflowRefHandlesSig = useMemo(
        () =>
            JSON.stringify({
                inputs: data.subWorkflowRequiredInputs ?? null,
                outputs: data.subWorkflowRequiredOutputs ?? null,
            }),
        [data.subWorkflowRequiredInputs, data.subWorkflowRequiredOutputs],
    );
    useLayoutEffect(() => {
        if (nodeId != null && nodeId !== '') {
            updateNodeInternals(nodeId);
        }
    }, [nodeId, updateNodeInternals, workflowRefHandlesSig]);

    const inputs: NodeSlot[] = rawInputs.map(inp => ({ key: inp.key, type: inp.type, label: inp.key }));
    const outputs: NodeSlot[] = rawOutputs.map(out => ({ key: out.key, type: out.type, label: out.key || '\u00A0' }));
    return (
        <StyledNodeBase
            typeLabel={data.stepTypeLabel ?? 'Workflow'}
            nodeLabel={data.label}
            inputs={inputs}
            outputs={outputs}
            borderColor={getHandleColor(data.paletteColors, 'workflow')}
            isRunning={data.isRunning}
            isCanvasSelected={Boolean((data as { isCanvasSelected?: boolean }).isCanvasSelected)}
            outputOverrideActive={Boolean((data as { outputOverrideActive?: boolean }).outputOverrideActive)}
            minWidth={NODE_MIN_WIDTH.large}
            paletteColors={data.paletteColors}
            triggerInput
            signalOutput
        />
    );
};

export const nodeTypes = {
    simpleLLMCall: SimpleLLMCallNodeComp,
    multimodalLLMCall: MultimodalLLMCallNodeComp,
    textToSpeech: TextToSpeechNodeComp,
    transcribeAudio: TranscribeAudioNodeComp,
    audioFileInput: AudioFileInputNodeComp,
    transcribeFile: TranscribeFileNodeComp,
    gmailListMessages: GmailListMessagesNodeComp,
    calendarListEvents: CalendarListEventsNodeComp,
    googleDocsGetDocument: GoogleDocsGetDocumentNodeComp,
    googleDocsParseDocument: GoogleDocsParseDocumentNodeComp,
    fetchUrl: FetchUrlNodeComp,
    captureUrlSnapshot: CaptureUrlSnapshotNodeComp,
    listToString: ListToStringNodeComp,
    stringToList: StringToListNodeComp,
    prependText: PrependTextNodeComp,
    stringTrunc: StringTruncNodeComp,
    broadcastMessage: BroadcastMessageNodeComp,
    lenFromList: LenFromListNodeComp,
    randomItemFromList: RandomItemFromListNodeComp,
    intToString: IntToStringNodeComp,
    listItemByIndex: ListItemByIndexNodeComp,
    sandboxGetPosition: SandboxGetPositionNodeComp,
    sandboxGetFacing: SandboxGetFacingNodeComp,
    sandboxGetNearby: SandboxGetNearbyNodeComp,
    sandboxMoveForward: SandboxMoveForwardNodeComp,
    sandboxTurnLeft: SandboxTurnLeftNodeComp,
    sandboxTurnRight: SandboxTurnRightNodeComp,
    sandboxIdle: SandboxIdleNodeComp,
    sandboxPickUpItem: SandboxPickUpItemNodeComp,
    sandboxPlaceItem: SandboxPlaceItemNodeComp,
    sandboxGetInventory: SandboxGetInventoryNodeComp,
    sandboxPromptUserAction: SandboxPromptUserActionNodeComp,
    sandboxForceSimulationPause: SandboxForceSimulationPauseNodeComp,
    sandboxGetCellItems: SandboxGetCellItemsNodeComp,
    sandboxRemoveItemAtCell: SandboxRemoveItemAtCellNodeComp,
    sandboxSpawnItemAtCell: SandboxSpawnItemAtCellNodeComp,
    dictionaryValueByKey: DictionaryValueByKeyNodeComp,
    dictionarySetValueByKey: DictionarySetValueByKeyNodeComp,
    readDocumentProperty: ReadDocumentPropertyNodeComp,
    loadDocument: LoadDocumentNodeComp,
    upsertDocument: UpsertDocumentNodeComp,
    parseDocumentBody: ParseDocumentBodyNodeComp,
    htmlParseBasic: HtmlParseBasicNodeComp,
    writeObjectToDocumentBody: WriteObjectToDocumentBodyNodeComp,
    appendValueToDocument: AppendValueToDocumentNodeComp,
    validateAgainstStructure: ValidateAgainstStructureNodeComp,
    addToList: AddToListNodeComp,
    addDays: AddDaysNodeComp,
    addInts: AddIntsNodeComp,
    subtractInts: SubtractIntsNodeComp,
    multiplyInts: MultiplyIntsNodeComp,
    divideInts: DivideIntsNodeComp,
    moduloInts: ModuloIntsNodeComp,
    minInts: MinIntsNodeComp,
    maxInts: MaxIntsNodeComp,
    basicConditional: BasicConditionalNodeComp,
    isControl: IsNodeComp,
    isEmptyControl: IsEmptyNodeComp,
    gtControl: GtNodeComp,
    ltControl: LtNodeComp,
    gteControl: GteNodeComp,
    lteControl: LteNodeComp,
    andControl: AndNodeComp,
    orControl: OrNodeComp,
    xorControl: XorNodeComp,
    notControl: NotControlComp,
    betweenControl: BetweenControlComp,
    tryCatchControl: TryCatchControlComp,
    forLoopControl: ForLoopControlComp,
    forLoopEndControl: ForLoopEndControlComp,
    stringPrimitive: StringValueNodeComp,
    sandboxTickPrimitive: SandboxTickPrimitiveNodeComp,
    sandboxRegionPrimitive: SandboxRegionPrimitiveNodeComp,
    listPrimitive: ListValueNodeComp,
    dictionaryPrimitive: DictionaryValueNodeComp,
    booleanPrimitive: BooleanValueNodeComp,
    intPrimitive: IntValueNodeComp,
    dateTimePrimitive: DateTimeValueNodeComp,
    structurePrimitive: StructureValueNodeComp,
    documentPrimitive: DocumentValueNodeComp,
    imagePrimitive: ImagePrimitiveNodeComp,
    gmailPrimitive: GmailPrimitiveNodeComp,
    start: StartNodeComp,
    stop: StopNodeComp,
    invalidStep: InvalidStepNodeComp,
    workflowRef: WorkflowRefNodeComp,
    annotationNote: AnnotationNoteNodeComp,
    annotationRegion: AnnotationRegionNodeComp,
};
