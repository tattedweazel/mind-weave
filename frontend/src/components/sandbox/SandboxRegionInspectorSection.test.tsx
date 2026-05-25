import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../../api/types';
import type { SandboxItemJson } from '../../domain/sandbox/types';
import { SandboxRegionInspectorSection } from './SandboxRegionInspectorSection';

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

const regionItem: SandboxItemJson = {
    id: 'region-1',
    type: 'region',
    position: { x: 1, y: 2 },
    color: '#3B82F6',
    label: 'target',
    trigger: { enabled: true, mode: 'enter', workflow_id: null, inputs: {} },
};

const pickerProps = {
    workflows: allWorkflows,
    workflowProjects: projects,
    sharedProjectId,
};

describe('SandboxRegionInspectorSection', () => {
    it('lists only sandbox-eligible workflows grouped by project in trigger dropdown', () => {
        render(
            <SandboxRegionInspectorSection
                item={regionItem}
                readOnly={false}
                {...pickerProps}
                onItemChange={vi.fn()}
            />,
        );

        const select = screen.getByLabelText('Workflow') as HTMLSelectElement;
        const optgroups = Array.from(select.querySelectorAll('optgroup'));
        expect(optgroups.map(g => g.label)).toEqual(['Shared', 'Sandbox']);

        const optionLabels = Array.from(select.options).map(o => o.textContent);
        expect(optionLabels).toContain('None');
        expect(optionLabels).toContain('Shared Brain');
        expect(optionLabels).toContain('Sandbox Brain');
        expect(optionLabels).not.toContain('Gmail Brain');
    });

    it('shows orphan option when trigger workflow is no longer eligible', () => {
        render(
            <SandboxRegionInspectorSection
                item={{
                    ...regionItem,
                    trigger: { enabled: true, mode: 'enter', workflow_id: 'wf-disabled', inputs: {} },
                }}
                readOnly
                {...pickerProps}
                onItemChange={vi.fn()}
            />,
        );

        const select = screen.getByLabelText('Workflow') as HTMLSelectElement;
        expect(select.value).toBe('wf-disabled');
        expect(screen.getByRole('option', { name: 'Gmail Brain (unavailable)' })).toBeDisabled();
    });

    it('definition variant shows trigger fields only', () => {
        render(
            <SandboxRegionInspectorSection
                item={regionItem}
                readOnly={false}
                variant="definition"
                {...pickerProps}
                onItemChange={vi.fn()}
            />,
        );

        expect(screen.getByText('Trigger')).toBeInTheDocument();
        expect(screen.getByLabelText('Trigger enabled')).toBeInTheDocument();
        expect(screen.queryByText('Id')).not.toBeInTheDocument();
        expect(screen.queryByText('Position')).not.toBeInTheDocument();
        expect(screen.queryByLabelText('Label')).not.toBeInTheDocument();
    });
});
