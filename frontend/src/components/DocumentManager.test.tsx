import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DocumentManager } from './DocumentManager';
import { ApiClient } from '../api/client';
import type { Document, DocumentMetadata } from '../api/types';

const docA = {
    id: 'a1',
    user_id: 'u1',
    name: 'Alpha',
    description: 'desc a',
    created_at: '',
    updated_at: '',
};

const docB = {
    id: 'b2',
    user_id: 'u1',
    name: 'Beta',
    description: 'desc b',
    created_at: '',
    updated_at: '',
};

const docC = {
    id: 'c3',
    user_id: 'u1',
    name: 'Gamma',
    description: 'desc c',
    created_at: '',
    updated_at: '',
};

const fullDoc = (id: string, body: string): Document => {
    const base = id === 'a1' ? docA : id === 'b2' ? docB : docC;
    return { ...base, body };
};

vi.mock('../api/client', () => ({
    ApiClient: {
        getDocuments: vi.fn(),
        getDocument: vi.fn(),
        getDocumentMetadata: vi.fn(),
        createDocument: vi.fn(),
        updateDocument: vi.fn(),
        deleteDocument: vi.fn(),
    },
}));

const metaFor = (id: string, overrides: Partial<DocumentMetadata> = {}): DocumentMetadata => ({
    id,
    name: `name-${id}`,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    token_count: 7,
    character_count: 42,
    word_count: 8,
    line_count: 1,
    tokenizer: 'o200k_base',
    ...overrides,
});

