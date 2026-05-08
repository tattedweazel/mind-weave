import type { ReactElement } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ClipboardFeedbackProvider } from '../../contexts/ClipboardFeedbackContext';
import { RunInputsExplorer } from './RunInputsExplorer';

function renderWithClipboard(ui: ReactElement) {
    return render(<ClipboardFeedbackProvider>{ui}</ClipboardFeedbackProvider>);
}

describe('RunInputsExplorer', () => {
    it('renders one explorer card per input key', () => {
        renderWithClipboard(
            <RunInputsExplorer payload={{ user_prompt: 'hello', meta: { a: 1 } }} />,
        );

        expect(screen.getByText('hello')).toBeInTheDocument();
        expect(screen.getByText('1 key(s)')).toBeInTheDocument();
        expect(screen.getAllByRole('button', { name: /copy input value/i }).length).toBeGreaterThanOrEqual(1);
        expect(screen.getByRole('button', { name: /copy entire dictionary as json/i })).toBeInTheDocument();
        expect(screen.queryByText('Resolved inputs')).not.toBeInTheDocument();
        expect(screen.queryByText('Raw inputs (JSON)')).not.toBeInTheDocument();
    });

    it('opens detail modal from a scalar input header with full string in preview', async () => {
        const user = userEvent.setup();
        const long = `${'z'.repeat(600)}TAIL`;
        renderWithClipboard(<RunInputsExplorer payload={{ body: long }} />);

        await user.click(screen.getByRole('button', { name: /open full value: body/i }));
        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'body' })).toBeInTheDocument();
        expect(within(dialog).getByText(/TAIL$/)).toBeInTheDocument();
    });
});
