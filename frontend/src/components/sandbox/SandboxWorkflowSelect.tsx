import React, { useMemo } from 'react';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../../api/types';
import {
    creatureBrainWorkflowsInProject,
    projectsWithSandboxCreatureBrains,
} from '../../domain/workflowProjectMembership';

export interface SandboxWorkflowSelectProps {
    id: string;
    value: string;
    onChange: (workflowId: string) => void;
    disabled?: boolean;
    workflows: readonly WorkflowDefinitionListItem[];
    workflowProjects: readonly WorkflowProject[];
    sharedProjectId: string | null;
    emptyOptionLabel: string;
    className?: string;
    showEligibilityHint?: boolean;
}

export const SandboxWorkflowSelect: React.FC<SandboxWorkflowSelectProps> = ({
    id,
    value,
    onChange,
    disabled = false,
    workflows,
    workflowProjects,
    sharedProjectId,
    emptyOptionLabel,
    className = 'w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card rounded-lg',
    showEligibilityHint = false,
}) => {
    const eligibleProjects = useMemo(
        () => projectsWithSandboxCreatureBrains(workflowProjects, sharedProjectId, workflows),
        [workflowProjects, sharedProjectId, workflows],
    );

    const groupedWorkflows = useMemo(
        () =>
            eligibleProjects
                .map(project => ({
                    project,
                    workflows: creatureBrainWorkflowsInProject(project.id, sharedProjectId, workflows),
                }))
                .filter(group => group.workflows.length > 0),
        [eligibleProjects, sharedProjectId, workflows],
    );

    const listedWorkflowIds = useMemo(
        () => new Set(groupedWorkflows.flatMap(g => g.workflows.map(w => w.id))),
        [groupedWorkflows],
    );

    const orphanWorkflow = useMemo(() => {
        if (!value || listedWorkflowIds.has(value)) return null;
        return workflows.find(w => w.id === value) ?? null;
    }, [value, listedWorkflowIds, workflows]);

    return (
        <>
            <select
                id={id}
                value={value}
                disabled={disabled}
                onChange={e => onChange(e.target.value)}
                className={className}
            >
                <option value="">{emptyOptionLabel}</option>
                {groupedWorkflows.map(({ project, workflows: projectWorkflows }) => (
                    <optgroup key={project.id} label={project.name}>
                        {projectWorkflows.map(w => (
                            <option key={w.id} value={w.id}>
                                {w.name}
                            </option>
                        ))}
                    </optgroup>
                ))}
                {orphanWorkflow ? (
                    <option value={orphanWorkflow.id} disabled>
                        {orphanWorkflow.name} (unavailable)
                    </option>
                ) : value && !listedWorkflowIds.has(value) ? (
                    <option value={value} disabled>
                        {value.slice(0, 8)}… (unavailable)
                    </option>
                ) : null}
            </select>
            {showEligibilityHint ? (
                <p className="text-[11px] text-mw-text-secondary mt-1">
                    Only workflows in sandbox-enabled projects (plus Shared) are listed.
                </p>
            ) : null}
        </>
    );
};
