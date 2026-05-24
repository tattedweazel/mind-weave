import { describe, expect, it } from 'vitest';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../api/types';
import {
    creatureBrainCountForProject,
    creatureBrainWorkflows,
    creatureBrainWorkflowsInProject,
    isDeletableProject,
    isSandboxEnabledProject,
    projectDeleteConfirmMessage,
    projectsWithCreatureBrains,
    projectsWithSandboxCreatureBrains,
    sandboxEligibleCreatureBrainWorkflows,
    sharedProjectIdFromProjects,
    workflowsInProject,
} from './workflowProjectMembership';

function project(overrides: Partial<WorkflowProject> & Pick<WorkflowProject, 'id' | 'name'>): WorkflowProject {
    return {
        user_id: 'user-1',
        sort_order: 0,
        sandbox_enabled: false,
        workflow_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        ...overrides,
    };
}

function wf(overrides: Partial<WorkflowDefinitionListItem> & Pick<WorkflowDefinitionListItem, 'id'>): WorkflowDefinitionListItem {
    return {
        user_id: null,
        name: 'W',
        description: null,
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

describe('creatureBrainWorkflows', () => {
    it('excludes custom skills', () => {
        const workflows = [
            wf({ id: 'a' }),
            wf({ id: 'b', expose_as_custom_skill: true }),
        ];
        expect(creatureBrainWorkflows(workflows).map(r => r.id)).toEqual(['a']);
    });
});

describe('creatureBrainWorkflowsInProject', () => {
    const sharedId = 'shared-id';
    const otherId = 'other-id';
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'b', project_id: null }),
        wf({ id: 'c', project_id: otherId, expose_as_custom_skill: true }),
        wf({ id: 'd', project_id: otherId }),
    ];

    it('includes Shared null rows and excludes custom skills', () => {
        const rows = creatureBrainWorkflowsInProject(sharedId, sharedId, workflows);
        expect(rows.map(r => r.id).sort()).toEqual(['a', 'b']);
    });

    it('excludes custom skills in non-Shared projects', () => {
        const rows = creatureBrainWorkflowsInProject(otherId, sharedId, workflows);
        expect(rows.map(r => r.id)).toEqual(['d']);
    });
});

describe('creatureBrainCountForProject', () => {
    const sharedId = 'shared-id';
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'b', project_id: sharedId, expose_as_custom_skill: true }),
    ];

    it('counts only creature-brain workflows', () => {
        expect(creatureBrainCountForProject({ id: sharedId }, sharedId, workflows)).toBe(1);
    });
});

describe('projectsWithCreatureBrains', () => {
    const sharedId = 'shared-id';
    const otherId = 'other-id';
    const projects = [
        project({ id: sharedId, name: 'Shared', sort_order: 0 }),
        project({ id: otherId, name: 'Alpha', sort_order: 1 }),
        project({ id: 'empty-id', name: 'Empty', sort_order: 2 }),
    ];
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'd', project_id: otherId }),
    ];

    it('hides empty projects and sorts by sort_order then name', () => {
        const result = projectsWithCreatureBrains(projects, sharedId, workflows);
        expect(result.map(p => p.id)).toEqual([sharedId, otherId]);
    });
});

describe('isSandboxEnabledProject', () => {
    const sharedId = 'shared-id';

    it('returns true for Shared even when sandbox_enabled is false', () => {
        expect(isSandboxEnabledProject(project({ id: sharedId, name: 'Shared', sandbox_enabled: false }), sharedId)).toBe(
            true,
        );
    });

    it('returns sandbox_enabled for non-Shared projects', () => {
        expect(
            isSandboxEnabledProject(project({ id: 'a', name: 'Alpha', sandbox_enabled: true }), sharedId),
        ).toBe(true);
        expect(
            isSandboxEnabledProject(project({ id: 'a', name: 'Alpha', sandbox_enabled: false }), sharedId),
        ).toBe(false);
    });
});

describe('projectsWithSandboxCreatureBrains', () => {
    const sharedId = 'shared-id';
    const enabledId = 'enabled-id';
    const disabledId = 'disabled-id';
    const projects = [
        project({ id: sharedId, name: 'Shared', sort_order: 0, sandbox_enabled: false }),
        project({ id: enabledId, name: 'Sandbox', sort_order: 1, sandbox_enabled: true }),
        project({ id: disabledId, name: 'Gmail', sort_order: 2, sandbox_enabled: false }),
    ];
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'b', project_id: enabledId }),
        wf({ id: 'c', project_id: disabledId }),
    ];

    it('includes Shared and sandbox-enabled projects with creature brains', () => {
        const result = projectsWithSandboxCreatureBrains(projects, sharedId, workflows);
        expect(result.map(p => p.id)).toEqual([sharedId, enabledId]);
    });
});

describe('sandboxEligibleCreatureBrainWorkflows', () => {
    const sharedId = 'shared-id';
    const enabledId = 'enabled-id';
    const disabledId = 'disabled-id';
    const projects = [
        project({ id: sharedId, name: 'Shared', sort_order: 0, sandbox_enabled: false }),
        project({ id: enabledId, name: 'Sandbox', sort_order: 1, sandbox_enabled: true }),
        project({ id: disabledId, name: 'Gmail', sort_order: 2, sandbox_enabled: false }),
    ];
    const workflows = [
        wf({ id: 'a', project_id: sharedId }),
        wf({ id: 'b', project_id: enabledId }),
        wf({ id: 'c', project_id: disabledId }),
        wf({ id: 'd', project_id: disabledId, expose_as_custom_skill: true }),
    ];

    it('returns creature brains from Shared and sandbox-enabled projects only', () => {
        const result = sandboxEligibleCreatureBrainWorkflows(projects, sharedId, workflows);
        expect(result.map(w => w.id).sort()).toEqual(['a', 'b']);
    });
});

describe('sharedProjectIdFromProjects', () => {
    it('returns Shared project id', () => {
        expect(
            sharedProjectIdFromProjects([
                { id: 'x', name: 'Mine' } as WorkflowProject,
                { id: 'shared', name: 'Shared' } as WorkflowProject,
            ]),
        ).toBe('shared');
    });

    it('returns null when Shared is missing', () => {
        expect(sharedProjectIdFromProjects([{ id: 'x', name: 'Mine' } as WorkflowProject])).toBeNull();
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
