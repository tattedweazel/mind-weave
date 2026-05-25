import type { NodeRunResult } from '../api/types';

export type BroadcastSeverity = 'info' | 'notice' | 'success';

export interface BroadcastSegment {
    node_id: string;
    body: string;
    severity?: BroadcastSeverity;
    title?: string;
    render_markdown?: boolean;
    source?: string;
    step_number?: number;
}

const MARKDOWN_PATTERNS = [
    /^#{1,6}\s+\S/m,
    /```/,
    /^\s*[-*+]\s+\S/m,
    /^\s*\d+\.\s+\S/m,
    /\*\*[^*\n]+\*\*/,
    /__[^_\n]+__/,
];

export function normalizeBroadcastSeverity(raw: unknown): BroadcastSeverity {
    const s = String(raw ?? 'info').trim().toLowerCase();
    if (s === 'info' || s === 'notice' || s === 'success') return s;
    return 'info';
}

export function looksLikeMarkdown(text: string): boolean {
    if (!text.trim()) return false;
    return MARKDOWN_PATTERNS.some(p => p.test(text));
}

export function broadcastSegmentFromNodeResult(nr: NodeRunResult): BroadcastSegment | null {
    if (nr.status !== 'ok' || !nr.details) return null;
    const det = nr.details as Record<string, unknown>;
    const raw = det.broadcast_segment;
    if (!raw || typeof raw !== 'object') return null;
    const seg = raw as Record<string, unknown>;
    const body = seg.body;
    if (typeof body !== 'string' || !body.trim()) return null;
    return {
        node_id: String(seg.node_id ?? nr.node_id),
        body,
        severity: normalizeBroadcastSeverity(seg.severity),
        title: typeof seg.title === 'string' && seg.title.trim() ? seg.title.trim() : undefined,
        render_markdown:
            typeof seg.render_markdown === 'boolean' ? seg.render_markdown : looksLikeMarkdown(body),
        source: typeof seg.source === 'string' && seg.source.trim() ? seg.source.trim() : undefined,
        step_number: typeof seg.step_number === 'number' ? seg.step_number : nr.step_number,
    };
}

export function collectBroadcastSegmentsFromNodeResults(
    nodeResults: NodeRunResult[] | undefined,
    source?: string,
): BroadcastSegment[] {
    if (!nodeResults?.length) return [];
    const sorted = [...nodeResults].sort((a, b) => {
        const sa = a.step_number ?? 0;
        const sb = b.step_number ?? 0;
        if (sa !== sb) return sa - sb;
        return a.node_id.localeCompare(b.node_id);
    });
    const out: BroadcastSegment[] = [];
    for (const nr of sorted) {
        const seg = broadcastSegmentFromNodeResult(nr);
        if (!seg) continue;
        out.push(source && !seg.source ? { ...seg, source } : seg);
    }
    return out;
}

export function collectBroadcastSegmentsFromRuns(
    runs: Array<{ node_results?: NodeRunResult[] } | null | undefined>,
): BroadcastSegment[] {
    const merged: BroadcastSegment[] = [];
    for (const run of runs) {
        if (!run?.node_results?.length) continue;
        merged.push(...collectBroadcastSegmentsFromNodeResults(run.node_results));
    }
    merged.sort((a, b) => {
        const sa = a.step_number ?? 0;
        const sb = b.step_number ?? 0;
        if (sa !== sb) return sa - sb;
        return a.node_id.localeCompare(b.node_id);
    });
    return merged;
}

export function parseBroadcastSegmentsFromEffects(raw: unknown): BroadcastSegment[] {
    if (!Array.isArray(raw)) return [];
    const out: BroadcastSegment[] = [];
    for (const item of raw) {
        if (!item || typeof item !== 'object') continue;
        const seg = item as Record<string, unknown>;
        const body = seg.body;
        if (typeof body !== 'string' || !body.trim()) continue;
        out.push({
            node_id: String(seg.node_id ?? ''),
            body,
            severity: normalizeBroadcastSeverity(seg.severity),
            title: typeof seg.title === 'string' && seg.title.trim() ? seg.title.trim() : undefined,
            render_markdown:
                typeof seg.render_markdown === 'boolean'
                    ? seg.render_markdown
                    : looksLikeMarkdown(body),
            source: typeof seg.source === 'string' && seg.source.trim() ? seg.source.trim() : undefined,
            step_number: typeof seg.step_number === 'number' ? seg.step_number : undefined,
        });
    }
    return out;
}

export function severityAccentClass(severity: BroadcastSeverity | undefined): string {
    switch (severity ?? 'info') {
        case 'success':
            return 'border-t-success bg-success-muted/30';
        case 'notice':
            return 'border-t-amber-500 bg-amber-500/5 dark:bg-amber-500/10';
        default:
            return 'border-t-mw-primary bg-mw-primary-muted/40';
    }
}
