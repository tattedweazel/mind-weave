import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContextHelpModal } from './ContextHelpModal';

describe('ContextHelpModal', () => {
    it('opens on trigger click and shows title and body', async () => {
        const user = userEvent.setup();
        render(
            <ContextHelpModal title="Test help" triggerLabel="Open help">
                <p>Primer body text</p>
            </ContextHelpModal>,
        );
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Open help' }));
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByText('Test help')).toBeInTheDocument();
        expect(screen.getByText('Primer body text')).toBeInTheDocument();
    });

    it('closes when Close button is clicked', async () => {
        const user = userEvent.setup();
        render(
            <ContextHelpModal title="Test help" triggerLabel="Open help">
                <p>Body</p>
            </ContextHelpModal>,
        );
        await user.click(screen.getByRole('button', { name: 'Open help' }));
        await user.click(screen.getByRole('button', { name: 'Close' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('closes when backdrop is clicked', async () => {
        const user = userEvent.setup();
        render(
            <ContextHelpModal title="Test help" triggerLabel="Open help">
                <p>Body</p>
            </ContextHelpModal>,
        );
        await user.click(screen.getByRole('button', { name: 'Open help' }));
        await user.click(screen.getByTestId('context-help-backdrop'));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
});
