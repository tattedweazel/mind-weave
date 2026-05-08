import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiClient } from '../api/client';
import type { Companion } from '../api/types';
import { CompanionSettingsModal } from './CompanionSettingsModal';

vi.mock('../api/client', () => ({
    ApiClient: {
        getPersonas: vi.fn(),
        getWorkflows: vi.fn(),
        updateCompanion: vi.fn(),
    },
}));

const baseCompanion: Companion = {
    id: 'c1',
    owner_user_id: 'u1',
    name: 'Old',
    description: '',
    persona_id: 'p1',
    identity_profile: {},
    default_mode: 'default',
    available_modes: ['default'],
    enabled_workflow_ids: [],
    memory_policy: { approval_required: true },
    created_at: '2020-01-01T00:00:00Z',
    updated_at: '2020-01-01T00:00:00Z',
};

describe('CompanionSettingsModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.getPersonas).mockResolvedValue([]);
        vi.mocked(ApiClient.getWorkflows).mockResolvedValue([]);
    });

    it('calls updateCompanion with name patch and onSaved when display name changes', async () => {
        const user = userEvent.setup();
        const onSaved = vi.fn();
        const updated: Companion = { ...baseCompanion, name: 'NewName' };
        vi.mocked(ApiClient.updateCompanion).mockResolvedValue(updated);

        render(
            <CompanionSettingsModal
                isOpen
                onClose={() => {}}
                companion={baseCompanion}
                workspaceEnabledWorkflowIds={[]}
                onSaved={onSaved}
            />,
        );

        await waitFor(() => expect(ApiClient.getPersonas).toHaveBeenCalled());
        const input = screen.getByLabelText(/Display name/i);
        await user.clear(input);
        await user.type(input, 'NewName');
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        await waitFor(() => {
            expect(ApiClient.updateCompanion).toHaveBeenCalledWith({ name: 'NewName' });
        });
        expect(onSaved).toHaveBeenCalledWith(updated);
    });

    it('closes without calling updateCompanion when nothing changed', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();

        render(
            <CompanionSettingsModal
                isOpen
                onClose={onClose}
                companion={baseCompanion}
                workspaceEnabledWorkflowIds={[]}
                onSaved={vi.fn()}
            />,
        );

        await waitFor(() => expect(ApiClient.getPersonas).toHaveBeenCalled());
        await user.click(screen.getByRole('button', { name: /^Save$/i }));

        expect(ApiClient.updateCompanion).not.toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
    });
});
