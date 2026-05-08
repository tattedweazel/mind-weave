import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ClipboardFeedbackProvider, useCopyWithFeedback, useStatusToast } from './ClipboardFeedbackContext';

const writeTextToSystemClipboard = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock('../systemClipboard', () => ({
    writeTextToSystemClipboard: (text: string) => writeTextToSystemClipboard(text),
}));

function CopyButton({ text }: { text: string }) {
    const copy = useCopyWithFeedback();
    return (
        <button type="button" onClick={() => void copy(text)}>
            Copy
        </button>
    );
}

function StatusButton() {
    const show = useStatusToast();
    return (
        <button type="button" onClick={() => show('Status message', false)}>
            Status
        </button>
    );
}

describe('ClipboardFeedbackProvider', () => {
    beforeEach(() => {
        writeTextToSystemClipboard.mockClear();
        writeTextToSystemClipboard.mockResolvedValue(undefined);
    });

    afterEach(() => {
        writeTextToSystemClipboard.mockReset();
        writeTextToSystemClipboard.mockResolvedValue(undefined);
    });

    it('shows error when clipboard rejects', async () => {
        writeTextToSystemClipboard.mockRejectedValue(new Error('denied'));
        const user = userEvent.setup();
        render(
            <ClipboardFeedbackProvider>
                <CopyButton text="x" />
            </ClipboardFeedbackProvider>,
        );
        await user.click(screen.getByRole('button', { name: 'Copy' }));
        await waitFor(() => {
            expect(writeTextToSystemClipboard).toHaveBeenCalledWith('x');
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Could not copy');
    });

    it('shows status toast from useStatusToast', async () => {
        const user = userEvent.setup();
        render(
            <ClipboardFeedbackProvider>
                <StatusButton />
            </ClipboardFeedbackProvider>,
        );
        await user.click(screen.getByRole('button', { name: 'Status' }));
        expect(await screen.findByRole('status')).toHaveTextContent('Status message');
    });

    it('shows Copied to clipboard after successful copy', async () => {
        const user = userEvent.setup();
        render(
            <ClipboardFeedbackProvider>
                <CopyButton text="hello" />
            </ClipboardFeedbackProvider>,
        );
        await user.click(screen.getByRole('button', { name: 'Copy' }));
        await waitFor(() => {
            expect(writeTextToSystemClipboard).toHaveBeenCalledWith('hello');
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Copied to clipboard');
    });

    it('hides toast after timeout', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
        render(
            <ClipboardFeedbackProvider>
                <CopyButton text="hi" />
            </ClipboardFeedbackProvider>,
        );
        await user.click(screen.getByRole('button', { name: 'Copy' }));
        expect(await screen.findByRole('status')).toBeInTheDocument();
        vi.advanceTimersByTime(2600);
        await waitFor(() => {
            expect(screen.queryByRole('status')).not.toBeInTheDocument();
        });
        vi.useRealTimers();
    });
});
