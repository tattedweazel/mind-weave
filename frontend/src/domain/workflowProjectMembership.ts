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

/** Workflows eligible as sandbox creature brains (project drill-in minus custom skills). */
export function creatureBrainWorkflows(
    workflows: readonly WorkflowDefinitionListItem[],
): WorkflowDefinitionListItem[] {
    return workflows.filter(w => !w.expose_as_custom_skill);
}

/** Creature-brain workflows in a project folder (Shared includes null project_id rows). */
export function creatureBrainWorkflowsInProject(
    projectId: string,
    sharedProjectId: string | null,
    workflows: readonly WorkflowDefinitionListItem[],
): WorkflowDefinitionListItem[] {
    return creatureBrainWorkflows(workflowsInProject(projectId, sharedProjectId, workflows));
}

/** Count of creature-brain workflows in a project (for project list badges). */
export function creatureBrainCountForProject(
    project: Pick<WorkflowProject, 'id'>,
    sharedProjectId: string | null,
    workflows: readonly WorkflowDefinitionListItem[],
): number {
    return creatureBrainWorkflowsInProject(project.id, sharedProjectId, workflows).length;
}

/** Projects that have at least one creature-brain workflow, sorted like Build drill-in. */
export function projectsWithCreatureBrains(
    projects: readonly WorkflowProject[],
    sharedProjectId: string | null,
    workflows: readonly WorkflowDefinitionListItem[],
): WorkflowProject[] {
    return [...projects]
        .filter(p => creatureBrainCountForProject(p, sharedProjectId, workflows) > 0)
        .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
}

/** Resolve the seeded Shared project id from a loaded project list. */
export function sharedProjectIdFromProjects(projects: readonly WorkflowProject[]): string | null {
    return projects.find(p => p.name === 'Shared')?.id ?? null;
}
