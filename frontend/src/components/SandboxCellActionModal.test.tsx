import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SandboxCellActionModal } from './SandboxCellActionModal';

describe('SandboxCellActionModal', () => {
    it('completes remove_item when Remove item is chosen', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        const onDismiss = vi.fn();
        render(
            <SandboxCellActionModal cell={{ x: 2, y: 3 }} onComplete={onComplete} onDismiss={onDismiss} />,
        );

        await user.click(screen.getByRole('button', { name: 'Remove item' }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'remove_item',
            cell: { x: 2, y: 3 },
        });
        expect(onDismiss).not.toHaveBeenCalled();
    });

    it('completes place_item after Food is chosen', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        render(
            <SandboxCellActionModal cell={{ x: 1, y: 1 }} onComplete={onComplete} onDismiss={() => {}} />,
        );

        await user.click(screen.getByRole('button', { name: 'Place item' }));
        await user.click(screen.getByRole('button', { name: 'Food' }));
        expect(onComplete).toHaveBeenCalledWith({
            type: 'place_item',
            cell: { x: 1, y: 1 },
            item_type: 'food',
        });
    });

    it('calls onDismiss when Escape is pressed', async () => {
        const user = userEvent.setup();
        const onDismiss = vi.fn();
        render(<SandboxCellActionModal cell={{ x: 0, y: 0 }} onComplete={() => {}} onDismiss={onDismiss} />);

        await user.keyboard('{Escape}');
        expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it('shows Inspect when canInspect and calls onInspect without onComplete', async () => {
        const user = userEvent.setup();
        const onComplete = vi.fn();
        const onInspect = vi.fn();
        render(
            <SandboxCellActionModal
                cell={{ x: 0, y: 0 }}
                canInspect
                onComplete={onComplete}
                onDismiss={() => {}}
                onInspect={onInspect}
            />,
        );

        await user.click(screen.getByRole('button', { name: 'Inspect' }));
        expect(onInspect).toHaveBeenCalledTimes(1);
        expect(onComplete).not.toHaveBeenCalled();
    });

    it('does not show Inspect when canInspect is false', () => {
        render(
            <SandboxCellActionModal
                cell={{ x: 0, y: 0 }}
                canInspect={false}
                onComplete={() => {}}
                onDismiss={() => {}}
                onInspect={() => {}}
            />,
        );

        expect(screen.queryByRole('button', { name: 'Inspect' })).toBeNull();
    });
});
