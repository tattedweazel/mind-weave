import type { ReactElement } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { NodeRunResult } from '../../api/types';
import { ClipboardFeedbackProvider } from '../../contexts/ClipboardFeedbackContext';
import { WorkflowRunLogsNodeResultsList } from './WorkflowRunLogsNodeResultsList';

function wrap(ui: ReactElement) {
    return render(<ClipboardFeedbackProvider>{ui}</ClipboardFeedbackProvider>);
}

describe('WorkflowRunLogsNodeResultsList', () => {
    it('renders labels from getNodeLabel and expands to show Output and Inputs', async () => {
        const user = userEvent.setup();
        const getNodeLabel = vi.fn((id: string) => (id === 'n_dec' ? 'sandbox_decision_intent' : id));

        const node_results: NodeRunResult[] = [
            {
                node_id: 'n_dec',
                status: 'ok',
                step_number: 2,
                latency_ms: 3.25,
                output: {
                    kind: 'dictionary',
                    node_id: 'n_dec',
                    data: { action: 'wander', reason: 'unit' },
                },
                details: {
                    resolved_inputs: {
                        action: 'wander',
                        reason: 'unit',
                    },
                },
            },
        ];

        wrap(
            <WorkflowRunLogsNodeResultsList node_results={node_results} getNodeLabel={getNodeLabel} />,
        );

        expect(getNodeLabel).toHaveBeenCalledWith('n_dec');
        expect(screen.getByText('sandbox_decision_intent')).toBeInTheDocument();
        expect(screen.getByText('Step 2')).toBeInTheDocument();
        expect(screen.getByText('3.3ms')).toBeInTheDocument();

        await user.click(screen.getByText('sandbox_decision_intent'));

        expect(screen.getByText('Output')).toBeInTheDocument();
        expect(screen.getByText('Inputs')).toBeInTheDocument();
        expect(screen.getByText('wander')).toBeInTheDocument();
    });

    it('renders audio player and download for TTS output with base64', async () => {
        const user = userEvent.setup();
        const b64 = btoa('fake');
        const node_results: NodeRunResult[] = [
            {
                node_id: 'n_tts',
                status: 'ok',
                step_number: 1,
                output: {
                    kind: 'audio',
                    node_id: 'n_tts',
                    mime_type: 'audio/wav',
                    audio_base64: b64,
                },
                details: {},
            },
        ];

        wrap(
            <WorkflowRunLogsNodeResultsList node_results={node_results} getNodeLabel={id => id} />,
        );

        await user.click(screen.getByText('n_tts'));
        expect(screen.getByRole('button', { name: /Download WAV/i })).toBeInTheDocument();
        expect(document.querySelector('audio')).toBeTruthy();
    });

    it('shows re-run hint when audio base64 is redacted', async () => {
        const user = userEvent.setup();
        const node_results: NodeRunResult[] = [
            {
                node_id: 'n_tts',
                status: 'ok',
                step_number: 1,
                output: {
                    kind: 'audio',
                    node_id: 'n_tts',
                    mime_type: 'audio/wav',
                    audio_base64: '[redacted]',
                },
                details: {},
            },
        ];

        wrap(
            <WorkflowRunLogsNodeResultsList node_results={node_results} getNodeLabel={id => id} />,
        );

        await user.click(screen.getByText('n_tts'));
        expect(screen.getByText(/Audio is only available during the live run/i)).toBeInTheDocument();
    });
});
