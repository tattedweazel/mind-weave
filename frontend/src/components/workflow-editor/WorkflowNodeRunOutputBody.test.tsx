import type { ReactElement } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ClipboardFeedbackProvider } from '../../contexts/ClipboardFeedbackContext';
import { WorkflowNodeRunOutputBody } from './WorkflowNodeRunOutputBody';

vi.mock('./UrlSnapshotArtifactPreview', () => ({
    UrlSnapshotArtifactPreview: ({ artifactId, nodeId }: { artifactId: string; nodeId: string }) => (
        <div data-testid="url-snap-preview" data-artifact={artifactId} data-nodeid={nodeId} />
    ),
}));

function wrap(ui: ReactElement) {
    return render(<ClipboardFeedbackProvider>{ui}</ClipboardFeedbackProvider>);
}

describe('WorkflowNodeRunOutputBody', () => {
    it('renders TTS player for audio kind (not explorer-only)', () => {
        const b64 = btoa('fake');
        wrap(
            <WorkflowNodeRunOutputBody
                nodeId="n1"
                output={{
                    kind: 'audio',
                    node_id: 'n1',
                    mime_type: 'audio/wav',
                    audio_base64: b64,
                }}
                details={{
                    output_explorer: {
                        version: 1,
                        kind: 'generic',
                        summary: { line: 'audio output', detail_lines: ['audio/wav · base64 length 8'] },
                        items: [],
                    },
                }}
            />,
        );
        expect(screen.getByRole('button', { name: /Download WAV/i })).toBeInTheDocument();
        expect(document.querySelector('audio')).toBeTruthy();
        expect(screen.getByText('audio output')).toBeInTheDocument();
    });

    it('shows history hint when audio is redacted', () => {
        wrap(
            <WorkflowNodeRunOutputBody
                nodeId="n1"
                output={{
                    kind: 'audio',
                    node_id: 'n1',
                    mime_type: 'audio/wav',
                    audio_base64: '[redacted]',
                }}
                details={{}}
            />,
        );
        expect(screen.getByText(/Audio is only available during the live run/i)).toBeInTheDocument();
    });

    it('renders url snapshot preview + explorer for dictionary with image.artifact_id', () => {
        const artifact = '9f8e7d6c-aaaa-bbbb-cccc-ddddeeeeffff';
        wrap(
            <WorkflowNodeRunOutputBody
                nodeId="cap-node"
                output={{
                    kind: 'dictionary',
                    node_id: 'cap-node',
                    data: {
                        image: {
                            artifact_id: artifact,
                            mime_type: 'image/png',
                            width: 800,
                            height: 600,
                        },
                        final_url: 'https://example.com',
                        captured_at: '2026-01-01T00:00:00Z',
                        duration_ms: 12,
                        cached: false,
                    },
                }}
                details={{
                    output_explorer: {
                        version: 1,
                        kind: 'capture_url_snapshot',
                        summary: { line: 'Snapshot 800×600', detail_lines: [] },
                        items: [],
                    },
                }}
            />,
        );
        const pre = screen.getByTestId('url-snap-preview');
        expect(pre).toBeInTheDocument();
        expect(pre).toHaveAttribute('data-artifact', artifact);
        expect(pre).toHaveAttribute('data-nodeid', 'cap-node');
        expect(screen.getByText('Snapshot 800×600')).toBeInTheDocument();
    });
});
