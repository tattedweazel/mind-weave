/**
 * Per-workflow persisted left/right panel widths for the workflow editor (browser localStorage).
 * Bounded map with LRU eviction by `touchedAt`.
 */

export const WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY = 'mind-weave.workflowEditor.panelWidths';

export const WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES = 96;
const MAX_JSON_CHARS = 50_000;

const SCHEMA_VERSION = 1 as const;

export interface StoredPanelWidthsEntry {
    left: number;
    right: number;
    touchedAt: number;
}

interface StoredDocumentV1 {
    v: typeof SCHEMA_VERSION;
    entries: Record<string, StoredPanelWidthsEntry>;
}

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function parseDocument(raw: string | null): StoredDocumentV1 | null {
    if (raw == null || raw === '') return null;
    try {
        const parsed: unknown = JSON.parse(raw);
        if (!isRecord(parsed) || parsed.v !== SCHEMA_VERSION) return null;
        const entriesRaw = parsed.entries;
        if (!isRecord(entriesRaw)) return null;
        const entries: Record<string, StoredPanelWidthsEntry> = {};
        for (const [k, val] of Object.entries(entriesRaw)) {
            if (!isRecord(val)) continue;
            const left = val.left;
            const right = val.right;
            const touchedAt = val.touchedAt;
            if (typeof left !== 'number' || typeof right !== 'number' || typeof touchedAt !== 'number') continue;
            if (!Number.isFinite(left) || !Number.isFinite(right) || !Number.isFinite(touchedAt)) continue;
            entries[k] = { left, right, touchedAt };
        }
        return { v: SCHEMA_VERSION, entries };
    } catch {
        return null;
    }
}

function pruneByEntryCount(
    entries: Record<string, StoredPanelWidthsEntry>,
    maxEntries: number,
    keepId: string | null,
): Record<string, StoredPanelWidthsEntry> {
    const keys = Object.keys(entries);
    if (keys.length <= maxEntries) return entries;
    const sorted = [...keys].sort((a, b) => entries[a].touchedAt - entries[b].touchedAt);
    const next = { ...entries };
    let removeCount = keys.length - maxEntries;
    for (const id of sorted) {
        if (removeCount <= 0) break;
        if (keepId != null && id === keepId) continue;
        delete next[id];
        removeCount--;
    }
    return next;
}

function pruneByJsonSize(
    entries: Record<string, StoredPanelWidthsEntry>,
    keepId: string | null,
): Record<string, StoredPanelWidthsEntry> {
    let doc: StoredDocumentV1 = { v: SCHEMA_VERSION, entries };
    let serialized = JSON.stringify(doc);
    if (serialized.length <= MAX_JSON_CHARS) return entries;

    const sorted = Object.keys(entries).sort((a, b) => entries[a].touchedAt - entries[b].touchedAt);
    const next = { ...entries };
    for (const id of sorted) {
        if (serialized.length <= MAX_JSON_CHARS) break;
        if (keepId != null && id === keepId) continue;
        delete next[id];
        doc = { v: SCHEMA_VERSION, entries: next };
        serialized = JSON.stringify(doc);
    }
    return next;
}

function readDoc(storage: Storage): StoredDocumentV1 | null {
    try {
        return parseDocument(storage.getItem(WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY));
    } catch {
        return null;
    }
}

function writeDoc(storage: Storage, doc: StoredDocumentV1): void {
    try {
        let serialized = JSON.stringify(doc);
        if (serialized.length > MAX_JSON_CHARS) {
            const pruned = pruneByJsonSize(doc.entries, null);
            doc = { v: SCHEMA_VERSION, entries: pruned };
            serialized = JSON.stringify(doc);
        }
        storage.setItem(WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY, serialized);
    } catch {
        /* quota or private mode */
    }
}

/** Read stored widths for a workflow, or null if missing / invalid. */
export function readPanelWidthsForWorkflow(
    workflowId: string,
    storage: Storage = localStorage,
): { left: number; right: number } | null {
    const doc = readDoc(storage);
    if (!doc) return null;
    const e = doc.entries[workflowId];
    if (!e) return null;
    return { left: e.left, right: e.right };
}

/** Upsert widths for a workflow and persist (with LRU + size cap). */
export function writePanelWidthsForWorkflow(
    workflowId: string,
    left: number,
    right: number,
    storage: Storage = localStorage,
): void {
    const doc = readDoc(storage) ?? { v: SCHEMA_VERSION, entries: {} };
    const now = Date.now();
    const entries = pruneByEntryCount(
        {
            ...doc.entries,
            [workflowId]: { left, right, touchedAt: now },
        },
        WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES,
        workflowId,
    );
    let pruned = pruneByJsonSize(entries, workflowId);
    pruned = pruneByEntryCount(pruned, WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES, workflowId);
    writeDoc(storage, { v: SCHEMA_VERSION, entries: pruned });
}
