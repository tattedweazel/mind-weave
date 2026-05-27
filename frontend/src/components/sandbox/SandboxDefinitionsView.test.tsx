import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../../api/client';
import type {
    CreatureDefinitionRead,
    FixtureDefinitionRead,
    ItemDefinitionRead,
    RegionDefinitionRead,
    WorkflowDefinitionListItem,
    WorkflowProject,
} from '../../api/types';
import { SandboxDefinitionsView } from './SandboxDefinitionsView';

vi.mock('../../api/client', () => ({
    ApiClient: {
        listItemDefinitions: vi.fn(),
        createItemDefinition: vi.fn(),
        updateItemDefinition: vi.fn(),
        deleteItemDefinition: vi.fn(),
        listTerrainDefinitions: vi.fn(),
        listFixtureDefinitions: vi.fn(),
        createFixtureDefinition: vi.fn(),
        updateFixtureDefinition: vi.fn(),
        deleteFixtureDefinition: vi.fn(),
        listCreatureDefinitions: vi.fn(),
        createCreatureDefinition: vi.fn(),
        updateCreatureDefinition: vi.fn(),
        deleteCreatureDefinition: vi.fn(),
        listRegionDefinitions: vi.fn(),
    },
}));

const sharedProjectId = 'proj-shared';
const sandboxProjectId = 'proj-sandbox';

const workflowProjects: WorkflowProject[] = [
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
        id: sandboxProjectId,
        user_id: 'u1',
        name: 'Sandbox',
        sort_order: 1,
        sandbox_enabled: true,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
];

const workflows: WorkflowDefinitionListItem[] = [
    {
        id: 'wf-brain',
        user_id: 'u1',
        name: 'Creature Brain',
        description: null,
        project_id: sandboxProjectId,
        updated_at: '2026-06-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
    },
];

const sampleItem: ItemDefinitionRead = {
    id: 'item-1',
    name: 'food_snack',
    label: 'Snack',
    custom_metadata: { energy: 48 },
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

const sampleFixture: FixtureDefinitionRead = {
    id: 'fixture-1',
    name: 'vending_machine',
    label: 'Vending Machine',
    workflow_id: 'wf-brain',
    color: '#8B5CF6',
    is_system: false,
};

const sampleCreature: CreatureDefinitionRead = {
    id: 'creature-1',
    name: 'npc_guide',
    label: 'Guide',
    workflow_id: 'wf-brain',
    default_color: '#3B82F6',
    default_facing: 'N',
    default_inventory: [],
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

    it.each([
        ['Fixtures', /^fixtures$/i, 'fixture-workflow', ApiClient.listFixtureDefinitions] as const,
        ['Creatures', /^creatures$/i, 'creature-workflow', ApiClient.listCreatureDefinitions] as const,
    ])(
        'opens new %s definition editor with workflow select',
        async (_label, tab, selectId, listApi) => {
            const user = userEvent.setup();
            render(
                <SandboxDefinitionsView
                    workflows={workflows}
                    workflowProjects={workflowProjects}
                    sharedProjectId={sharedProjectId}
                />,
            );
            await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
            await user.click(screen.getByRole('tab', { name: tab }));
            await waitFor(() => expect(listApi).toHaveBeenCalled());
            await user.click(screen.getByRole('button', { name: /^new$/i }));
            expect(screen.getByRole('dialog')).toBeInTheDocument();
            expect(screen.getByLabelText(/workflow/i)).toBeInTheDocument();
            expect(document.getElementById(selectId)).toBeInTheDocument();
        },
    );

    it('creates a new fixture definition from the slide-over', async () => {
        const user = userEvent.setup();
        const onDefinitionsChange = vi.fn();
        vi.mocked(ApiClient.createFixtureDefinition).mockResolvedValue({
            ...sampleFixture,
            id: 'fixture-2',
            name: 'new_fixture',
            label: 'New Fixture',
        });
        render(
            <SandboxDefinitionsView
                workflows={workflows}
                workflowProjects={workflowProjects}
                sharedProjectId={sharedProjectId}
                onDefinitionsChange={onDefinitionsChange}
            />,
        );
        await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('tab', { name: /^fixtures$/i }));
        await waitFor(() => expect(ApiClient.listFixtureDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('button', { name: /^new$/i }));
        const dialog = screen.getByRole('dialog');
        const inputs = dialog.querySelectorAll('input');
        await user.type(inputs[0]!, 'new_fixture');
        await user.type(inputs[1]!, 'New Fixture');
        await user.selectOptions(screen.getByLabelText(/workflow/i), 'wf-brain');
        await user.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() =>
            expect(ApiClient.createFixtureDefinition).toHaveBeenCalledWith(
                expect.objectContaining({
                    name: 'new_fixture',
                    label: 'New Fixture',
                    workflow_id: 'wf-brain',
                }),
            ),
        );
        await waitFor(() => expect(onDefinitionsChange).toHaveBeenCalledTimes(1));
    });

    it('creates a new creature definition from the slide-over', async () => {
        const user = userEvent.setup();
        const onDefinitionsChange = vi.fn();
        vi.mocked(ApiClient.createCreatureDefinition).mockResolvedValue({
            ...sampleCreature,
            id: 'creature-2',
            name: 'new_creature',
            label: 'New Creature',
        });
        render(
            <SandboxDefinitionsView
                workflows={workflows}
                workflowProjects={workflowProjects}
                sharedProjectId={sharedProjectId}
                onDefinitionsChange={onDefinitionsChange}
            />,
        );
        await waitFor(() => expect(ApiClient.listItemDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('tab', { name: /^creatures$/i }));
        await waitFor(() => expect(ApiClient.listCreatureDefinitions).toHaveBeenCalled());
        await user.click(screen.getByRole('button', { name: /^new$/i }));
        const dialog = screen.getByRole('dialog');
        const inputs = dialog.querySelectorAll('input');
        await user.type(inputs[0]!, 'new_creature');
        await user.type(inputs[1]!, 'New Creature');
        await user.selectOptions(screen.getByLabelText(/workflow/i), 'wf-brain');
        await user.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() =>
            expect(ApiClient.createCreatureDefinition).toHaveBeenCalledWith(
                expect.objectContaining({
                    name: 'new_creature',
                    label: 'New Creature',
                    workflow_id: 'wf-brain',
                    default_inventory: [],
                }),
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
