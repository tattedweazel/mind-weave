import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ExternalLink } from './ExternalLink';

describe('ExternalLink', () => {
    beforeEach(() => {
        vi.spyOn(window, 'open').mockImplementation(() => null);
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('shows leave-site confirmation for cross-origin https links', async () => {
        const user = userEvent.setup();
        render(
            <ExternalLink href="https://example.com/docs/page" className="text-mw-primary">
                Read docs
            </ExternalLink>,
        );
        await user.click(screen.getByRole('link', { name: /read docs/i }));
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByText(/example\.com\/docs\/page/)).toBeInTheDocument();
    });

    it('opens URL from confirmation when Continue is clicked', async () => {
        const user = userEvent.setup();
        const url = 'https://example.org/x';
        render(
            <ExternalLink href={url} className="text-mw-primary">
                Go
            </ExternalLink>,
        );
        await user.click(screen.getByRole('link', { name: /go/i }));
        await user.click(screen.getByRole('button', { name: 'Continue' }));
        expect(window.open).toHaveBeenCalledWith(url, '_blank', 'noopener,noreferrer');
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('skips confirmation when skipLeaveConfirmation is true', async () => {
        const user = userEvent.setup();
        const url = 'https://example.net/';
        render(
            <ExternalLink href={url} skipLeaveConfirmation className="text-mw-primary">
                Direct
            </ExternalLink>,
        );
        await user.click(screen.getByRole('link', { name: /direct/i }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('closes confirmation when Cancel is clicked', async () => {
        const user = userEvent.setup();
        render(
            <ExternalLink href="https://example.com/" className="text-mw-primary">
                X
            </ExternalLink>,
        );
        await user.click(screen.getByRole('link', { name: /x/i }));
        await user.click(screen.getByRole('button', { name: 'Cancel' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(window.open).not.toHaveBeenCalled();
    });

    it('closes confirmation when backdrop is clicked', async () => {
        const user = userEvent.setup();
        render(
            <ExternalLink href="https://example.com/" className="text-mw-primary">
                Y
            </ExternalLink>,
        );
        await user.click(screen.getByRole('link', { name: /y/i }));
        await user.click(screen.getByTestId('external-link-confirm-backdrop'));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
});
