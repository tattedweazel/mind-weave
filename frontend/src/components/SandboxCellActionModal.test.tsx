import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { CreatureDefinitionRead, ItemDefinitionRead, TerrainDefinitionRead, WorkflowDefinitionListItem, WorkflowProject } from '../api/types';
import type { CellOccupants } from '../sandbox/sandboxCellOccupants';
import { projectsWithSandboxCreatureBrains } from '../domain/workflowProjectMembership';
import { SandboxCellActionModal } from './SandboxCellActionModal';

const sharedProjectId = 'proj-shared';
const alphaProjectId = 'proj-alpha';
const emptyProjectId = 'proj-empty';

const workflowProjects: WorkflowProject[] = [
    {
        id: sharedProjectId,
        user_id: 'u1',
        name: 'Shared',
        sort_order: 0,
        sandbox_enabled: false,
        workflow_count: 2,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: alphaProjectId,
        user_id: 'u1',
        name: 'Alpha',
        sort_order: 1,
        sandbox_enabled: true,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: emptyProjectId,
        user_id: 'u1',
        name: 'Empty',
        sort_order: 2,
        sandbox_enabled: true,
        workflow_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: 'proj-gmail',
        user_id: 'u1',
        name: 'Gmail',
        sort_order: 3,
        sandbox_enabled: false,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
];

const creatureBrainWorkflows: WorkflowDefinitionListItem[] = [
    {
        id: 'wf-shared',
        user_id: 'u1',
        name: 'Shared Brain',
        description: null,
        project_id: sharedProjectId,
        updated_at: '2026-06-01T00:00:00Z',
    },
    {
        id: 'wf-orphan',
        user_id: 'u1',
        name: 'Orphan Brain',
        description: null,
        project_id: null,
        updated_at: '2026-05-01T00:00:00Z',
    },
    {
        id: 'wf-alpha',
        user_id: 'u1',
        name: 'Alpha Brain',
        description: null,
        project_id: alphaProjectId,
        updated_at: '2026-04-01T00:00:00Z',
    },
    {
        id: 'wf-gmail',
        user_id: 'u1',
        name: 'Gmail Brain',
        description: null,
        project_id: 'proj-gmail',
        updated_at: '2026-04-02T00:00:00Z',
    },
    {
        id: 'wf-skill',
        user_id: 'u1',
        name: 'Hidden Skill',
        description: null,
        project_id: alphaProjectId,
        expose_as_custom_skill: true,
        updated_at: '2026-03-01T00:00:00Z',
    },
];

const emptyOccupants: CellOccupants = { items: [], creatures: [] };

const itemOccupants: CellOccupants = {
    items: [{ id: 'w1', type: 'wall', position: { x: 2, y: 3 } }],
    creatures: [],
};

const creatureOccupants: CellOccupants = {
    items: [],
    creatures: [
        {
            id: 'c1',
            workflow_id: 'wf-1',
            position: { x: 2, y: 3 },
            facing: 'N',
        },
    ],
};

const bothOccupants: CellOccupants = {
    items: [{ id: 'f1', type: 'food', position: { x: 2, y: 3 }, energy: 25 }],
    creatures: [
        {
            id: 'c1',
            workflow_id: 'wf-1',
            position: { x: 2, y: 3 },
            facing: 'N',
        },
    ],
};

function renderModal(
    props: Partial<ComponentProps<typeof SandboxCellActionModal>> & {
        cell?: { x: number; y: number };
    } = {},
) {
    const {
        cell = { x: 2, y: 3 },
        occupants = emptyOccupants,
        allowCreatureActions = true,
        onComplete = vi.fn(),
        onDismiss = vi.fn(),
        ...rest
    } = props;

    return render(
        <SandboxCellActionModal
            cell={cell}
            occupants={occupants}
            allowCreatureActions={allowCreatureActions}
            onComplete={onComplete}
            onDismiss={onDismiss}
            {...rest}
        />,
    );
}

const creatureDefinitions: CreatureDefinitionRead[] = [
    {
        id: 'creature-def-1',
        name: 'Scout',
        label: 'Scout',
        workflow_id: 'wf-alpha',
        default_color: '#22C55E',
        default_facing: 'E',
        default_inventory: [],
        is_system: false,
    },
];

const userItemDefinition: ItemDefinitionRead = {
    id: 'item-user-1',
    name: 'custom_snack',
    label: 'Custom Snack',
    default_energy: 32,
    default_color: '#FF6B6B',
    shape: 'circle',
    pickable: true,
    is_system: false,
};

const systemItemDefinition: ItemDefinitionRead = {
    id: 'item-system-1',
    name: 'builtin-food',
    label: 'Food',
    default_energy: 48,
    default_color: null,
    shape: 'circle',
    pickable: true,
    is_system: true,
};

const userTerrainDefinition: TerrainDefinitionRead = {
    id: 'terrain-user-1',
    name: 'custom_wall',
    label: 'Custom Wall',
    default_color: '#64748B',
    shape: 'rect',
    is_system: false,
};

const systemTerrainDefinition: TerrainDefinitionRead = {
    id: 'terrain-system-1',
    name: 'builtin-wall',
    label: 'Wall',
    default_color: '#64748B',
    shape: 'rect',
    is_system: true,
};

async function openPlaceItemMenu(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /^Place item/ }));
}

