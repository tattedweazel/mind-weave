import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiClient } from '../api/client';
import type { Workspace } from '../api/types';
import { WorkspaceSettingsModal } from './WorkspaceSettingsModal';

vi.mock('../api/client', () => ({
    ApiClient: {
        getWorkflows: vi.fn(),
        getModels: vi.fn(),
        getGoogleWorkflowConnections: vi.fn(),
        updateWorkspace: vi.fn(),
    },
}));

const baseWorkspace: Workspace = {
    id: 'w1',
    owner_user_id: 'u1',
    name: 'Companion Chat',
    runtime_configuration: {},
    ui_configuration: {},
    interaction_configuration: {},
    enabled_workflow_ids: ['550e8400-e29b-41d4-a716-446655440001'],
    created_at: '2020-01-01T00:00:00Z',
    updated_at: '2020-01-01T00:00:00Z',
};

describe('WorkspaceSettingsModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.getWorkflows).mockResolvedValue([
            {
                id: '550e8400-e29b-41d4-a716-446655440001',
                user_id: 'u1',
                name: 'Test WF',
                description: null,
                expose_as_custom_skill: false,
            },
        ]);
        vi.mocked(ApiClient.getModels).mockResolvedValue({ local: ['planning-model-a'], external: [] });
        vi.mocked(ApiClient.getGoogleWorkflowConnections).mockResolvedValue([
            {
                id: '660e8400-e29b-41d4-a716-446655440099',
                google_email: 'a@example.com',
                label: 'Work',
                scopes: 'email',
                created_at: '2020-01-01T00:00:00Z',
                updated_at: '2020-01-01T00:00:00Z',
            },
        ]);
    });

    it('calls updateWorkspace when unchecking a workflow and saving', async () => {
        const user = userEvent.setup();
        const onSaved = vi.fn();
        const updated: Workspace = { ...baseWorkspace, enabled_workflow_ids: [] };
        vi.mocked(ApiClient.updateWorkspace).mockResolvedValue(updated);

        render(
            <WorkspaceSettingsModal
                isOpen
                onClose={() => {}}
                workspace={baseWorkspace}
                onSaved={onSaved}
            />,
        );

        await waitFor(() => {
            expect(ApiClient.getWorkflows).toHaveBeenCalled();
            expect(ApiClient.getModels).toHaveBeenCalled();
            expect(ApiClient.getGoogleWorkflowConnections).toHaveBeenCalled();
        });
        const checkbox = screen.getByRole('checkbox', { name: /Test WF/i });
        await user.click(checkbox);
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        await waitFor(() => {
            expect(ApiClient.updateWorkspace).toHaveBeenCalledWith('w1', { enabled_workflow_ids: [] });
        });
        expect(onSaved).toHaveBeenCalledWith(updated);
    });

    it('closes without calling updateWorkspace when selection unchanged', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();

        render(
            <WorkspaceSettingsModal
                isOpen
                onClose={onClose}
                workspace={baseWorkspace}
                onSaved={vi.fn()}
            />,
        );

        await waitFor(() => {
            expect(ApiClient.getWorkflows).toHaveBeenCalled();
            expect(ApiClient.getModels).toHaveBeenCalled();
            expect(ApiClient.getGoogleWorkflowConnections).toHaveBeenCalled();
        });
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        expect(ApiClient.updateWorkspace).not.toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
    });

    it('sends interpretation_model when planning model is changed', async () => {
        const user = userEvent.setup();
        const onSaved = vi.fn();
        const updated: Workspace = {
            ...baseWorkspace,
            interpretation_model: 'planning-model-a',
        };
        vi.mocked(ApiClient.updateWorkspace).mockResolvedValue(updated);

        render(
            <WorkspaceSettingsModal
                isOpen
                onClose={() => {}}
                workspace={baseWorkspace}
                onSaved={onSaved}
            />,
        );

        await waitFor(() => expect(ApiClient.getModels).toHaveBeenCalled());
        await user.selectOptions(screen.getByLabelText(/Planning model/i), 'planning-model-a');
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        await waitFor(() => {
            expect(ApiClient.updateWorkspace).toHaveBeenCalledWith('w1', {
                interpretation_model: 'planning-model-a',
            });
        });
        expect(onSaved).toHaveBeenCalledWith(updated);
    });

    it('sends default_google_workflow_connection_id when default Google connection changes', async () => {
        const user = userEvent.setup();
        const onSaved = vi.fn();
        const gid = '660e8400-e29b-41d4-a716-446655440099';
        const updated: Workspace = { ...baseWorkspace, default_google_workflow_connection_id: gid };
        vi.mocked(ApiClient.updateWorkspace).mockResolvedValue(updated);

        render(
            <WorkspaceSettingsModal
                isOpen
                onClose={() => {}}
                workspace={baseWorkspace}
                onSaved={onSaved}
            />,
        );

        await waitFor(() => expect(ApiClient.getGoogleWorkflowConnections).toHaveBeenCalled());
        await user.selectOptions(screen.getByLabelText(/Default Google workflow connection/i), gid);
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        await waitFor(() => {
            expect(ApiClient.updateWorkspace).toHaveBeenCalledWith('w1', {
                default_google_workflow_connection_id: gid,
            });
        });
        expect(onSaved).toHaveBeenCalledWith(updated);
    });
});
