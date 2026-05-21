import type { WorkflowDefinitionListItem, WorkflowProject } from '../api/types';

/** All workflow definitions belonging to a project folder (including custom skills). */
export function workflowsInProject(
    projectId: string,
    sharedProjectId: string | null,
    workflows: readonly WorkflowDefinitionListItem[],
): WorkflowDefinitionListItem[] {
    if (sharedProjectId && projectId === sharedProjectId) {
        return workflows.filter(w => w.project_id === projectId || w.project_id == null);
    }
    return workflows.filter(w => w.project_id === projectId);
}

/** Reserved Shared folder cannot be deleted from the UI. */
export function isDeletableProject(project: Pick<WorkflowProject, 'name'>): boolean {
    return project.name !== 'Shared';
}

export function projectDeleteConfirmMessage(projectName: string, workflowCount: number): string {
    if (workflowCount > 0) {
        const noun = workflowCount === 1 ? 'workflow' : 'workflows';
        return `Delete ${projectName} and all ${workflowCount} ${noun} in it?`;
    }
    return `Delete ${projectName}?`;
}