async function openBuiltInsMenu(user: ReturnType<typeof userEvent.setup>) {
    await openPlaceItemMenu(user);
    await user.click(screen.getByRole('button', { name: /^Built-ins/ }));
}

describe('SandboxCellActionModal', () => {
    it('shows place actions on empty cell', () => {
        renderModal();

        expect(screen.getByRole('button', { name: /^Place region/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Place item/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Place creature/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: /^Remove item/ })).toBeNull();
        expect(screen.queryByRole('button', { name: /^Remove creature/ })).toBeNull();
    });

    it('shows remove_item on item cell and still allows place_region', () => {
        renderModal({ occupants: itemOccupants, canInspect: true, onInspect: vi.fn() });

        expect(screen.getByRole('button', { name: /^Inspect/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Place region/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Remove item/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: /^Place item/ })).toBeNull();
        expect(screen.queryByRole('button', { name: /^Place creature/ })).toBeNull();
        expect(screen.queryByRole('button', { name: /^Remove creature/ })).toBeNull();
    });

    it('shows remove_creature on creature cell and still allows place_region', () => {
        renderModal({ occupants: creatureOccupants, canInspect: true, onInspect: vi.fn() });

        expect(screen.getByRole('button', { name: /^Inspect/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Place region/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Remove creature/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: /^Place item/ })).toBeNull();
        expect(screen.queryByRole('button', { name: /^Remove item/ })).toBeNull();
    });

    it('shows both remove actions when item and creature share cell', () => {
        renderModal({ occupants: bothOccupants, canInspect: true, onInspect: vi.fn() });

        expect(screen.getByRole('button', { name: /^Remove item/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Remove creature/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Place region/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: /^Place item/ })).toBeNull();
    });

    it('completes remove_item when Remove item is chosen', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({ occupants: itemOccupants, onComplete });

        await user.click(screen.getByRole('button', { name: /^Remove item/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'remove_item',
            cell: { x: 2, y: 3 },
            item_id: 'w1',
        });
    });

    it('shows place_item and remove_fixture on fixture-only cell', () => {
        renderModal({
            occupants: {
                items: [
                    {
                        id: 'fx1',
                        type: 'fixture',
                        definition_id: 'def-1',
                        definition_kind: 'fixture',
                        role: 'solid',
                        position: { x: 2, y: 3 },
                    },
                ],
                creatures: [],
            },
        });

        expect(screen.getByRole('button', { name: /^Place item/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Remove fixture/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: /^Remove item/ })).toBeNull();
    });

    it('opens remove picker when multiple removable items share a cell', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({
            occupants: {
                items: [
                    { id: 'f1', type: 'food', position: { x: 2, y: 3 }, energy: 25 },
                    { id: 'b1', type: 'ball', position: { x: 2, y: 3 }, color: '#AABBCC' },
                ],
                creatures: [],
            },
            onComplete,
        });

        await user.click(screen.getByRole('button', { name: /^Remove item/ }));
        expect(screen.getByRole('button', { name: /^Food \(25\)$/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Ball \(#AABBCC\)$/ })).toBeTruthy();
        expect(screen.getByRole('button', { name: /^Remove all/ })).toBeTruthy();
        expect(onComplete).not.toHaveBeenCalled();
    });

    it('completes targeted remove_item from picker', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({
            occupants: {
                items: [
                    { id: 'f1', type: 'food', position: { x: 2, y: 3 }, energy: 25 },
                    { id: 'b1', type: 'ball', position: { x: 2, y: 3 }, color: '#AABBCC' },
                ],
                creatures: [],
            },
            onComplete,
        });

        await user.click(screen.getByRole('button', { name: /^Remove item/ }));
        await user.click(screen.getByRole('button', { name: /^Food \(25\)$/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'remove_item',
            cell: { x: 2, y: 3 },
            item_id: 'f1',
        });
    });

    it('completes place_item after Ball color is confirmed', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({
            cell: { x: 1, y: 1 },
            onComplete,
            sandboxFavoriteColors: ['#00FF00'],
        });

        await openBuiltInsMenu(user);
        await user.click(screen.getByRole('button', { name: /^Ball/ }));
        await user.click(screen.getByRole('button', { name: /Place ball \(#00FF00\)/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_item',
            cell: { x: 1, y: 1 },
            item_type: 'ball',
            color: '#00FF00',
        });
    });

    it('completes place_item after Food is chosen', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({ cell: { x: 1, y: 1 }, onComplete });

        await openBuiltInsMenu(user);
        await user.click(screen.getByRole('button', { name: /^Food/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_item',
            cell: { x: 1, y: 1 },
            item_type: 'food',
        });
    });

    describe('place item source menu', () => {
        it('shows Item, Terrain, and Built-ins in order', async () => {
            const user = userEvent.setup();
            renderModal();

            await openPlaceItemMenu(user);

            expect(screen.getByText('Place item')).toBeTruthy();
            const labels = screen
                .getAllByRole('button')
                .map(btn => btn.querySelector('.text-sm.font-medium')?.textContent)
                .filter((label): label is string => label === 'Item' || label === 'Terrain' || label === 'Built-ins');
            expect(labels).toEqual(['Item', 'Terrain', 'Built-ins']);
        });

        it('lists only user item definitions and excludes seeded built-ins', async () => {
            const user = userEvent.setup();
            renderModal({
                itemDefinitions: [userItemDefinition, systemItemDefinition],
            });

            await openPlaceItemMenu(user);
            await user.click(screen.getByRole('button', { name: /^Item/ }));

            expect(screen.getByRole('button', { name: /custom_snack/ })).toBeTruthy();
            expect(screen.queryByRole('button', { name: /builtin-food/ })).toBeNull();
        });

        it('lists only user terrain definitions and excludes seeded built-ins', async () => {
            const user = userEvent.setup();
            renderModal({
                terrainDefinitions: [userTerrainDefinition, systemTerrainDefinition],
            });

            await openPlaceItemMenu(user);
            await user.click(screen.getByRole('button', { name: /^Terrain/ }));

            expect(screen.getByRole('button', { name: /custom_wall/ })).toBeTruthy();
            expect(screen.queryByRole('button', { name: /builtin-wall/ })).toBeNull();
        });

        it('shows empty item list when only system definitions exist', async () => {
            const user = userEvent.setup();
            renderModal({
                itemDefinitions: [systemItemDefinition],
            });

            await openPlaceItemMenu(user);
            await user.click(screen.getByRole('button', { name: /^Item/ }));

            expect(screen.getByText('No item definitions available.')).toBeTruthy();
            expect(screen.queryByRole('button', { name: /builtin-food/ })).toBeNull();
        });

        it('completes place_item from user item definition', async () => {
            const user = userEvent.setup();
            const onComplete = vi.fn();
            renderModal({
                cell: { x: 2, y: 3 },
                onComplete,
                itemDefinitions: [userItemDefinition],
            });

            await openPlaceItemMenu(user);
            await user.click(screen.getByRole('button', { name: /^Item/ }));
            await user.click(screen.getByRole('button', { name: /custom_snack/ }));

            expect(onComplete).toHaveBeenCalledWith({
                type: 'place_item',
                cell: { x: 2, y: 3 },
                definition_id: 'item-user-1',
                color: '#FF6B6B',
                energy: 32,
            });
        });
    });

    it('completes place_region after color and label steps', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({
            cell: { x: 1, y: 1 },
            onComplete,
            sandboxFavoriteColors: ['#FF0000'],
        });

        await user.click(screen.getByRole('button', { name: /^Place region/ }));
        await user.click(screen.getByRole('button', { name: /Next: label/i }));
        await user.type(screen.getByLabelText('Region label'), 'target');
        await user.click(screen.getByRole('button', { name: /Place region \(#FF0000\)/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_region',
            cell: { x: 1, y: 1 },
            color: '#FF0000',
            label: 'target',
        });
    });

    it('calls onDismiss when Escape is pressed', async () => {
        const user = userEvent.setup();
        const onDismiss = vi.fn();
        renderModal({ cell: { x: 0, y: 0 }, onDismiss });

        await user.keyboard('{Escape}');
        expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it('shows Inspect when canInspect and calls onInspect without onComplete', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        const onInspect = vi.fn();
        renderModal({ occupants: itemOccupants, canInspect: true, onInspect, onComplete });

        await user.click(screen.getByRole('button', { name: /^Inspect/ }));
        expect(onInspect).toHaveBeenCalledTimes(1);
        expect(onComplete).not.toHaveBeenCalled();
    });

    it('does not show Inspect when canInspect is false', () => {
        renderModal({ occupants: itemOccupants, canInspect: false, onInspect: vi.fn() });

        expect(screen.queryByRole('button', { name: /^Inspect/ })).toBeNull();
    });

    describe('place creature from definition', () => {
        it('shows creature definition picker when definitions exist', async () => {
            const user = userEvent.setup();
            renderModal({ creatureDefinitions });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));

            expect(screen.getByText('Creature definition')).toBeTruthy();
            expect(screen.getByRole('button', { name: /Scout/ })).toBeTruthy();
            expect(screen.queryByText('Project')).toBeNull();
        });

        it('completes place_creature from selected definition', async () => {
            const user = userEvent.setup();
            const onComplete = vi.fn();
            renderModal({
                cell: { x: 3, y: 4 },
                onComplete,
                creatureDefinitions,
            });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            await user.click(screen.getByRole('button', { name: /Scout/ }));

            expect(onComplete).toHaveBeenCalledWith({
                type: 'place_creature',
                cell: { x: 3, y: 4 },
                workflow_id: 'wf-alpha',
                name: 'Scout',
                facing: 'E',
                color: '#22C55E',
                creature_definition_id: 'creature-def-1',
            });
        });

        it('navigates back from creature definition picker to actions', async () => {
            const user = userEvent.setup();
            renderModal({ creatureDefinitions });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            expect(screen.getByText('Creature definition')).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Back' }));
            expect(screen.getByRole('button', { name: /^Place creature/ })).toBeTruthy();
        });
    });

    describe('place creature project → workflow picker', () => {
        const pickerProps = {
            workflowProjects: projectsWithSandboxCreatureBrains(workflowProjects, sharedProjectId, creatureBrainWorkflows),
            workflows: creatureBrainWorkflows,
            sharedProjectId,
        };

        it('shows project list with counts and omits empty and sandbox-disabled projects', async () => {
            const user = userEvent.setup();
            renderModal(pickerProps);

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));

            expect(screen.getByText('Project')).toBeTruthy();
            expect(screen.getByRole('button', { name: /Shared/ })).toBeTruthy();
            expect(screen.getByRole('button', { name: /Alpha/ })).toBeTruthy();
            expect(screen.queryByRole('button', { name: /Empty/ })).toBeNull();
            expect(screen.queryByRole('button', { name: /Gmail/ })).toBeNull();
            expect(screen.getByRole('button', { name: /Shared/ }).textContent).toContain('2');
            expect(screen.getByRole('button', { name: /Alpha/ }).textContent).toContain('1');
        });

        it('drills into workflows with filter and sort, then completes place_creature', async () => {
            const user = userEvent.setup();
            const onComplete = vi.fn();
            renderModal({ ...pickerProps, cell: { x: 4, y: 5 }, onComplete });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            await user.click(screen.getByRole('button', { name: /Shared/ }));

            expect(screen.getByRole('heading', { name: 'Shared' })).toBeTruthy();
            expect(screen.getByRole('button', { name: 'Shared Brain' })).toBeTruthy();
            expect(screen.getByRole('button', { name: 'Orphan Brain' })).toBeTruthy();
            expect(screen.queryByRole('button', { name: 'Hidden Skill' })).toBeNull();

            await user.click(screen.getByRole('button', { name: 'Name A–Z' }));
            await user.type(screen.getByRole('searchbox', { name: 'Filter workflows' }), 'Orphan');
            expect(screen.queryByRole('button', { name: 'Shared Brain' })).toBeNull();
            expect(screen.getByRole('button', { name: 'Orphan Brain' })).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Orphan Brain' }));
            await user.click(screen.getByRole('button', { name: 'Continue' }));
            await user.click(screen.getByRole('button', { name: /Place creature \(#3B82F6\)/ }));
            expect(onComplete).toHaveBeenCalledWith({
                type: 'place_creature',
                cell: { x: 4, y: 5 },
                workflow_id: 'wf-orphan',
                facing: 'N',
                color: '#3B82F6',
            });
        });

        it('includes selected facing and favorite color when placing a creature', async () => {
            const user = userEvent.setup();
            const onComplete = vi.fn();
            renderModal({
                ...pickerProps,
                cell: { x: 1, y: 2 },
                onComplete,
                sandboxFavoriteColors: ['#FF0000'],
            });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            await user.click(screen.getByRole('button', { name: /Shared/ }));
            await user.click(screen.getByRole('button', { name: 'Shared Brain' }));
            await user.click(screen.getByRole('button', { name: 'Face E' }));
            await user.click(screen.getByRole('button', { name: 'Continue' }));
            await user.click(screen.getByRole('button', { name: /Place creature \(#FF0000\)/ }));

            expect(onComplete).toHaveBeenCalledWith({
                type: 'place_creature',
                cell: { x: 1, y: 2 },
                workflow_id: 'wf-shared',
                facing: 'E',
                color: '#FF0000',
            });
        });

        it('does not show facing picker on workflow step', async () => {
            const user = userEvent.setup();
            renderModal(pickerProps);

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            await user.click(screen.getByRole('button', { name: /Shared/ }));

            expect(screen.queryByRole('button', { name: 'Face N' })).toBeNull();
        });

        it('navigates back from color to facing to workflow to project to actions', async () => {
            const user = userEvent.setup();
            renderModal(pickerProps);

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            await user.click(screen.getByRole('button', { name: /Alpha/ }));
            await user.click(screen.getByRole('button', { name: 'Alpha Brain' }));
            await user.click(screen.getByRole('button', { name: 'Continue' }));
            expect(screen.getByText('Creature color')).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Back' }));
            expect(screen.getByText('Initial facing')).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Back' }));
            expect(screen.getByRole('heading', { name: 'Alpha' })).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Back' }));
            expect(screen.getByText('Project')).toBeTruthy();

            await user.click(screen.getByRole('button', { name: 'Back' }));
            expect(screen.getByRole('button', { name: /^Place creature/ })).toBeTruthy();
        });

        it('shows empty state when no projects have creature brains', async () => {
            const user = userEvent.setup();
            renderModal({ workflowProjects: [], workflows: [], sharedProjectId: null });

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));
            expect(screen.getByText('No workflows available. Create one in Build first.')).toBeTruthy();
        });
    });
});
