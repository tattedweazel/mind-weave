/**
 * Collapsible Primitives / Skills / Utilities / Sandbox Utilities / Controls / Annotation palette blocks with per-section filter and scroll.
 */
import React, { useMemo, useState } from 'react';
import type { WorkflowDefinitionListItem, WorkflowProject } from '../../api/types';
import { WorkflowPaletteWorkflowRow } from './WorkflowPaletteWorkflowRow';
import {
    AlignLeft,
    ArrowDownToLine,
    ArrowLeftRight,
    ArrowUpToLine,
    BookKey,
    Braces,
    Calendar,
    CalendarDays,
    Camera,
    Captions,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Circle,
    CircleDot,
    CircleSlash,
    Divide,
    Equal,
    FileAudio,
    FileJson,
    FileSearch,
    FileText,
    Frame,
    GitBranch,
    Hash,
    Image,
    ImagePlus,
    Inbox,
    LayoutGrid,
    Link2,
    List as ListIcon,
    ListFilter,
    ListPlus,
    ListTree,
    ListOrdered,
    Mail,
    MessageSquare,
    Minus,
    Octagon,
    Percent,
    Plus,
    Puzzle,
    Repeat,
    Save,
    ShieldHalf,
    Ruler,
    Shuffle,
    Sparkles,
    StickyNote,
    Target,
    ToggleLeft,
    Type,
    Volume2,
    Mic,
    X,
} from 'lucide-react';
import { getHandleColor } from './constants';
import {
    PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS,
} from './workflowEditorPanelLayout';
import {
    WORKFLOW_PALETTE_ANNOTATION_ITEMS,
    WORKFLOW_PALETTE_CONTROL_ITEMS,
    WORKFLOW_PALETTE_FLOW_ITEMS,
    WORKFLOW_PALETTE_PRIMITIVE_ITEMS,
    WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS,
    WORKFLOW_PALETTE_SKILL_ITEMS,
    WORKFLOW_PALETTE_UTILITY_ITEMS,
    type WorkflowPaletteStepItem,
} from './workflowPaletteStepItems';