describe('DocumentManager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.getDocuments).mockResolvedValue([docA, docB, docC]);
        vi.mocked(ApiClient.deleteDocument).mockResolvedValue(undefined);
        vi.mocked(ApiClient.getDocument).mockImplementation(async (id: string) =>
            fullDoc(id, `body-${id}`),
        );
        vi.mocked(ApiClient.getDocumentMetadata).mockImplementation(async (id: string) =>
            metaFor(id),
        );
        vi.mocked(ApiClient.updateDocument).mockImplementation(async (id: string) =>
            fullDoc(id, `updated-${id}`),
        );
        vi.mocked(ApiClient.createDocument).mockImplementation(async () =>
            fullDoc('a1', 'created'),
        );
    });

    it('renders nothing when closed', () => {
        const { container } = render(<DocumentManager isOpen={false} onClose={() => {}} />);
        expect(container.firstChild).toBeNull();
    });

    it('lists documents with a checkbox per row when open', async () => {
        render(<DocumentManager isOpen onClose={() => {}} />);
        expect(await screen.findByText('Alpha')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /select alpha/i })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /select beta/i })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /select gamma/i })).toBeInTheDocument();
    });

    it('plain row click selects one document and shows its name in the editor', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Beta'));
        expect(screen.getByDisplayValue('Beta')).toBeInTheDocument();
        expect(screen.getByDisplayValue('desc b')).toBeInTheDocument();
    });

    it('ctrl+click adds a second selection and shows bulk bar with count', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        const alphaRow = screen.getByText('Alpha').closest('[role="button"]')!;
        const betaRow = screen.getByText('Beta').closest('[role="button"]')!;
        await user.click(alphaRow);
        fireEvent.click(betaRow, { ctrlKey: true });
        expect(await screen.findByText('2 selected')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /delete selected/i })).toBeInTheDocument();
    });

    it('focus follows last ctrl+clicked row in the editor', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        const alphaRow = screen.getByText('Alpha').closest('[role="button"]')!;
        const betaRow = screen.getByText('Beta').closest('[role="button"]')!;
        await user.click(alphaRow);
        fireEvent.click(betaRow, { ctrlKey: true });
        expect(screen.getByDisplayValue('Beta')).toBeInTheDocument();
        fireEvent.click(alphaRow, { ctrlKey: true });
        expect(screen.getByDisplayValue('Alpha')).toBeInTheDocument();
    });

    it('bulk delete confirms then calls deleteDocument for each selected id', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        const alphaRow = screen.getByText('Alpha').closest('[role="button"]')!;
        const betaRow = screen.getByText('Beta').closest('[role="button"]')!;
        await user.click(alphaRow);
        fireEvent.click(betaRow, { ctrlKey: true });
        await user.click(screen.getByRole('button', { name: /delete selected/i }));
        expect(screen.getByText(/delete 2 documents/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^delete all$/i }));
        expect(ApiClient.deleteDocument).toHaveBeenCalledTimes(2);
        expect(ApiClient.deleteDocument).toHaveBeenCalledWith('a1');
        expect(ApiClient.deleteDocument).toHaveBeenCalledWith('b2');
        expect(vi.mocked(ApiClient.getDocuments).mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('checkbox toggles selection and bulk bar appears when two are checked', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByRole('checkbox', { name: /select alpha/i }));
        await user.click(screen.getByRole('checkbox', { name: /select beta/i }));
        expect(await screen.findByText('2 selected')).toBeInTheDocument();
    });

    it('hides per-row delete while multiple rows are selected', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByRole('checkbox', { name: /select alpha/i }));
        await user.click(screen.getByRole('checkbox', { name: /select beta/i }));
        const gammaRow = screen.getByText('Gamma').closest('.group')! as HTMLElement;
        expect(within(gammaRow).queryByTitle('Delete')).not.toBeInTheDocument();
    });

    it('fetches the full document and hydrates Body on row click (list payload omits body)', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.getDocument).mockResolvedValueOnce(fullDoc('b2', 'BODY-FROM-FETCH'));
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Beta'));
        expect(ApiClient.getDocument).toHaveBeenCalledWith('b2');
        expect(await screen.findByDisplayValue('BODY-FROM-FETCH')).toBeInTheDocument();
    });

    it('fetches the full document and hydrates Body when a checkbox toggles selection on', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.getDocument).mockResolvedValueOnce(fullDoc('a1', 'CHECKBOX-BODY'));
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByRole('checkbox', { name: /select alpha/i }));
        expect(ApiClient.getDocument).toHaveBeenCalledWith('a1');
        expect(await screen.findByDisplayValue('CHECKBOX-BODY')).toBeInTheDocument();
    });

    it('discards stale getDocument responses when the user picks another row mid-flight', async () => {
        const user = userEvent.setup();
        let resolveAlpha!: (doc: Document) => void;
        const alphaPromise = new Promise<Document>(resolve => {
            resolveAlpha = resolve;
        });
        vi.mocked(ApiClient.getDocument).mockImplementationOnce(() => alphaPromise);
        vi.mocked(ApiClient.getDocument).mockResolvedValueOnce(fullDoc('b2', 'WINNER-BODY'));

        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');

        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByText('Beta'));
        expect(await screen.findByDisplayValue('WINNER-BODY')).toBeInTheDocument();

        resolveAlpha(fullDoc('a1', 'STALE-BODY'));
        await waitFor(() => {
            expect(screen.queryByDisplayValue('STALE-BODY')).not.toBeInTheDocument();
        });
        expect(screen.getByDisplayValue('WINNER-BODY')).toBeInTheDocument();
    });

    it('keeps Body empty (no crash) when getDocument fails', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.getDocument).mockRejectedValueOnce(new Error('boom'));
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        expect(ApiClient.getDocument).toHaveBeenCalledWith('a1');
        await waitFor(() => {
            expect(screen.queryByText(/Loading body/i)).not.toBeInTheDocument();
        });
        expect(screen.getByDisplayValue('Alpha')).toBeInTheDocument();
    });

    it('labels the body section "Body" (no longer "Body (Markdown)")', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        const labels = await screen.findAllByText(/^Body$/);
        expect(labels.length).toBeGreaterThan(0);
        expect(screen.queryByText(/Body \(Markdown\)/i)).not.toBeInTheDocument();
    });

    it('renders the Metadata tab on the body editor when a document is focused', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        expect(await screen.findByRole('button', { name: /^metadata$/i })).toBeInTheDocument();
    });

    it('lazy-fetches metadata only when the Metadata tab is first opened', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        expect(ApiClient.getDocumentMetadata).not.toHaveBeenCalled();

        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await waitFor(() => {
            expect(ApiClient.getDocumentMetadata).toHaveBeenCalledWith('a1');
        });
        expect(await screen.findByTestId('document-metadata-panel')).toBeInTheDocument();
    });

    it('resets the body editor back to the Raw tab when focus moves to another document', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));

        // Move off Raw on the first doc — body textarea disappears, metadata panel appears.
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await screen.findByTestId('document-metadata-panel');
        expect(screen.queryByDisplayValue('body-a1')).not.toBeInTheDocument();

        // Switching to a different document should land on Raw again, not the
        // tab the previous doc was viewed on. The Body textarea (with the new
        // doc's body) should be back, and the metadata panel should be gone.
        await user.click(screen.getByText('Beta'));
        await screen.findByDisplayValue('body-b2');
        expect(screen.queryByTestId('document-metadata-panel')).not.toBeInTheDocument();
        expect(screen.queryByTestId('document-metadata-panel-skeleton')).not.toBeInTheDocument();
    });

    it('shows the pulsing skeleton while the metadata fetch is in flight', async () => {
        const user = userEvent.setup();
        let resolveMeta!: (m: DocumentMetadata) => void;
        vi.mocked(ApiClient.getDocumentMetadata).mockImplementationOnce(
            () =>
                new Promise<DocumentMetadata>(resolve => {
                    resolveMeta = resolve;
                }),
        );

        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));

        const skeleton = await screen.findByTestId('document-metadata-panel-skeleton');
        expect(skeleton.className).toMatch(/animate-pulse/);
        expect(screen.queryByTestId('document-metadata-panel')).not.toBeInTheDocument();

        resolveMeta(metaFor('a1'));
        await screen.findByTestId('document-metadata-panel');
        expect(screen.queryByTestId('document-metadata-panel-skeleton')).not.toBeInTheDocument();
    });

    it('caches metadata between tab switches for the same document', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await screen.findByTestId('document-metadata-panel');

        await user.click(screen.getByRole('button', { name: /^raw$/i }));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));

        expect(ApiClient.getDocumentMetadata).toHaveBeenCalledTimes(1);
    });

    it('invalidates cached metadata after a save so the next open refetches', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await screen.findByTestId('document-metadata-panel');
        expect(ApiClient.getDocumentMetadata).toHaveBeenCalledTimes(1);

        await user.click(screen.getByRole('button', { name: /save document/i }));
        await waitFor(() => {
            expect(ApiClient.updateDocument).toHaveBeenCalled();
        });

        // After save, focus is cleared; reopen the doc and reopen the tab.
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await waitFor(() => {
            expect(ApiClient.getDocumentMetadata).toHaveBeenCalledTimes(2);
        });
    });

    it('shows an unsaved-doc message in Metadata when creating a new document', async () => {
        const user = userEvent.setup();
        render(<DocumentManager isOpen onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /new document/i }));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        expect(await screen.findByText(/save the document to see token count/i)).toBeInTheDocument();
        expect(ApiClient.getDocumentMetadata).not.toHaveBeenCalled();
    });

    it('shows a friendly error in Metadata when the fetch fails', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.getDocumentMetadata).mockRejectedValueOnce(new Error('boom'));
        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        expect(await screen.findByText(/failed to load metadata/i)).toBeInTheDocument();
    });

    it('discards stale metadata responses if the user picks another document mid-flight', async () => {
        const user = userEvent.setup();
        let resolveAlpha!: (m: DocumentMetadata) => void;
        const alphaMeta = new Promise<DocumentMetadata>(resolve => {
            resolveAlpha = resolve;
        });
        vi.mocked(ApiClient.getDocumentMetadata).mockImplementationOnce(() => alphaMeta);
        vi.mocked(ApiClient.getDocumentMetadata).mockResolvedValueOnce(
            metaFor('b2', { token_count: 99 }),
        );

        render(<DocumentManager isOpen onClose={() => {}} />);
        await screen.findByText('Alpha');
        await user.click(screen.getByText('Alpha'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));

        // Switch to Beta — the body editor remounts back on the Raw tab, so a
        // single click on Metadata fires onModeChange and triggers the b2 fetch.
        await user.click(screen.getByText('Beta'));
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await screen.findByTestId('document-metadata-panel');

        resolveAlpha(metaFor('a1', { token_count: 11 }));
        await waitFor(() => {
            const panel = screen.getByTestId('document-metadata-panel');
            expect(panel.textContent).toContain('99');
            expect(panel.textContent).not.toContain('11');
        });
    });
});
