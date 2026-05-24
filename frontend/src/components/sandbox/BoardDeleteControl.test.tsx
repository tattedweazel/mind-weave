import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BoardDeleteControl } from './BoardDeleteControl';

describe('BoardDeleteControl', () => {
    it('shows confirm message and calls onConfirmDelete', async () => {
        const onConfirmDelete = vi.fn().mockResolvedValue(undefined);
        render(<BoardDeleteControl boardName="Arena" onConfirmDelete={onConfirmDelete} />);

        fireEvent.click(screen.getByTitle('Delete board'));
        expect(screen.getByText('Delete "Arena"?')).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
        expect(onConfirmDelete).toHaveBeenCalledTimes(1);
    });

    it('cancel dismisses confirm without deleting', () => {
        const onConfirmDelete = vi.fn();
        render(<BoardDeleteControl boardName="Arena" onConfirmDelete={onConfirmDelete} />);

        fireEvent.click(screen.getByTitle('Delete board'));
        fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
        expect(onConfirmDelete).not.toHaveBeenCalled();
        expect(screen.queryByText('Delete "Arena"?')).toBeNull();
    });

    it('toolbar variant uses Yes label', () => {
        render(
            <BoardDeleteControl boardName="Arena" variant="toolbar" onConfirmDelete={vi.fn()} />,
        );
        fireEvent.click(screen.getByTitle('Delete board'));
        expect(screen.getByRole('button', { name: 'Yes' })).toBeTruthy();
    });

    it('does not render trash when disabled during confirm flow entry', () => {
        render(<BoardDeleteControl boardName="Arena" disabled onConfirmDelete={vi.fn()} />);
        expect(screen.getByTitle('Delete board')).toHaveProperty('disabled', true);
    });
});
