import type { BoardProject } from '../api/types';
import type { SandboxBoardJson } from './sandbox/types';

/** All user boards belonging to a project folder (excludes system boards). */
export function boardsInProject(
    projectId: string,
    sharedProjectId: string | null,
    boards: readonly SandboxBoardJson[],
): SandboxBoardJson[] {
    const userBoards = boards.filter(b => !b.is_system);
    if (sharedProjectId && projectId === sharedProjectId) {
        return userBoards.filter(b => b.project_id === projectId || b.project_id == null);
    }
    return userBoards.filter(b => b.project_id === projectId);
}

/** Reserved Shared folder cannot be deleted from the UI. */
export function isDeletableBoardProject(project: Pick<BoardProject, 'name'>): boolean {
    return project.name !== 'Shared';
}

export function boardProjectDeleteConfirmMessage(projectName: string, boardCount: number): string {
    if (boardCount > 0) {
        const noun = boardCount === 1 ? 'board' : 'boards';
        return `Delete ${projectName} and all ${boardCount} ${noun} in it?`;
    }
    return `Delete ${projectName}?`;
}

export function boardCountForProject(
    project: Pick<BoardProject, 'id'>,
    sharedProjectId: string | null,
    boards: readonly SandboxBoardJson[],
): number {
    return boardsInProject(project.id, sharedProjectId, boards).length;
}

export function boardDeleteConfirmMessage(boardName: string): string {
    return `Delete "${boardName}"?`;
}

/** After deleting a board, pick the next id in the current sorted list (or null). */
export function nextBoardIdAfterDelete(sortedBoardIds: readonly string[], deletedId: string): string | null {
    const idx = sortedBoardIds.indexOf(deletedId);
    if (idx < 0) {
        return sortedBoardIds[0] ?? null;
    }
    if (sortedBoardIds.length <= 1) {
        return null;
    }
    if (idx < sortedBoardIds.length - 1) {
        return sortedBoardIds[idx + 1] ?? null;
    }
    return sortedBoardIds[idx - 1] ?? null;
}

/** Resolve the seeded Shared project id from a loaded project list. */
export function sharedBoardProjectIdFromProjects(projects: readonly BoardProject[]): string | null {
    return projects.find(p => p.name === 'Shared')?.id ?? null;
}

export function sortBoardsForList(
    boards: readonly SandboxBoardJson[],
    sort: 'updated' | 'name',
): SandboxBoardJson[] {
    const copy = [...boards];
    if (sort === 'name') {
        copy.sort((a, b) => a.name.localeCompare(b.name));
    } else {
        copy.sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.name.localeCompare(b.name));
    }
    return copy;
}
