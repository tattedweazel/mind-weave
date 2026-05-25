import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../../api/types';
import { SandboxWorkflowSelect } from './SandboxWorkflowSelect';

const sharedProjectId = 'proj-shared';
const enabledProjectId = 'proj-enabled';
const disabledProjectId = 'proj-disabled';

const projects: WorkflowProject[] = [
    {
        id: sharedProjectId,
        user_id: 'u1',
        name: 'Shared',
        sort_order: 0,
        sandbox_enabled: false,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: enabledProjectId,
        user_id: 'u1',
        name: 'Sandbox',
        sort_order: 1,
        sandbox_enabled: true,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: disabledProjectId,
        user_id: 'u1',
        name: 'Gmail',
        sort_order: 2,
        sandbox_enabled: false,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
];

const allWorkflows: WorkflowDefinitionListItem[] = [
    {
        id: 'wf-shared',
        user_id: 'u1',
        name: 'Shared Brain',
        description: null,
        project_id: sharedProjectId,
        updated_at: '2026-06-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
    },
    {
        id: 'wf-enabled',
        user_id: 'u1',
        name: 'Sandbox Brain',
        description: null,
        project_id: enabledProjectId,
        updated_at: '2026-05-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
    },
    {
        id: 'wf-disabled',
        user_id: 'u1',
        name: 'Gmail Brain',
        description: null,
        project_id: disabledProjectId,
        updated_at: '2026-04-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
    },
];

describe('SandboxWorkflowSelect', () => {
    it('groups sandbox-eligible workflows by project', () => {
        render(
            <SandboxWorkflowSelect
                id="wf-select"
                value=""
                onChange={vi.fn()}
                workflows={allWorkflows}
                workflowProjects={projects}
                sharedProjectId={sharedProjectId}
                emptyOptionLabel="None"
            />,
        );

        const select = screen.getByRole('combobox') as HTMLSelectElement;
        const optgroups = Array.from(select.querySelectorAll('optgroup'));
        expect(optgroups.map(g => g.label)).toEqual(['Shared', 'Sandbox']);

        const optionLabels = Array.from(select.options).map(o => o.textContent);
        expect(optionLabels).toContain('None');
        expect(optionLabels).toContain('Shared Brain');
        expect(optionLabels).toContain('Sandbox Brain');
        expect(optionLabels).not.toContain('Gmail Brain');
    });

    it('shows eligibility hint when requested', () => {
        render(
            <SandboxWorkflowSelect
                id="wf-select"
                value=""
                onChange={vi.fn()}
                workflows={allWorkflows}
                workflowProjects={projects}
                sharedProjectId={sharedProjectId}
                emptyOptionLabel="Select workflow…"
                showEligibilityHint
            />,
        );

        expect(screen.getByText(/sandbox-enabled projects/i)).toBeInTheDocument();
    });

    it('shows orphan option for ineligible selected workflow', () => {
        render(
            <SandboxWorkflowSelect
                id="wf-select"
                value="wf-disabled"
                onChange={vi.fn()}
                workflows={allWorkflows}
                workflowProjects={projects}
                sharedProjectId={sharedProjectId}
                emptyOptionLabel="None"
            />,
        );

        const select = screen.getByRole('combobox') as HTMLSelectElement;
        expect(select.value).toBe('wf-disabled');
        expect(screen.getByRole('option', { name: 'Gmail Brain (unavailable)' })).toBeDisabled();
    });
});
