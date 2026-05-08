/**
 * Fetches a URL snapshot artifact with session credentials, shows a preview, and offers download.
 * Blob URLs (not raw /api/... in <img src>) so auth works when API is on a different dev port.
 * Click the inline preview to open a larger view (same overlay pattern as Output explorer detail modals).
 */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { AlertCircle, Download, Image as ImageIcon, RotateCcw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { API_BASE } from '../../api/baseUrl';
import { fetchWithCredentials } from '../../api/http';

export type UrlSnapshotArtifactPreviewProps = {
    /** UUID from `output.data.image.artifact_id` */
    artifactId: string;
    nodeId: string;
};

function downloadFileName(artifactId: string, nodeId: string): string {
    const shortNode = nodeId.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 32);
    const shortArt = artifactId.replace(/[^a-zA-Z0-9-]+/g, '').slice(0, 8);
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    return `url-snapshot-${shortNode}-${shortArt}-${stamp}.png`;
}

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_FACTOR = 1.2;

function clampZoom(n: number): number {
    return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, n));
}

export function UrlSnapshotArtifactPreview({ artifactId, nodeId }: UrlSnapshotArtifactPreviewProps) {
    const [objectUrl, setObjectUrl] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [lightboxOpen, setLightboxOpen] = useState(false);
    const [lightboxZoom, setLightboxZoom] = useState(1);
    const [lightboxNatural, setLightboxNatural] = useState<{ w: number; h: number } | null>(null);
    const lightboxScrollRef = useRef<HTMLDivElement | null>(null);
    const lightboxTitleId = useId();

    useEffect(() => {
        let cancelled = false;
        let createdUrl: string | null = null;

        async function load() {
            setLoading(true);
            setError(null);
            setObjectUrl(null);
            if (!artifactId?.trim()) {
                setError('Missing snapshot id.');
                setLoading(false);
                return;
            }
            try {
                const res = await fetchWithCredentials(
                    `${API_BASE}/url-snapshot-artifacts/${encodeURIComponent(artifactId.trim())}`,
                );
                if (cancelled) return;
                if (!res.ok) {
                    setError(
                        res.status === 404
                            ? 'Image not found or you no longer have access.'
                            : `Could not load image (HTTP ${res.status}).`,
                    );
                    setLoading(false);
                    return;
                }
                const ct = res.headers.get('content-type') ?? '';
                if (!ct.startsWith('image/')) {
                    setError('Unexpected response (not an image).');
                    setLoading(false);
                    return;
                }
                const blob = await res.blob();
                if (cancelled) return;
                const url = URL.createObjectURL(blob);
                createdUrl = url;
                if (cancelled) {
                    URL.revokeObjectURL(url);
                    return;
                }
                setObjectUrl(url);
            } catch {
                if (!cancelled) setError('Network error while loading the snapshot.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        void load();
        return () => {
            cancelled = true;
            if (createdUrl) {
                URL.revokeObjectURL(createdUrl);
            }
        };
    }, [artifactId]);

    const handleDownload = useCallback(() => {
        if (!objectUrl) return;
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = downloadFileName(artifactId, nodeId);
        a.rel = 'noopener';
        a.click();
    }, [artifactId, nodeId, objectUrl]);

    useEffect(() => {
        if (!lightboxOpen) return;
        setLightboxZoom(1);
        setLightboxNatural(null);
    }, [lightboxOpen]);

    useEffect(() => {
        if (!lightboxOpen) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setLightboxOpen(false);
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [lightboxOpen]);

    useLayoutEffect(() => {
        if (!lightboxOpen) return;
        const el = lightboxScrollRef.current;
        if (!el) return;
        const onWheel = (e: WheelEvent) => {
            if (!(e.ctrlKey || e.metaKey)) return;
            e.preventDefault();
            setLightboxZoom(z => clampZoom(e.deltaY < 0 ? z * ZOOM_FACTOR : z / ZOOM_FACTOR));
        };
        el.addEventListener('wheel', onWheel, { passive: false });
        return () => el.removeEventListener('wheel', onWheel);
    }, [lightboxOpen]);

    const zoomOut = useCallback(() => {
        setLightboxZoom(z => clampZoom(z / ZOOM_FACTOR));
    }, []);
    const zoomIn = useCallback(() => {
        setLightboxZoom(z => clampZoom(z * ZOOM_FACTOR));
    }, []);
    const zoomReset = useCallback(() => {
        setLightboxZoom(1);
    }, []);

    if (error) {
        return (
            <div className="flex items-start gap-2 rounded-md border border-mw-border/80 bg-mw-card-alt px-2 py-2 text-xs text-mw-text-secondary">
                <AlertCircle className="shrink-0 mt-0.5 text-amber-500" size={14} aria-hidden />
                <span>{error}</span>
            </div>
        );
    }

    if (loading) {
        return <p className="text-xs text-mw-text-secondary">Loading image…</p>;
    }

    if (!objectUrl) {
        return null;
    }

    return (
        <div className="space-y-2">
            <button
                type="button"
                onClick={() => setLightboxOpen(true)}
                className="group relative inline-flex max-w-full rounded-md border border-mw-border overflow-hidden bg-mw-card-alt text-left cursor-zoom-in focus:outline-none focus-visible:ring-2 focus-visible:ring-mw-primary focus-visible:ring-offset-2 focus-visible:ring-offset-mw-card p-0"
                aria-label="View larger snapshot"
            >
                <img
                    src={objectUrl}
                    alt="Captured page snapshot"
                    className="max-w-full max-h-[min(24rem,70vh)] w-auto h-auto object-contain block pointer-events-none"
                />
                <span className="absolute bottom-1 right-1 rounded bg-black/55 px-1.5 py-0.5 text-[9px] font-medium text-white opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity pointer-events-none">
                    Click to enlarge
                </span>
            </button>
            {lightboxOpen && objectUrl ?
                <div
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
                    onClick={() => setLightboxOpen(false)}
                    role="presentation"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby={lightboxTitleId}
                        className="bg-mw-card rounded-xl shadow-2xl border border-mw-border w-full max-w-[min(96vw,95rem)] max-h-[92vh] flex flex-col overflow-hidden"
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-mw-border shrink-0">
                            <div className="min-w-0 flex-1">
                                <h2
                                    id={lightboxTitleId}
                                    className="text-sm font-semibold text-mw-text-primary leading-snug truncate"
                                >
                                    URL snapshot
                                </h2>
                                <p className="text-[11px] text-mw-text-secondary mt-0.5 line-clamp-1 font-mono break-all">
                                    {artifactId}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setLightboxOpen(false)}
                                aria-label="Close"
                                className="p-1.5 text-mw-text-secondary hover:text-mw-text-primary rounded-lg hover:bg-mw-card-alt transition-colors shrink-0"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="shrink-0 flex flex-wrap items-center justify-center gap-2 px-3 py-2 border-b border-mw-border/60 bg-mw-page/30">
                            <span className="text-[10px] text-mw-text-secondary">Zoom</span>
                            <div className="inline-flex items-center gap-0.5 rounded-md border border-mw-border bg-mw-card p-0.5">
                                <button
                                    type="button"
                                    onClick={zoomOut}
                                    disabled={lightboxZoom <= ZOOM_MIN + 1e-6}
                                    aria-label="Zoom out"
                                    className="p-1.5 text-mw-text-primary rounded hover:bg-mw-card-alt disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                    <ZoomOut size={14} aria-hidden />
                                </button>
                                <span className="min-w-[2.75rem] text-center text-[11px] font-medium tabular-nums text-mw-text-primary">
                                    {Math.round(lightboxZoom * 100)}%
                                </span>
                                <button
                                    type="button"
                                    onClick={zoomIn}
                                    disabled={lightboxZoom >= ZOOM_MAX - 1e-6}
                                    aria-label="Zoom in"
                                    className="p-1.5 text-mw-text-primary rounded hover:bg-mw-card-alt disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                    <ZoomIn size={14} aria-hidden />
                                </button>
                            </div>
                            <button
                                type="button"
                                onClick={zoomReset}
                                aria-label="Reset zoom to 100 percent"
                                className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-card-alt transition-colors"
                            >
                                <RotateCcw size={12} aria-hidden />
                                1:1
                            </button>
                            <span className="text-[9px] text-mw-text-secondary hidden sm:inline">
                                · Ctrl+scroll
                            </span>
                        </div>
                        <div
                            ref={lightboxScrollRef}
                            className="px-3 py-3 overflow-auto min-h-0 flex-1 bg-mw-page/50 touch-pan-x touch-pan-y"
                            title="Use zoom buttons, or Ctrl+scroll (⌘+scroll on Mac) to zoom"
                        >
                            <div className="p-2 inline-block min-w-full text-center">
                                <img
                                    src={objectUrl}
                                    alt="Captured page snapshot (enlarged)"
                                    onLoad={e => {
                                        const t = e.currentTarget;
                                        setLightboxNatural({ w: t.naturalWidth, h: t.naturalHeight });
                                    }}
                                    className={
                                        lightboxNatural ?
                                            'h-auto max-w-none rounded-md border border-mw-border/60 bg-mw-card-alt'
                                        :   'max-w-full w-auto h-auto max-h-[min(85vh,1200px)] object-contain rounded-md border border-mw-border/60 bg-mw-card-alt'
                                    }
                                    style={
                                        lightboxNatural ?
                                            {
                                                width: Math.round(lightboxNatural.w * lightboxZoom),
                                                height: 'auto',
                                            }
                                        :   undefined
                                    }
                                />
                            </div>
                        </div>
                        <div className="px-4 py-2.5 border-t border-mw-border bg-mw-card-alt/40 shrink-0 flex flex-wrap items-center gap-2 justify-end">
                            <button
                                type="button"
                                onClick={handleDownload}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-page transition-colors"
                            >
                                <Download size={12} aria-hidden />
                                Download PNG
                            </button>
                        </div>
                    </div>
                </div>
            : null}
            <div className="flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    onClick={handleDownload}
                    className="inline-flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium rounded-md border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-card-alt transition-colors"
                >
                    <Download size={12} aria-hidden />
                    Download PNG
                </button>
                <span className="inline-flex items-center gap-1 text-[10px] text-mw-text-secondary">
                    <ImageIcon size={10} className="opacity-80" aria-hidden />
                    {artifactId}
                </span>
            </div>
        </div>
    );
}
