import { afterEach, describe, it, expect, vi } from 'vitest';
import {
    readPanelWidthsForWorkflow,
    writePanelWidthsForWorkflow,
    WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES,
    WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY,
} from './workflowEditorPanelWidthsStorage';

function makeMemoryStorage(): Storage {
    const m = new Map<string, string>();
    return {
        get length() {
            return m.size;
        },
        clear: () => m.clear(),
        getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
        key: (i: number) => Array.from(m.keys())[i] ?? null,
        removeItem: (k: string) => {
            m.delete(k);
        },
        setItem: (k: string, v: string) => {
            m.set(k, v);
        },
    };
}

describe('workflowEditorPanelWidthsStorage', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('round-trips widths for a workflow', () => {
        const storage = makeMemoryStorage();
        writePanelWidthsForWorkflow('wf-1', 300, 400, storage);
        expect(readPanelWidthsForWorkflow('wf-1', storage)).toEqual({ left: 300, right: 400 });
    });

    it('returns null for unknown workflow', () => {
        const storage = makeMemoryStorage();
        expect(readPanelWidthsForWorkflow('nope', storage)).toBeNull();
    });

    it('ignores corrupt JSON', () => {
        const storage = makeMemoryStorage();
        storage.setItem(WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY, '{ not json');
        expect(readPanelWidthsForWorkflow('wf-1', storage)).toBeNull();
    });

    it('ignores wrong schema version', () => {
        const storage = makeMemoryStorage();
        storage.setItem(
            WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY,
            JSON.stringify({ v: 99, entries: { a: { left: 1, right: 2, touchedAt: 0 } } }),
        );
        expect(readPanelWidthsForWorkflow('a', storage)).toBeNull();
    });

    it('evicts oldest entry when over max count', () => {
        const storage = makeMemoryStorage();
        let t = 1000;
        vi.spyOn(Date, 'now').mockImplementation(() => {
            t += 1;
            return t;
        });
        for (let i = 0; i < WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES; i++) {
            writePanelWidthsForWorkflow(`wf-${i}`, 256, 320, storage);
        }
        expect(readPanelWidthsForWorkflow('wf-0', storage)).not.toBeNull();
        writePanelWidthsForWorkflow(`wf-${WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES}`, 280, 330, storage);
        expect(readPanelWidthsForWorkflow('wf-0', storage)).toBeNull();
        expect(readPanelWidthsForWorkflow('wf-1', storage)).not.toBeNull();
        expect(readPanelWidthsForWorkflow(`wf-${WORKFLOW_EDITOR_PANEL_WIDTHS_MAX_ENTRIES}`, storage)).toEqual({
            left: 280,
            right: 330,
        });
    });

    it('updates touchedAt for existing workflow without creating extra keys', () => {
        const storage = makeMemoryStorage();
        writePanelWidthsForWorkflow('wf-a', 256, 320, storage);
        writePanelWidthsForWorkflow('wf-a', 400, 500, storage);
        expect(readPanelWidthsForWorkflow('wf-a', storage)).toEqual({ left: 400, right: 500 });
        const raw = storage.getItem(WORKFLOW_EDITOR_PANEL_WIDTHS_STORAGE_KEY)!;
        const doc = JSON.parse(raw) as { entries: Record<string, unknown> };
        expect(Object.keys(doc.entries)).toEqual(['wf-a']);
    });
});
