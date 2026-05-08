import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DocumentMetadataPanel, DocumentMetadataPanelSkeleton } from './DocumentMetadataPanel';
import type { DocumentMetadata } from '../api/types';

const baseMeta: DocumentMetadata = {
    id: '11111111-1111-1111-1111-111111111111',
    name: 'Sample',
    created_at: '2026-01-02T03:04:05Z',
    updated_at: '2026-02-03T04:05:06Z',
    token_count: 1234,
    character_count: 5678,
    word_count: 90,
    line_count: 12,
    tokenizer: 'o200k_base',
};

describe('DocumentMetadataPanel', () => {
    it('renders all derived stats with locale-formatted integers', () => {
        render(<DocumentMetadataPanel metadata={baseMeta} />);
        const panel = screen.getByTestId('document-metadata-panel');
        const formatted = new Intl.NumberFormat();
        expect(panel.textContent).toContain(formatted.format(1234));
        expect(panel.textContent).toContain(formatted.format(5678));
        expect(panel.textContent).toContain(formatted.format(90));
        expect(panel.textContent).toContain(formatted.format(12));
    });

    it('shows the document id and tokenizer hint', () => {
        render(<DocumentMetadataPanel metadata={baseMeta} />);
        expect(screen.getByText(baseMeta.id)).toBeInTheDocument();
        expect(screen.getByText(/Estimated with o200k_base/i)).toBeInTheDocument();
    });

    it('formats valid timestamps via toLocaleString', () => {
        render(<DocumentMetadataPanel metadata={baseMeta} />);
        const expectedCreated = new Date(baseMeta.created_at).toLocaleString();
        expect(screen.getByText(expectedCreated)).toBeInTheDocument();
    });

    it('falls back to the raw string when the timestamp is unparsable', () => {
        const meta = { ...baseMeta, created_at: 'not-a-date', updated_at: '' };
        render(<DocumentMetadataPanel metadata={meta} />);
        expect(screen.getByText('not-a-date')).toBeInTheDocument();
    });
});

describe('DocumentMetadataPanelSkeleton', () => {
    it('renders the same row labels as the real panel for layout parity', () => {
        render(<DocumentMetadataPanelSkeleton />);
        const skeleton = screen.getByTestId('document-metadata-panel-skeleton');
        expect(skeleton.textContent).toContain('Token count');
        expect(skeleton.textContent).toContain('Characters');
        expect(skeleton.textContent).toContain('Words');
        expect(skeleton.textContent).toContain('Lines');
        expect(skeleton.textContent).toContain('Document ID');
        expect(skeleton.textContent).toContain('Created');
        expect(skeleton.textContent).toContain('Updated');
    });

    it('uses the Tailwind pulse animation and exposes a busy/live region for assistive tech', () => {
        render(<DocumentMetadataPanelSkeleton />);
        const skeleton = screen.getByTestId('document-metadata-panel-skeleton');
        expect(skeleton.className).toMatch(/animate-pulse/);
        expect(skeleton).toHaveAttribute('aria-busy', 'true');
        expect(skeleton).toHaveAttribute('aria-live', 'polite');
        expect(screen.getByText(/loading metadata/i)).toBeInTheDocument();
    });
});
