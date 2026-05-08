import type { ReactNode } from 'react';
import { FolderInput } from 'lucide-react';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../../api/types';

export interface WorkflowPaletteWorkflowRowProps {
    workflow: WorkflowDefinitionListItem;
    wfColor: string;
    activeWorkflowId: string | null;
    /** When false, row is the open workflow — show as active, no drag. */
    draggable: boolean;
    onOpen: (wf: WorkflowDefinitionListItem) => void;
    moveProjectPickerFor: string | null;
    onToggleMovePicker: (wfId: string) => void;
    workflowProjects: readonly WorkflowProject[];
    sharedProjectId: string | null;
    onMoveToProject: (wfId: string, projectId: string) => Promise<boolean>;
    onMoveComplete?: () => void;
    /** Optional icon before the name (e.g. Custom Skills puzzle). */
    leading?: ReactNode;
}

/**
 * Shared workflow row for the left palette (project list) and Custom Skills:
 * open on click, drag as nested workflow ref when allowed, move between projects.
 */
export function WorkflowPaletteWorkflowRow({
    workflow: wf,
    wfColor,
    activeWorkflowId,
    draggable,
    onOpen,
    moveProjectPickerFor,
    onToggleMovePicker,
    workflowProjects,
    sharedProjectId,
    onMoveToProject,
    onMoveComplete,
    leading,
}: WorkflowPaletteWorkflowRowProps) {
    const isActive = activeWorkflowId === wf.id;
    return (
        <div className="flex items-stretch gap-1 min-w-0">
            <div
                draggable={draggable}
                onDragStart={e => {
                    if (!draggable) return;
                    e.dataTransfer.setData('nodeType', 'workflowRef');
                    e.dataTransfer.setData(
                        'nodeExtra',
                        JSON.stringify({ workflow_id: wf.id, workflow_name: wf.name }),
                    );
                }}
                onClick={() => onOpen(wf)}
                className={`flex flex-1 min-w-0 items-center gap-1.5 px-2 py-1.5 text-sm rounded-lg truncate transition-colors ${
                    isActive
                        ? 'bg-mw-primary-muted text-mw-primary font-medium cursor-pointer'
                        : 'cursor-grab text-mw-text-primary hover:bg-mw-card'
                } ${draggable ? 'select-none' : ''}`}
                style={draggable ? { borderLeft: `3px solid ${wfColor}` } : undefined}
            >
                {leading ? <span className="shrink-0 flex items-center">{leading}</span> : null}
                <span className="truncate font-medium">{wf.name}</span>
            </div>
            <div className="flex items-center gap-0.5 shrink-0">
                <button
                    type="button"
                    title="Move to another project"
                    aria-label={`Move ${wf.name} to another project`}
                    aria-expanded={moveProjectPickerFor === wf.id}
                    onClick={e => {
                        e.stopPropagation();
                        onToggleMovePicker(wf.id);
                    }}
                    className="p-1 rounded-md text-mw-text-secondary hover:bg-mw-card hover:text-mw-text-primary focus:outline-none focus:ring-1 focus:ring-mw-primary"
                >
                    <FolderInput size={14} aria-hidden />
                </button>
                {moveProjectPickerFor === wf.id && (
                    <select
                        value={wf.project_id ?? sharedProjectId ?? ''}
                        aria-label={`Move ${wf.name} to project`}
                        onClick={e => e.stopPropagation()}
                        onChange={async e => {
                            e.stopPropagation();
                            const v = e.target.value;
                            if (!v) return;
                            const ok = await onMoveToProject(wf.id, v);
                            if (ok) onMoveComplete?.();
                        }}
                        className="max-w-[7rem] text-[10px] border border-mw-border bg-mw-card text-mw-text-secondary rounded px-0.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-mw-primary"
                    >
                        {workflowProjects.map(p => (
                            <option key={p.id} value={p.id}>
                                {p.name}
                            </option>
                        ))}
                    </select>
                )}
            </div>
        </div>
    );
}
