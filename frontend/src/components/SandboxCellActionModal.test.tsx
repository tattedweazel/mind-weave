import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { WorkflowDefinitionListItem, WorkflowProject } from '../api/types';
import type { CellOccupants } from '../sandbox/sandboxCellOccupants';
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
        workflow_count: 2,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: alphaProjectId,
        user_id: 'u1',
        name: 'Alpha',
        sort_order: 1,
        workflow_count: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
    },
    {
        id: emptyProjectId,
        user_id: 'u1',
        name: 'Empty',
        sort_order: 2,
        workflow_count: 0,
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
        });
    });

    it('completes place_item after Food is chosen', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({ cell: { x: 1, y: 1 }, onComplete });

        await user.click(screen.getByRole('button', { name: /^Place item/ }));
        await user.click(screen.getByRole('button', { name: /^Food/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_item',
            cell: { x: 1, y: 1 },
            item_type: 'food',
        });
    });

    it('completes place_region after color is confirmed', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        renderModal({
            cell: { x: 1, y: 1 },
            onComplete,
            sandboxFavoriteColors: ['#FF0000'],
        });

        await user.click(screen.getByRole('button', { name: /^Place region/ }));
        await user.click(screen.getByRole('button', { name: /Place region \(#FF0000\)/ }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_region',
            cell: { x: 1, y: 1 },
            color: '#FF0000',
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

    describe('place creature project → workflow picker', () => {
        const pickerProps = {
            workflowProjects: workflowProjects.filter(
                p => p.id === sharedProjectId || p.id === alphaProjectId,
            ),
            workflows: creatureBrainWorkflows,
            sharedProjectId,
        };

        it('shows project list with counts and omits empty projects', async () => {
            const user = userEvent.setup();
            renderModal(pickerProps);

            await user.click(screen.getByRole('button', { name: /^Place creature/ }));

            expect(screen.getByText('Project')).toBeTruthy();
            expect(screen.getByRole('button', { name: /Shared/ })).toBeTruthy();
            expect(screen.getByRole('button', { name: /Alpha/ })).toBeTruthy();
            expect(screen.queryByRole('button', { name: /Empty/ })).toBeNull();
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
