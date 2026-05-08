import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ManagerModal } from './ManagerModal';

describe('ManagerModal', () => {
    it('renders nothing when closed', () => {
        const { container } = render(
            <ManagerModal isOpen={false} onClose={() => {}} title="Test Modal">
                <div>Body content</div>
            </ManagerModal>
        );
        expect(container.firstChild).toBeNull();
    });

    it('renders title and body when open', () => {
        render(
            <ManagerModal isOpen={true} onClose={() => {}} title="Test Modal">
                <div>Body content</div>
            </ManagerModal>
        );
        expect(screen.getByText('Test Modal')).toBeInTheDocument();
        expect(screen.getByText('Body content')).toBeInTheDocument();
    });

    it('calls onClose when close button is clicked', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        render(
            <ManagerModal isOpen={true} onClose={onClose} title="Test Modal">
                <div>Body content</div>
            </ManagerModal>
        );
        await user.click(screen.getByRole('button', { name: 'Close' }));
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when backdrop is clicked', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        const { container } = render(
            <ManagerModal isOpen={true} onClose={onClose} title="Test Modal">
                <div>Body content</div>
            </ManagerModal>
        );
        const backdrop = container.firstElementChild as HTMLElement;
        await user.click(backdrop);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('does not call onClose when panel content is clicked', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        render(
            <ManagerModal isOpen={true} onClose={onClose} title="Test Modal">
                <div>Body content</div>
            </ManagerModal>
        );
        await user.click(screen.getByText('Body content'));
        expect(onClose).not.toHaveBeenCalled();
    });

    it('renders leadingSlot and forwards close actions from it', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        render(
            <ManagerModal
                isOpen={true}
                onClose={onClose}
                title="Test Modal"
                leadingSlot={
                    <button type="button" onClick={onClose}>
                        Back
                    </button>
                }
            >
                <div>Body content</div>
            </ManagerModal>
        );
        await user.click(screen.getByRole('button', { name: 'Back' }));
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});
