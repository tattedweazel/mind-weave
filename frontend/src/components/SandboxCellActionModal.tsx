/**
 * Stepped cell actions: choose root action → optional item type / project / workflow / facing / color.
 */
import React from 'react';
import { ChevronLeft, X } from 'lucide-react';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../api/types';
import type { SandboxGridCellJson, SandboxFacing } from '../domain/sandbox/types';
import { DEFAULT_SANDBOX_FACING, SANDBOX_FACING_VALUES } from '../domain/sandbox/types';
import {
    creatureBrainCountForProject,
    creatureBrainWorkflowsInProject,
} from '../domain/workflowProjectMembership';
import { deriveCellRootActions, type CellOccupants } from '../sandbox/sandboxCellOccupants';
import {
    placeCreatureInteraction,
    placeBallInteraction,
    placeFoodInteraction,
    placeRegionInteraction,
    placeWallInteraction,
    removeCreatureAtCellInteraction,
    removeItemAtCellInteraction,
    removeRegionAtCellInteraction,
    type SandboxCellInteraction,
} from '../sandbox/sandboxCellInteractions';
import { defaultSandboxPlacementColor } from '../sandbox/sandboxFavoriteColors';
import { SandboxColorPicker } from './sandbox/SandboxColorPicker';
import { PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS } from './workflow-editor/workflowEditorPanelLayout';
import {
    filterNamesByPrefix,
    sortWorkflowListItems,
    type WorkflowListSort,
} from './workflow-editor/workflowListFilter';

export type CellActionWizardStep =
    | 'choose_action'
    | 'choose_item_type'
    | 'choose_region_color'
    | 'choose_region_label'
    | 'choose_project'
    | 'choose_workflow'
    | 'choose_creature_facing'
    | 'choose_creature_color'
    | 'choose_ball_color';

const PLACE_ITEM_TYPES = [
    { id: 'food' as const, label: 'Food', description: 'Energy for creatures' },
    { id: 'wall' as const, label: 'Wall', description: 'Solid block — blocks movement and placement' },
    { id: 'ball' as const, label: 'Ball', description: 'Pickable object — choose color at placement' },
];

export interface SandboxCellActionModalProps {
    cell: SandboxGridCellJson;
    occupants: CellOccupants;
    canInspect?: boolean;
    /** Show place/remove creature actions when cell is empty or has a creature. */
    allowCreatureActions?: boolean;
    /** Projects with at least one creature-brain workflow. */
    workflowProjects?: WorkflowProject[];
    /** Full workflow list; modal filters per selected project. */
    workflows?: WorkflowDefinitionListItem[];
    /** Seeded Shared project id (null project_id rows belong here). */
    sharedProjectId?: string | null;
    /** User favorite hex colors from View Settings. */
    sandboxFavoriteColors?: string[];
    initialStep?: CellActionWizardStep;
    onComplete: (interaction: SandboxCellInteraction) => void;
    onDismiss: () => void;
    onInspect?: () => void;
}

