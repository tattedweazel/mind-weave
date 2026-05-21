import { describe, expect, it } from 'vitest';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../api/types';
import {
    isDeletableProject,
    projectDeleteConfirmMessage,
    workflowsInProject,
} from './workflowProjectMembership';

function wf(overrides: Partial<WorkflowDefinitionListItem> & Pick<WorkflowDefinitionListItem, 'id'>): WorkflowDefinitionListItem {
    return {
        name: 'W',
        updated_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        ...overrides,
    };
}

describe('workflowsInProject', () => {
    const sharedId = 'shared-id';
    const otherId = 'other-id';
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'b', project_id: null }),
        wf({ id: 'c', project_id: otherId, expose_as_custom_skill: true }),
        wf({ id: 'd', project_id: otherId }),
    ];

    it('includes null project_id rows when folder is Shared', () => {
        const rows = workflowsInProject(sharedId, sharedId, workflows);
        expect(rows.map(r => r.id).sort()).toEqual(['a', 'b']);
    });

    it('includes custom skills for non-Shared projects', () => {
        const rows = workflowsInProject(otherId, sharedId, workflows);
        expect(rows.map(r => r.id).sort()).toEqual(['c', 'd']);
    });
});

describe('isDeletableProject', () => {
    it('returns false for Shared', () => {
        expect(isDeletableProject({ name: 'Shared' } as WorkflowProject)).toBe(false);
    });

    it('returns true for user projects', () => {
        expect(isDeletableProject({ name: 'My Project' } as WorkflowProject)).toBe(true);
    });
});

describe('projectDeleteConfirmMessage', () => {
    it('uses empty-project copy', () => {
        expect(projectDeleteConfirmMessage('Alpha', 0)).toBe('Delete Alpha?');
    });

    it('uses cascade copy with plural workflows', () => {
        expect(projectDeleteConfirmMessage('Beta', 2)).toBe('Delete Beta and all 2 workflows in it?');
    });

    it('uses singular workflow', () => {
        expect(projectDeleteConfirmMessage('Gamma', 1)).toBe('Delete Gamma and all 1 workflow in it?');
    });
});