function paletteStepIcon(nodeType: string): React.ReactNode {
    const size = 13;
    switch (nodeType) {
        case 'stringPrimitive':
            return <AlignLeft size={size} />;
        case 'listPrimitive':
            return <ListIcon size={size} />;
        case 'dictionaryPrimitive':
            return <FileJson size={size} />;
        case 'booleanPrimitive':
            return <ToggleLeft size={size} />;
        case 'intPrimitive':
            return <Hash size={size} />;
        case 'dateTimePrimitive':
            return <Calendar size={size} />;
        case 'structurePrimitive':
            return <Braces size={size} />;
        case 'documentPrimitive':
            return <FileText size={size} />;
        case 'imagePrimitive':
            return <ImagePlus size={size} />;
        case 'gmailPrimitive':
            return <Mail size={size} />;
        case 'stop':
            return <Octagon size={size} />;
        case 'simpleLLMCall':
            return <Sparkles size={size} />;
        case 'multimodalLLMCall':
            return <Image size={size} />;
        case 'textToSpeech':
            return <Volume2 size={size} />;
        case 'transcribeAudio':
            return <Mic size={size} />;
        case 'audioFileInput':
            return <FileAudio size={size} />;
        case 'transcribeFile':
            return <Captions size={size} />;
        case 'gmailListMessages':
            return <Mail size={size} />;
        case 'calendarListEvents':
            return <Calendar size={size} />;
        case 'googleDocsGetDocument':
            return <FileText size={size} />;
        case 'fetchUrl':
            return <Link2 size={size} />;
        case 'captureUrlSnapshot':
            return <Camera size={size} />;
        case 'listToString':
            return <ListIcon size={size} />;
        case 'stringToList':
            return <ListTree size={size} />;
        case 'prependText':
            return <Type size={size} />;
        case 'stringTrunc':
            return <Type size={size} />;
        case 'messageUtility':
            return <MessageSquare size={size} />;
        case 'annotationNote':
            return <StickyNote size={size} />;
        case 'annotationRegion':
            return <Frame size={size} />;
        case 'lenFromList':
            return <Ruler size={size} />;
        case 'randomItemFromList':
            return <Shuffle size={size} />;
        case 'decisionActionPrimitive':
            return <Target size={size} />;
        case 'sandboxTickPrimitive':
            return <LayoutGrid size={size} />;
        case 'sandboxTickItems':
            return <LayoutGrid size={size} />;
        case 'sandboxWorldGrid':
            return <LayoutGrid size={size} />;
        case 'sandboxAvailableCells':
            return <LayoutGrid size={size} />;
        case 'sandboxTickPet':
            return <Hash size={size} />;
        case 'sandboxNearestItemByType':
            return <ListFilter size={size} />;
        case 'sandboxClosestItem':
            return <ListFilter size={size} />;
        case 'sandboxDecisionMoveTo':
            return <GitBranch size={size} />;
        case 'sandboxFilterItemsByType':
            return <ListFilter size={size} />;
        case 'sandboxDecisionIntent':
            return <GitBranch size={size} />;
        case 'sandboxStarterDecision':
            return <LayoutGrid size={size} />;
        case 'sandboxPetHunger':
        case 'sandboxPetEnergy':
        case 'sandboxPetCell':
            return <Hash size={size} />;
        case 'sandboxIsNearby8':
            return <ArrowLeftRight size={size} />;
        case 'sandboxFirstNearbyFood':
        case 'sandboxFirstFoodWorldOrder':
            return <ListFilter size={size} />;
        case 'intToString':
            return <ArrowLeftRight size={size} />;
        case 'listItemByIndex':
            return <ListOrdered size={size} />;
        case 'dictionaryValueByKey':
            return <BookKey size={size} />;
        case 'dictionarySetValueByKey':
            return <BookKey size={size} />;
        case 'readDocumentProperty':
            return <BookKey size={size} />;
        case 'loadDocument':
            return <FileSearch size={size} />;
        case 'upsertDocument':
            return <Save size={size} />;
        case 'parseDocumentBody':
            return <Braces size={size} />;
        case 'htmlParseBasic':
        case 'googleDocsParseDocument':
            return <FileText size={size} />;
        case 'writeObjectToDocumentBody':
            return <FileJson size={size} />;
        case 'appendValueToDocument':
            return <ListPlus size={size} />;
        case 'validateAgainstStructure':
            return <Braces size={size} />;
        case 'addToList':
            return <ListPlus size={size} />;
        case 'addDays':
            return <CalendarDays size={size} />;
        case 'addInts':
            return <Plus size={size} />;
        case 'subtractInts':
            return <Minus size={size} />;
        case 'multiplyInts':
            return <X size={size} />;
        case 'divideInts':
            return <Divide size={size} />;
        case 'moduloInts':
            return <Percent size={size} />;
        case 'minInts':
            return <ArrowDownToLine size={size} />;
        case 'maxInts':
            return <ArrowUpToLine size={size} />;
        case 'basicConditional':
            return <GitBranch size={size} />;
        case 'isControl':
            return <Equal size={size} />;
        case 'isEmptyControl':
            return <Inbox size={size} />;
        case 'gtControl':
            return <ChevronRight size={size} />;
        case 'ltControl':
            return <ChevronLeft size={size} />;
        case 'gteControl':
            return <ChevronRight size={size} />;
        case 'lteControl':
            return <ChevronLeft size={size} />;
        case 'andControl':
            return <CircleDot size={size} />;
        case 'orControl':
            return <Circle size={size} />;
        case 'xorControl':
            return <Minus size={size} />;
        case 'notControl':
            return <CircleSlash size={size} />;
        case 'betweenControl':
            return <ArrowLeftRight size={size} />;
        case 'tryCatchControl':
            return <ShieldHalf size={size} />;
        case 'forLoopControl':
            return <Repeat size={size} />;
        case 'forLoopEndControl':
            return <Repeat size={size} />;
        default:
            return null;
    }
}

function filterItems(items: readonly WorkflowPaletteStepItem[], query: string): WorkflowPaletteStepItem[] {
    const q = query.trim().toLowerCase();
    if (!q) return [...items];
    return items.filter(i => i.label.toLowerCase().startsWith(q));
}

