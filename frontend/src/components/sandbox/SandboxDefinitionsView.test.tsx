import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../../api/client';
import type { ItemDefinitionRead, RegionDefinitionRead } from '../../api/types';
import { SandboxDefinitionsView } from './SandboxDefinitionsView';

vi.mock('../../api/client', () => ({
    ApiClient: {
        listItemDefinitions: vi.fn(),
        createItemDefinition: vi.fn(),
        updateItemDefinition: vi.fn(),
        deleteItemDefinition: vi.fn(),
        listTerrainDefinitions: vi.fn(),
        listFixtureDefinitions: vi.fn(),
        listCreatureDefinitions: vi.fn(),
        listRegionDefinitions: vi.fn(),
    },
}));

const sampleItem: ItemDefinitionRead = {
    id: 'item-1',
    name: 'food_snack',
    label: 'Snack',
    default_energy: 48,
    default_color: '#FF6B6B',
    shape: 'circle',
    pickable: true,
    is_system: false,
};

const sampleRegion: RegionDefinitionRead = {
    id: 'region-1',
    name: 'target_zone',
    label: 'target',
    color: '#3B82F6',
    trigger: { enabled: false, mode: null, workflow_id: null, inputs: {} },
    is_system: false,
};

describe('SandboxDefinitionsView', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.listItemDefinitions).mockResolvedValue([sampleItem]);
        vi.mocked(ApiClient.listTerrainDefinitions).mockResolvedValue([]);
        vi.mocked(ApiClient.listFixtureDefinitions).mockResolvedValue([]);
        vi.mocked(ApiClient.listCreatureDefinitions).mockResolvedValue([]);
        vi.mocked(ApiClient.listRegionDefinitions).mockResolvedValue([]);
    });

    it('loads and displays item definition cards', async () => {
        render(
            <SandboxDefinitionsView workflows={[]} workflowProjects={[]} sharedProjectId={null} />,
        );
        await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
        expect(screen.getByText('food_snack')).toBeInTheDocument();
        expect(screen.getByText('Snack')).toBeInTheDocument();
    });

    it('opens slide-over editor when a card is clicked', async () => {
        const user = userEvent.setup();
        render(
            <SandboxDefinitionsView workflows={[]} workflowProjects={[]} sharedProjectId={null} />,
        );
        await waitFor(() => expect(screen.getByText('food_snack')).toBeInTheDocument());
        await user.click(screen.getByText('food_snack'));
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByDisplayValue('food_snack')).toBeInTheDocument();
    });

    it('creates a new item definition from the slide-over', async () => {
        const user = userEvent.setup();
        const onDefinitionsChange = vi.fn();
        vi.mocked(ApiClient.createItemDefinition).mockResolvedValue({
            ...sampleItem,
            id: 'item-2',
            name: 'new_ball',
            label: 'New Ball',
        });
        render(
            <SandboxDefinitionsView
                workflows={[]}
                workflowProjects={[]}
                sharedProjectId={null}
                onDefinitionsChange={onDefinitionsChange}
            />,
        );
        await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('button', { name: /^new$/i }));
        const nameInput = screen.getByPlaceholderText('unique_key');
        await user.type(nameInput, 'new_ball');
        await user.type(screen.getByPlaceholderText('Display label'), 'New Ball');
        await user.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() =>
            expect(ApiClient.createItemDefinition).toHaveBeenCalledWith(
                expect.objectContaining({ name: 'new_ball', label: 'New Ball' }),
            ),
        );
        await waitFor(() => expect(onDefinitionsChange).toHaveBeenCalledTimes(1));
    });

    it('region edit shows single label field and trigger section only', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.listRegionDefinitions).mockResolvedValue([sampleRegion]);
        render(
            <SandboxDefinitionsView workflows={[]} workflowProjects={[]} sharedProjectId={null} />,
        );
        await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('tab', { name: /^regions$/i }));
        await waitFor(() => expect(screen.getByText('target_zone')).toBeInTheDocument());
        await user.click(screen.getByText('target_zone'));
        const dialog = screen.getByRole('dialog');
        expect(dialog).toBeInTheDocument();
        expect(screen.getAllByDisplayValue('target')).toHaveLength(1);
        expect(screen.getByText('Trigger')).toBeInTheDocument();
        expect(screen.queryByText('Position')).not.toBeInTheDocument();
    });
});
