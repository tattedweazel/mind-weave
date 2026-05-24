import { describe, expect, it } from 'vitest';

import {
    boardCountForProject,
    boardDeleteConfirmMessage,
    boardProjectDeleteConfirmMessage,
    boardsInProject,
    isDeletableBoardProject,
    nextBoardIdAfterDelete,
    sharedBoardProjectIdFromProjects,
    sortBoardsForList,
} from './boardProjectMembership';
import type { BoardProject } from '../api/types';
import type { SandboxBoardJson } from './sandbox/types';

function board(id: string, overrides: Partial<SandboxBoardJson> = {}): SandboxBoardJson {
    return {
        id,
        name: `Board ${id}`,
        description: '',
        is_system: false,
        project_id: 'proj-shared',
        definition: { schema_version: '2.4.0', grid: { width: 8, height: 8 }, items: [], creatures: [] },
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        ...overrides,
    };
}

describe('boardsInProject', () => {
    it('includes null project_id rows in Shared', () => {
        const boards = [
            board('a', { project_id: 'proj-shared' }),
            board('b', { project_id: null }),
            board('c', { project_id: 'other' }),
        ];
        expect(boardsInProject('proj-shared', 'proj-shared', boards).map(b => b.id)).toEqual(['a', 'b']);
    });

    it('excludes system boards', () => {
        const boards = [board('sys', { is_system: true, project_id: null })];
        expect(boardsInProject('proj-shared', 'proj-shared', boards)).toEqual([]);
    });
});

describe('sharedBoardProjectIdFromProjects', () => {
    it('finds Shared by name', () => {
        const projects: BoardProject[] = [
            {
                id: 'p1',
                user_id: 'u',
                name: 'Shared',
                sort_order: 0,
                board_count: 0,
                created_at: '',
                updated_at: '',
            },
        ];
        expect(sharedBoardProjectIdFromProjects(projects)).toBe('p1');
    });
});

describe('isDeletableBoardProject', () => {
    it('Shared is not deletable', () => {
        expect(isDeletableBoardProject({ name: 'Shared' })).toBe(false);
        expect(isDeletableBoardProject({ name: 'Mine' })).toBe(true);
    });
});

describe('boardProjectDeleteConfirmMessage', () => {
    it('includes count when non-empty', () => {
        expect(boardProjectDeleteConfirmMessage('Alpha', 2)).toContain('2 boards');
    });
});

describe('boardDeleteConfirmMessage', () => {
    it('quotes board name', () => {
        expect(boardDeleteConfirmMessage('My Board')).toBe('Delete "My Board"?');
    });
});

describe('nextBoardIdAfterDelete', () => {
    it('selects next board when deleting middle item', () => {
        expect(nextBoardIdAfterDelete(['a', 'b', 'c'], 'b')).toBe('c');
    });

    it('selects previous when deleting last', () => {
        expect(nextBoardIdAfterDelete(['a', 'b'], 'b')).toBe('a');
    });

    it('returns null when only one board', () => {
        expect(nextBoardIdAfterDelete(['a'], 'a')).toBeNull();
    });
});

describe('sortBoardsForList', () => {
    it('sorts by name', () => {
        const boards = [board('1', { name: 'Zeta' }), board('2', { name: 'Alpha' })];
        expect(sortBoardsForList(boards, 'name').map(b => b.name)).toEqual(['Alpha', 'Zeta']);
    });

    it('sorts by updated desc', () => {
        const boards = [
            board('1', { name: 'Old', updated_at: '2026-01-01T00:00:00Z' }),
            board('2', { name: 'New', updated_at: '2026-01-03T00:00:00Z' }),
        ];
        expect(sortBoardsForList(boards, 'updated').map(b => b.name)).toEqual(['New', 'Old']);
    });
});

describe('boardCountForProject', () => {
    it('counts boards in Shared including null project_id', () => {
        const boards = [board('a'), board('b', { project_id: null })];
        expect(boardCountForProject({ id: 'proj-shared' }, 'proj-shared', boards)).toBe(2);
    });
});