export interface WorkflowPaletteStepSectionsProps {
    paletteColors: Record<string, string>;
    mode: 'edit' | 'reference';
    flowOpen: boolean;
    onFlowOpenChange: (open: boolean) => void;
    primitivesOpen: boolean;
    onPrimitivesOpenChange: (open: boolean) => void;
    skillsOpen: boolean;
    onSkillsOpenChange: (open: boolean) => void;
    /** Workflows flagged as reusable custom skills (nested workflow refs). */
    customSkillWorkflows?: readonly WorkflowDefinitionListItem[];
    customSkillsOpen?: boolean;
    onCustomSkillsOpenChange?: (open: boolean) => void;
    activeWorkflowId?: string | null;
    onCustomSkillWorkflowOpen?: (wf: WorkflowDefinitionListItem) => void;
    moveProjectPickerFor?: string | null;
    onToggleMoveProjectPicker?: (wfId: string) => void;
    workflowProjects?: readonly WorkflowProject[];
    sharedProjectId?: string | null;
    onMoveWorkflowToProject?: (wfId: string, projectId: string) => Promise<boolean>;
    /** Called after a successful move from a Custom Skills row (closes project picker). */
    onAfterMoveWorkflowFromPalette?: () => void;
    utilitiesOpen: boolean;
    onUtilitiesOpenChange: (open: boolean) => void;
    sandboxUtilitiesOpen: boolean;
    onSandboxUtilitiesOpenChange: (open: boolean) => void;
    controlsOpen: boolean;
    onControlsOpenChange: (open: boolean) => void;
    annotationsOpen: boolean;
    onAnnotationsOpenChange: (open: boolean) => void;
}