export const SandboxCellActionModal: React.FC<SandboxCellActionModalProps> = ({
    cell,
    occupants,
    canInspect = false,
    allowCreatureActions = false,
    workflowProjects = [],
    workflows = [],
    sharedProjectId = null,
    sandboxFavoriteColors = [],
    initialStep = 'choose_action',
    onComplete,
    onDismiss,
    onInspect,
}) => {
    const [step, setStep] = React.useState<CellActionWizardStep>(initialStep);
    const [selectedProjectId, setSelectedProjectId] = React.useState<string | null>(null);
    const [selectedWorkflowId, setSelectedWorkflowId] = React.useState<string | null>(null);
    const [workflowNameFilter, setWorkflowNameFilter] = React.useState('');
    const [workflowListSort, setWorkflowListSort] = React.useState<WorkflowListSort>('updated');
    const [selectedFacing, setSelectedFacing] = React.useState<SandboxFacing>(DEFAULT_SANDBOX_FACING);
    const [selectedRegionColor, setSelectedRegionColor] = React.useState(() =>
        defaultSandboxPlacementColor(sandboxFavoriteColors),
    );
    const [selectedRegionLabel, setSelectedRegionLabel] = React.useState('');
    const [selectedCreatureColor, setSelectedCreatureColor] = React.useState(() =>
        defaultSandboxPlacementColor(sandboxFavoriteColors),
    );
    const [selectedBallColor, setSelectedBallColor] = React.useState(() =>
        defaultSandboxPlacementColor(sandboxFavoriteColors),
    );

    React.useEffect(() => {
        setSelectedRegionColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
        setSelectedCreatureColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
        setSelectedBallColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
    }, [sandboxFavoriteColors]);

    React.useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onDismiss]);

    const selectedProject = React.useMemo(
        () => (selectedProjectId ? workflowProjects.find(p => p.id === selectedProjectId) ?? null : null),
        [selectedProjectId, workflowProjects],
    );

    const workflowsInSelectedProject = React.useMemo(() => {
        if (!selectedProjectId) return [];
        return creatureBrainWorkflowsInProject(selectedProjectId, sharedProjectId, workflows);
    }, [selectedProjectId, sharedProjectId, workflows]);

    const filteredWorkflowsInProject = React.useMemo(() => {
        const filtered = filterNamesByPrefix(workflowsInSelectedProject, workflowNameFilter);
        return sortWorkflowListItems(filtered, workflowListSort);
    }, [workflowsInSelectedProject, workflowNameFilter, workflowListSort]);

    const title = React.useMemo(() => {
        if (step === 'choose_workflow' && selectedProject) {
            return selectedProject.name;
        }
        return `Cell (${cell.x}, ${cell.y})`;
    }, [step, selectedProject, cell.x, cell.y]);

    const resetCreatureWizard = () => {
        setSelectedProjectId(null);
        setSelectedWorkflowId(null);
        setWorkflowNameFilter('');
        setWorkflowListSort('updated');
        setSelectedFacing(DEFAULT_SANDBOX_FACING);
        setSelectedCreatureColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
    };

    const goBack = () => {
        if (step === 'choose_creature_color') {
            setStep('choose_creature_facing');
            return;
        }
        if (step === 'choose_creature_facing') {
            setSelectedWorkflowId(null);
            setStep('choose_workflow');
            return;
        }
        if (step === 'choose_workflow') {
            setSelectedProjectId(null);
            setWorkflowNameFilter('');
            setWorkflowListSort('updated');
            setStep('choose_project');
            return;
        }
        if (step === 'choose_project') {
            setStep('choose_action');
            return;
        }
        if (step === 'choose_item_type') {
            setStep('choose_action');
            return;
        }
        if (step === 'choose_region_label') {
            setStep('choose_region_color');
            return;
        }
        if (step === 'choose_region_color') {
            setStep('choose_action');
            return;
        }
        if (step === 'choose_ball_color') {
            setStep('choose_item_type');
            return;
        }
        onDismiss();
    };

    const openProject = (projectId: string) => {
        setSelectedProjectId(projectId);
        setSelectedWorkflowId(null);
        setWorkflowNameFilter('');
        setWorkflowListSort('updated');
        setSelectedFacing(DEFAULT_SANDBOX_FACING);
        setSelectedCreatureColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
        setStep('choose_workflow');
    };

    const selectWorkflow = (workflowId: string) => {
        setSelectedWorkflowId(workflowId);
        setStep('choose_creature_facing');
    };

    const confirmCreaturePlacement = (color: string) => {
        if (!selectedWorkflowId) return;
        onComplete(
            placeCreatureInteraction(cell, selectedWorkflowId, {
                facing: selectedFacing,
                color,
            }),
        );
    };

    const rootActions = deriveCellRootActions(occupants, { allowCreatureActions });

    return (
        <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
            onClick={onDismiss}
            role="presentation"
        >
            <div
                className="w-full max-w-md rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl overflow-hidden"
                onClick={e => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-labelledby="sandbox-cell-action-title"
            >
                <div className="flex items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                        {step !== 'choose_action' ? (
                            <button type="button" onClick={goBack} className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="Back">
                                <ChevronLeft className="h-5 w-5" />
                            </button>
                        ) : null}
                        <h2 id="sandbox-cell-action-title" className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                            {title}
                        </h2>
                    </div>
                    <button type="button" onClick={onDismiss} className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Close">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-4 space-y-3">
                    {step === 'choose_action' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Actions</p>
                            <ul className="space-y-2">
                                {canInspect && onInspect ? (
                                    <li>
                                        <button
                                            type="button"
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 dark:hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/30"
                                            onClick={() => onInspect()}
                                        >
                                            <span className="block text-sm font-medium">Inspect</span>
                                            <span className="block text-xs text-slate-500 mt-0.5">View cell details in Explorer</span>
                                        </button>
                                    </li>
                                ) : null}
                                {rootActions.map(a => (
                                    <li key={a.id}>
                                        <button
                                            type="button"
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 dark:hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/30"
                                            onClick={() => {
                                                if (a.id === 'remove_item') {
                                                    onComplete(removeItemAtCellInteraction(cell));
                                                    return;
                                                }
                                                if (a.id === 'remove_region') {
                                                    onComplete(removeRegionAtCellInteraction(cell));
                                                    return;
                                                }
                                                if (a.id === 'remove_creature') {
                                                    onComplete(removeCreatureAtCellInteraction(cell));
                                                    return;
                                                }
                                                if (a.id === 'place_creature') {
                                                    resetCreatureWizard();
                                                    setStep('choose_project');
                                                    return;
                                                }
                                                if (a.id === 'place_region') {
                                                    setSelectedRegionColor(defaultSandboxPlacementColor(sandboxFavoriteColors));
                                                    setSelectedRegionLabel('');
                                                    setStep('choose_region_color');
                                                    return;
                                                }
                                                setStep('choose_item_type');
                                            }}
                                        >
                                            <span className="block text-sm font-medium">{a.label}</span>
                                            <span className="block text-xs text-slate-500 mt-0.5">{a.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </>
                    ) : null}

                    {step === 'choose_item_type' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Item type</p>
                            <ul className="space-y-2">
                                {PLACE_ITEM_TYPES.map(t => (
                                    <li key={t.id}>
                                        <button
                                            type="button"
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 hover:bg-sky-50/50"
                                            onClick={() => {
                                                if (t.id === 'food') onComplete(placeFoodInteraction(cell));
                                                else if (t.id === 'wall') onComplete(placeWallInteraction(cell));
                                                else if (t.id === 'ball') {
                                                    setSelectedBallColor(
                                                        defaultSandboxPlacementColor(sandboxFavoriteColors),
                                                    );
                                                    setStep('choose_ball_color');
                                                }
                                            }}
                                        >
                                            <span className="block text-sm font-medium">{t.label}</span>
                                            <span className="block text-xs text-slate-500 mt-0.5">{t.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </>
                    ) : null}

                    {step === 'choose_ball_color' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                Ball color
                            </p>
                            <SandboxColorPicker
                                value={selectedBallColor}
                                favoriteColors={sandboxFavoriteColors}
                                onChange={setSelectedBallColor}
                                onConfirm={color => onComplete(placeBallInteraction(cell, color))}
                                confirmLabel={`Place ball (${selectedBallColor})`}
                            />
                        </>
                    ) : null}

                    {step === 'choose_region_color' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                Region color
                            </p>
                            <SandboxColorPicker
                                value={selectedRegionColor}
                                favoriteColors={sandboxFavoriteColors}
                                onChange={setSelectedRegionColor}
                                onConfirm={color => {
                                    setSelectedRegionColor(color);
                                    setStep('choose_region_label');
                                }}
                                confirmLabel="Next: label"
                            />
                        </>
                    ) : null}

                    {step === 'choose_region_label' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                Region label
                            </p>
                            <input
                                type="text"
                                value={selectedRegionLabel}
                                onChange={e => setSelectedRegionLabel(e.target.value)}
                                placeholder="e.g. target (leave empty if unlabeled)"
                                aria-label="Region label"
                                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                            />
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                                Creatures read this via Get nearby (<span className="font-mono">region_label</span>).
                            </p>
                            <button
                                type="button"
                                className="w-full rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium px-3 py-2.5"
                                onClick={() =>
                                    onComplete(
                                        placeRegionInteraction(cell, selectedRegionColor, selectedRegionLabel),
                                    )
                                }
                            >
                                Place region ({selectedRegionColor})
                            </button>
                        </>
                    ) : null}

                    {step === 'choose_project' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Project</p>
                            <ul className={`space-y-2 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                {workflowProjects.length === 0 ? (
                                    <li className="text-xs text-slate-500 py-2">No workflows available. Create one in Build first.</li>
                                ) : (
                                    workflowProjects.map(project => (
                                        <li key={project.id}>
                                            <button
                                                type="button"
                                                className="w-full flex items-center justify-between gap-2 text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500"
                                                onClick={() => openProject(project.id)}
                                            >
                                                <span className="block text-sm font-medium truncate">{project.name}</span>
                                                <span className="shrink-0 text-xs text-slate-500 tabular-nums">
                                                    {creatureBrainCountForProject(project, sharedProjectId, workflows)}
                                                </span>
                                            </button>
                                        </li>
                                    ))
                                )}
                            </ul>
                        </>
                    ) : null}

                    {step === 'choose_workflow' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Workflow brain</p>
                            <div
                                role="group"
                                aria-label="Sort workflows"
                                className="flex rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/50 p-0.5 gap-0.5"
                            >
                                {(['updated', 'name'] as const).map(key => (
                                    <button
                                        key={key}
                                        type="button"
                                        onClick={() => setWorkflowListSort(key)}
                                        className={`flex-1 min-w-0 px-1.5 py-1 text-[10px] font-medium rounded-md transition-colors ${
                                            workflowListSort === key
                                                ? 'bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-sm'
                                                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                                        }`}
                                    >
                                        {key === 'name' ? 'Name A–Z' : 'Last updated'}
                                    </button>
                                ))}
                            </div>
                            <input
                                type="search"
                                value={workflowNameFilter}
                                onChange={e => setWorkflowNameFilter(e.target.value)}
                                placeholder="Filter…"
                                aria-label="Filter workflows"
                                className="w-full px-2 py-1.5 text-xs border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                            />
                            <ul className={`space-y-2 min-h-0 ${PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS} overflow-y-auto`}>
                                {filteredWorkflowsInProject.length === 0 ? (
                                    <li className="text-xs text-slate-500 py-2">
                                        {workflowsInSelectedProject.length === 0
                                            ? 'No workflows in this project'
                                            : workflowNameFilter.trim()
                                              ? 'No matches'
                                              : 'No workflows in this project'}
                                    </li>
                                ) : (
                                    filteredWorkflowsInProject.map(wf => (
                                        <li key={wf.id}>
                                            <button
                                                type="button"
                                                className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500"
                                                onClick={() => selectWorkflow(wf.id)}
                                            >
                                                <span className="block text-sm font-medium">{wf.name}</span>
                                            </button>
                                        </li>
                                    ))
                                )}
                            </ul>
                        </>
                    ) : null}

                    {step === 'choose_creature_facing' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                Initial facing
                            </p>
                            <div className="flex justify-center gap-2" role="group" aria-label="Initial facing">
                                {SANDBOX_FACING_VALUES.map(facing => (
                                    <button
                                        key={facing}
                                        type="button"
                                        aria-label={`Face ${facing}`}
                                        aria-pressed={selectedFacing === facing}
                                        onClick={() => setSelectedFacing(facing)}
                                        className={`px-3 py-2 text-sm font-mono rounded-lg border ${
                                            selectedFacing === facing
                                                ? 'border-sky-500 text-sky-600 dark:text-sky-400 bg-sky-50/50 dark:bg-sky-950/30'
                                                : 'border-slate-200 dark:border-slate-600 text-slate-500 hover:text-sky-600 dark:hover:text-sky-400'
                                        }`}
                                    >
                                        {facing}
                                    </button>
                                ))}
                            </div>
                            <button
                                type="button"
                                onClick={() => setStep('choose_creature_color')}
                                className="w-full rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium py-2.5"
                            >
                                Continue
                            </button>
                        </>
                    ) : null}

                    {step === 'choose_creature_color' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                Creature color
                            </p>
                            <SandboxColorPicker
                                value={selectedCreatureColor}
                                favoriteColors={sandboxFavoriteColors}
                                onChange={setSelectedCreatureColor}
                                onConfirm={confirmCreaturePlacement}
                                confirmLabel={`Place creature (${selectedCreatureColor})`}
                            />
                        </>
                    ) : null}
                </div>
            </div>
        </div>
    );
};
