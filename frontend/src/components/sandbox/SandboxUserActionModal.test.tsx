import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SandboxCreatureJson, SandboxSandboxStateJson } from '../../domain/sandbox/types';
import * as sandboxSensoryProbes from '../../sandbox/sandboxSensoryProbes';
import { SandboxUserActionModal } from './SandboxUserActionModal';

vi.mock('../../sandbox/sandboxSensoryProbes', async importOriginal => {
    const actual = await importOriginal<typeof sandboxSensoryProbes>();
    return {
        ...actual,
        runSensoryProbe: vi.fn(actual.runSensoryProbe),
    };
});

const creature: SandboxCreatureJson = {
    id: 'c1',
    workflow_id: 'wf1',
    name: 'Scout',
    position: { x: 2, y: 2 },
    facing: 'N',
    color: '#3B82F6',
};

const sandboxState: SandboxSandboxStateJson = {
    tick: 3,
    creatures: [creature],
    world: { grid: { width: 5, height: 5 }, items: [] },
    recent_actions: [],
};

describe('SandboxUserActionModal', () => {
    beforeEach(() => {
        vi.mocked(sandboxSensoryProbes.runSensoryProbe).mockClear();
    });

    it('confirms move_forward on button click', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={onConfirm}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /forward/i }));
        await user.click(screen.getByRole('button', { name: /^confirm$/i }));
        expect(onConfirm).toHaveBeenCalledWith({ action: 'move_forward' });
    });

    it('hides Place when inventory is empty', () => {
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        expect(screen.queryByRole('button', { name: /^place$/i })).not.toBeInTheDocument();
    });

    it('hides Pick up when forward cell has nothing pickable', () => {
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        expect(screen.queryByRole('button', { name: /^pick up$/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('group', { name: 'Inventory actions' })).not.toBeInTheDocument();
    });

    it('shows Pick up when forward cell has food or ball', () => {
        const stateWithFood: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [{ id: 'f1', type: 'food', position: { x: 2, y: 1 }, energy: 10 }],
            },
        };
        const { unmount } = render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={stateWithFood}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        expect(screen.getByRole('button', { name: /^pick up$/i })).toBeInTheDocument();
        unmount();

        const stateWithBall: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [{ id: 'b1', type: 'ball', position: { x: 2, y: 1 }, color: '#AABBCC' }],
            },
        };
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={stateWithBall}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        expect(screen.getByRole('button', { name: /^pick up$/i })).toBeInTheDocument();
    });

    it('confirms pick_up_item when Pick up is available', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();
        const stateWithFood: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [{ id: 'f1', type: 'food', position: { x: 2, y: 1 }, energy: 10 }],
            },
        };
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={stateWithFood}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={onConfirm}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^pick up$/i }));
        await user.click(screen.getByRole('button', { name: /^confirm$/i }));
        expect(onConfirm).toHaveBeenCalledWith({ action: 'pick_up_item' });
    });

    it('requires inventory selection and empty forward cell before confirm for place_item', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();
        const creatureWithInventory: SandboxCreatureJson = {
            ...creature,
            inventory: [
                { type: 'food', energy: 10 },
                { type: 'ball', color: '#AABBCC' },
            ],
        };
        const blockedState: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [{ id: 'w1', type: 'wall', position: { x: 2, y: 1 } }],
            },
        };
        render(
            <SandboxUserActionModal
                creature={creatureWithInventory}
                sandboxState={blockedState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={onConfirm}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^place$/i }));
        expect(screen.getByTestId('sensory-probe-panel')).toBeInTheDocument();
        expect(screen.getByText('Choose an item to place')).toBeInTheDocument();

        const confirm = screen.getByRole('button', { name: /^confirm$/i });
        expect(confirm).toBeDisabled();

        await user.click(screen.getByRole('button', { name: /food/i }));
        expect(confirm).toBeDisabled();
        expect(screen.getByText('Forward cell must be empty to place')).toBeInTheDocument();
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it('confirms place_item with inventory_index when forward cell is empty', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();
        const creatureWithInventory: SandboxCreatureJson = {
            ...creature,
            inventory: [
                { type: 'food', energy: 10 },
                { type: 'ball', color: '#AABBCC' },
            ],
        };
        render(
            <SandboxUserActionModal
                creature={creatureWithInventory}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={onConfirm}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^place$/i }));
        await user.click(screen.getByRole('button', { name: /ball/i }));
        const confirm = screen.getByRole('button', { name: /^confirm$/i });
        expect(confirm).not.toBeDisabled();
        await user.click(confirm);
        expect(onConfirm).toHaveBeenCalledWith({
            action: 'place_item',
            inventory_index: 1,
            item_type: 'ball',
        });
    });

    it('runs nearby probe and shows structured results', async () => {
        const user = userEvent.setup();
        const stateWithWall: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [{ id: 'w1', type: 'wall', position: { x: 2, y: 1 } }],
            },
        };
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={stateWithWall}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^nearby$/i }));
        expect(screen.getByTestId('sensory-probe-panel')).toBeInTheDocument();
        expect(screen.getByText('Wall')).toBeInTheDocument();
        expect(screen.getByText('You')).toBeInTheDocument();
    });

    it('shows region chip in nearby probe when forward cell has labeled region', async () => {
        const user = userEvent.setup();
        const stateWithRegion: SandboxSandboxStateJson = {
            ...sandboxState,
            world: {
                grid: { width: 5, height: 5 },
                items: [
                    {
                        id: 'r1',
                        type: 'region',
                        position: { x: 2, y: 1 },
                        color: '#3B82F6',
                        label: 'target',
                    },
                ],
            },
        };
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={stateWithRegion}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^nearby$/i }));
        const panel = screen.getByTestId('sensory-probe-panel');
        expect(within(panel).getByText('target')).toBeInTheDocument();
    });

    it('replaces probe result when a different probe is clicked', async () => {
        const user = userEvent.setup();
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^nearby$/i }));
        expect(screen.getByText('You')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^position$/i }));
        expect(screen.queryByText('You')).not.toBeInTheDocument();
        const panel = screen.getByTestId('sensory-probe-panel');
        expect(panel).toHaveTextContent('Position');
        expect(panel).toHaveTextContent('Focused creature grid coordinates');
        expect(within(panel).getAllByText('2')).toHaveLength(2);
    });

    it('collapses probe panel when the active probe is clicked again', async () => {
        const user = userEvent.setup();
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        const nearby = screen.getByRole('button', { name: /^nearby$/i });
        await user.click(nearby);
        expect(screen.getByTestId('sensory-probe-panel')).toBeInTheDocument();
        expect(nearby).toHaveAttribute('aria-pressed', 'true');

        await user.click(nearby);
        expect(screen.queryByTestId('sensory-probe-panel')).not.toBeInTheDocument();
        expect(nearby).toHaveAttribute('aria-pressed', 'false');
        for (const label of ['Position', 'Facing', 'Inventory']) {
            expect(screen.getByRole('button', { name: new RegExp(`^${label}$`, 'i') })).toHaveAttribute(
                'aria-pressed',
                'false',
            );
        }
    });

    it('restores cached probe result on re-open without re-fetching', async () => {
        const user = userEvent.setup();
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );
        const nearby = screen.getByRole('button', { name: /^nearby$/i });
        await user.click(nearby);
        expect(screen.getByTestId('sensory-probe-panel')).toBeInTheDocument();
        expect(sandboxSensoryProbes.runSensoryProbe).toHaveBeenCalledTimes(1);

        await user.click(nearby);
        expect(screen.queryByTestId('sensory-probe-panel')).not.toBeInTheDocument();

        await user.click(nearby);
        expect(screen.getByTestId('sensory-probe-panel')).toBeInTheDocument();
        expect(screen.getByText('You')).toBeInTheDocument();
        expect(sandboxSensoryProbes.runSensoryProbe).toHaveBeenCalledTimes(1);
    });

    it('cancel calls onDismiss', async () => {
        const user = userEvent.setup();
        const onDismiss = vi.fn();
        render(
            <SandboxUserActionModal
                creature={creature}
                sandboxState={sandboxState}
                creatureIndex={0}
                creatureTotal={1}
                onConfirm={vi.fn()}
                onDismiss={onDismiss}
            />,
        );
        await user.click(screen.getByRole('button', { name: 'Cancel' }));
        expect(onDismiss).toHaveBeenCalled();
    });
});