export function WorkflowPaletteStepSections({
    paletteColors,
    mode,
    flowOpen,
    onFlowOpenChange,
    primitivesOpen,
    onPrimitivesOpenChange,
    skillsOpen,
    onSkillsOpenChange,
    customSkillWorkflows = [],
    customSkillsOpen = false,
    onCustomSkillsOpenChange,
    activeWorkflowId = null,
    onCustomSkillWorkflowOpen,
    moveProjectPickerFor = null,
    onToggleMoveProjectPicker,
    workflowProjects = [],
    sharedProjectId = null,
    onMoveWorkflowToProject,
    onAfterMoveWorkflowFromPalette,
    utilitiesOpen,
    onUtilitiesOpenChange,
    sandboxUtilitiesOpen,
    onSandboxUtilitiesOpenChange,
    controlsOpen,
    onControlsOpenChange,
    annotationsOpen,
    onAnnotationsOpenChange,
}: WorkflowPaletteStepSectionsProps) {
    const [filterFlow, setFilterFlow] = useState('');
    const [filterPrimitives, setFilterPrimitives] = useState('');
    const [filterSkills, setFilterSkills] = useState('');
    const [filterCustomSkills, setFilterCustomSkills] = useState('');
    const [filterUtilities, setFilterUtilities] = useState('');
    const [filterSandboxUtilities, setFilterSandboxUtilities] = useState('');
    const [filterControls, setFilterControls] = useState('');
    const [filterAnnotations, setFilterAnnotations] = useState('');

    const flowFiltered = useMemo(() => filterItems(WORKFLOW_PALETTE_FLOW_ITEMS, filterFlow), [filterFlow]);
    const primitivesFiltered = useMemo(() => filterItems(WORKFLOW_PALETTE_PRIMITIVE_ITEMS, filterPrimitives), [filterPrimitives]);
    const skillsFiltered = useMemo(() => filterItems(WORKFLOW_PALETTE_SKILL_ITEMS, filterSkills), [filterSkills]);
    const customSkillsFiltered = useMemo(() => {
        const q = filterCustomSkills.trim().toLowerCase();
        if (!q) return [...customSkillWorkflows];
        return customSkillWorkflows.filter(w => w.name.toLowerCase().startsWith(q));
    }, [customSkillWorkflows, filterCustomSkills]);

    const useCustomSkillRows =
        onCustomSkillWorkflowOpen != null &&
        onToggleMoveProjectPicker != null &&
        onMoveWorkflowToProject != null;
    const utilitiesFiltered = useMemo(() => filterItems(WORKFLOW_PALETTE_UTILITY_ITEMS, filterUtilities), [filterUtilities]);
    const sandboxUtilitiesFiltered = useMemo(
        () => filterItems(WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS, filterSandboxUtilities),
        [filterSandboxUtilities],
    );
    const controlsFiltered = useMemo(() => filterItems(WORKFLOW_PALETTE_CONTROL_ITEMS, filterControls), [filterControls]);
    const annotationsFiltered = useMemo(
        () => filterItems(WORKFLOW_PALETTE_ANNOTATION_ITEMS, filterAnnotations),
        [filterAnnotations],
    );

    const tileClass =
        mode === 'edit'
            ? 'flex items-center gap-2 px-2 py-2 bg-mw-card rounded-lg cursor-grab text-xs text-mw-text-primary transition-colors select-none hover:opacity-90'
            : 'flex items-center gap-2 px-2 py-2 bg-mw-card rounded-lg cursor-default text-xs text-mw-text-primary transition-colors select-none';

    const renderTiles = (items: WorkflowPaletteStepItem[]) =>
        items.map(item => {
            const color = getHandleColor(paletteColors, item.paletteType);
            return (
                <div
                    key={item.type}
                    draggable={mode === 'edit'}
                    onDragStart={
                        mode === 'edit'
                            ? e => {
                                  e.dataTransfer.setData('nodeType', item.type);
                                  e.dataTransfer.setData('nodeExtra', JSON.stringify(item.extra));
                              }
                            : undefined
                    }
                    className={tileClass}
                    style={{ border: `2px solid ${color}` }}
                    aria-label={mode === 'reference' ? `${item.label} (reference only)` : undefined}
                >
                    <span style={{ color }}>{paletteStepIcon(item.type)}</span>
                    <span className="font-medium">{item.label}</span>
                </div>
            );
        });

    const scrollListClass = `space-y-1.5 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`;

    return (
        <>
            <div className={`p-3 border-b border-mw-border ${!flowOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onFlowOpenChange(!flowOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {flowOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Flow
                    </button>
                    <input
                        type="search"
                        value={filterFlow}
                        onChange={e => setFilterFlow(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Flow"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {flowOpen && (
                    <div className={scrollListClass}>
                        {flowFiltered.length > 0 ? renderTiles(flowFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>
            <div className={`p-3 border-b border-mw-border ${!primitivesOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onPrimitivesOpenChange(!primitivesOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {primitivesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Primitives
                    </button>
                    <input
                        type="search"
                        value={filterPrimitives}
                        onChange={e => setFilterPrimitives(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Primitives"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {primitivesOpen && (
                    <div className={scrollListClass}>
                        {primitivesFiltered.length > 0 ? renderTiles(primitivesFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>

            <div className={`p-3 border-b border-mw-border ${!skillsOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onSkillsOpenChange(!skillsOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {skillsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Skills
                    </button>
                    <input
                        type="search"
                        value={filterSkills}
                        onChange={e => setFilterSkills(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Skills"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {skillsOpen && (
                    <div className={scrollListClass}>
                        {skillsFiltered.length > 0 ? renderTiles(skillsFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>

            {onCustomSkillsOpenChange != null && (
                <div className={`p-3 border-b border-mw-border ${!customSkillsOpen ? 'shrink-0' : ''}`}>
                    <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                        <button
                            type="button"
                            onClick={() => onCustomSkillsOpenChange(!customSkillsOpen)}
                            className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                        >
                            {customSkillsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Custom Skills
                        </button>
                        <input
                            type="search"
                            value={filterCustomSkills}
                            onChange={e => setFilterCustomSkills(e.target.value)}
                            placeholder="Filter…"
                            aria-label="Filter Custom Skills"
                            className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                        />
                    </div>
                    {customSkillsOpen && (
                        <div className={scrollListClass}>
                            {customSkillsFiltered.length > 0 ? (
                                customSkillsFiltered.map(wf => {
                                    const color = getHandleColor(paletteColors, 'workflow');
                                    if (useCustomSkillRows) {
                                        const canDrag = mode === 'edit' && wf.id !== activeWorkflowId;
                                        return (
                                            <WorkflowPaletteWorkflowRow
                                                key={wf.id}
                                                workflow={wf}
                                                wfColor={color}
                                                activeWorkflowId={activeWorkflowId}
                                                draggable={canDrag}
                                                onOpen={onCustomSkillWorkflowOpen}
                                                moveProjectPickerFor={moveProjectPickerFor}
                                                onToggleMovePicker={onToggleMoveProjectPicker}
                                                workflowProjects={workflowProjects}
                                                sharedProjectId={sharedProjectId}
                                                onMoveToProject={onMoveWorkflowToProject}
                                                onMoveComplete={onAfterMoveWorkflowFromPalette}
                                                leading={<Puzzle size={13} style={{ color }} aria-hidden />}
                                            />
                                        );
                                    }
                                    return (
                                        <div
                                            key={wf.id}
                                            draggable={mode === 'edit' && wf.id !== activeWorkflowId}
                                            onDragStart={
                                                mode === 'edit'
                                                    ? e => {
                                                          e.dataTransfer.setData('nodeType', 'workflowRef');
                                                          e.dataTransfer.setData(
                                                              'nodeExtra',
                                                              JSON.stringify({ workflow_id: wf.id, workflow_name: wf.name }),
                                                          );
                                                      }
                                                    : undefined
                                            }
                                            className={tileClass}
                                            style={{ border: `2px solid ${color}` }}
                                            aria-label={mode === 'reference' ? `${wf.name} (reference only)` : undefined}
                                        >
                                            <span style={{ color }}>
                                                <Puzzle size={13} />
                                            </span>
                                            <span className="font-medium truncate">{wf.name}</span>
                                        </div>
                                    );
                                })
                            ) : (
                                <p className="text-xs text-mw-text-secondary text-center py-1">
                                    {customSkillWorkflows.length === 0
                                        ? 'Use Explorer → Expose as Custom Skill at the bottom of the workflow panel.'
                                        : 'No matches'}
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className={`p-3 border-b border-mw-border ${!utilitiesOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onUtilitiesOpenChange(!utilitiesOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {utilitiesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Utilities
                    </button>
                    <input
                        type="search"
                        value={filterUtilities}
                        onChange={e => setFilterUtilities(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Utilities"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {utilitiesOpen && (
                    <div className={scrollListClass}>
                        {utilitiesFiltered.length > 0 ? renderTiles(utilitiesFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>

            <div className={`p-3 border-b border-mw-border ${!sandboxUtilitiesOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onSandboxUtilitiesOpenChange(!sandboxUtilitiesOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {sandboxUtilitiesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Sandbox Utilities
                    </button>
                    <input
                        type="search"
                        value={filterSandboxUtilities}
                        onChange={e => setFilterSandboxUtilities(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Sandbox Utilities"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {sandboxUtilitiesOpen && (
                    <div className={scrollListClass}>
                        {sandboxUtilitiesFiltered.length > 0 ? renderTiles(sandboxUtilitiesFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>

            <div className={`p-3 border-b border-mw-border ${!controlsOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onControlsOpenChange(!controlsOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {controlsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Controls
                    </button>
                    <input
                        type="search"
                        value={filterControls}
                        onChange={e => setFilterControls(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Controls"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {controlsOpen && (
                    <div className={scrollListClass}>
                        {controlsFiltered.length > 0 ? renderTiles(controlsFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>

            <div className={`p-3 ${!annotationsOpen ? 'shrink-0' : ''}`}>
                <div className="flex flex-nowrap items-center gap-x-2 mb-2">
                    <button
                        type="button"
                        onClick={() => onAnnotationsOpenChange(!annotationsOpen)}
                        className="flex items-center gap-1 text-xs font-semibold text-mw-text-secondary uppercase tracking-wide hover:text-mw-text-primary transition-colors"
                    >
                        {annotationsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Annotation
                    </button>
                    <input
                        type="search"
                        value={filterAnnotations}
                        onChange={e => setFilterAnnotations(e.target.value)}
                        placeholder="Filter…"
                        aria-label="Filter Annotation"
                        className="min-w-0 flex-1 basis-[8rem] max-w-full px-1.5 py-0.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    />
                </div>
                {annotationsOpen && (
                    <div className={scrollListClass}>
                        {annotationsFiltered.length > 0 ? renderTiles(annotationsFiltered) : (
                            <p className="text-xs text-mw-text-secondary text-center py-1">No matches</p>
                        )}
                    </div>
                )}
            </div>
        </>
    );
}
