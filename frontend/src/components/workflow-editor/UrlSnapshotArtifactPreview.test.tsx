import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { UrlSnapshotArtifactPreview } from './UrlSnapshotArtifactPreview';
import { fetchWithCredentials } from '../../api/http';

vi.mock('../../api/http', () => ({
    fetchWithCredentials: vi.fn(),
}));

const mockFetch = vi.mocked(fetchWithCredentials);

function wrap(ui: ReactElement) {
    return render(ui);
}

afterEach(() => {
    vi.clearAllMocks();
});

describe('UrlSnapshotArtifactPreview', () => {
    beforeEach(() => {
        mockFetch.mockReset();
    });

    it('loads PNG via fetch and shows image', async () => {
        const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
        const blob = new Blob([bytes], { type: 'image/png' });
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'image/png' : null) },
            blob: async () => blob,
        } as unknown as Awaited<ReturnType<typeof fetchWithCredentials>>);
        wrap(<UrlSnapshotArtifactPreview artifactId="a1b2c3d4-1111-2222-3333-444455556666" nodeId="node-1" />);
        expect(screen.getByText('Loading image…')).toBeInTheDocument();
        await waitFor(() => {
            expect(screen.getByRole('img', { name: 'Captured page snapshot' })).toBeInTheDocument();
        });
        expect(mockFetch).toHaveBeenCalledWith(
            expect.stringContaining('/url-snapshot-artifacts/a1b2c3d4-1111-2222-3333-444455556666'),
        );
        fireEvent.click(screen.getByRole('button', { name: /Download PNG/i }));
    });

    it('opens a lightbox with a larger image and closes on Escape', async () => {
        const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
        const blob = new Blob([bytes], { type: 'image/png' });
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'image/png' : null) },
            blob: async () => blob,
        } as unknown as Awaited<ReturnType<typeof fetchWithCredentials>>);
        wrap(<UrlSnapshotArtifactPreview artifactId="artifact-uuid-1" nodeId="n1" />);
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /View larger snapshot/i })).toBeInTheDocument();
        });
        fireEvent.click(screen.getByRole('button', { name: /View larger snapshot/i }));
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'URL snapshot' })).toBeInTheDocument();
        const dialog = screen.getByRole('dialog');
        expect(screen.getByRole('img', { name: 'Captured page snapshot (enlarged)' })).toBeInTheDocument();
        expect(within(dialog).getByText('100%')).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole('button', { name: /Zoom in/i }));
        expect(within(dialog).getByText('120%')).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole('button', { name: /Reset zoom to 100 percent/i }));
        expect(within(dialog).getByText('100%')).toBeInTheDocument();
        fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });
        await waitFor(() => {
            expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        });
    });

    it('shows 404 error message', async () => {
        mockFetch.mockResolvedValue({
            ok: false,
            status: 404,
            headers: { get: () => null },
            blob: async () => new Blob(),
        } as unknown as Awaited<ReturnType<typeof fetchWithCredentials>>);
        wrap(<UrlSnapshotArtifactPreview artifactId="a1" nodeId="n" />);
        await waitFor(() => {
            expect(screen.getByText(/Image not found or you no longer have access/i)).toBeInTheDocument();
        });
    });

    it('shows error when content-type is not an image', async () => {
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'text/plain' : null) },
            blob: async () => new Blob(),
        } as unknown as Awaited<ReturnType<typeof fetchWithCredentials>>);
        wrap(<UrlSnapshotArtifactPreview artifactId="a1" nodeId="n" />);
        await waitFor(() => {
            expect(screen.getByText(/Unexpected response \(not an image\)/i)).toBeInTheDocument();
        });
    });

    it('shows network error on fetch throw', async () => {
        mockFetch.mockRejectedValue(new Error('offline'));
        wrap(<UrlSnapshotArtifactPreview artifactId="a1" nodeId="n" />);
        await waitFor(() => {
            expect(screen.getByText(/Network error while loading the snapshot/i)).toBeInTheDocument();
        });
    });

    it('shows error for empty artifact id', async () => {
        wrap(<UrlSnapshotArtifactPreview artifactId="   " nodeId="n" />);
        await waitFor(() => {
            expect(screen.getByText(/Missing snapshot id/i)).toBeInTheDocument();
        });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('shows error for non-404 HTTP failure', async () => {
        mockFetch.mockResolvedValue({
            ok: false,
            status: 502,
            headers: { get: () => 'image/png' },
            blob: async () => new Blob(),
        } as unknown as Awaited<ReturnType<typeof fetchWithCredentials>>);
        wrap(<UrlSnapshotArtifactPreview artifactId="a1" nodeId="n" />);
        await waitFor(() => {
            expect(screen.getByText(/Could not load image \(HTTP 502\)/i)).toBeInTheDocument();
        });
    });
});
