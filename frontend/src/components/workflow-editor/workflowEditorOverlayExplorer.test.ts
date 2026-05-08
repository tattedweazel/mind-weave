import { describe, expect, it } from 'vitest';
import { shouldOpenCompactExplorerForInspectorSignals } from './workflowEditorOverlayExplorer';

const base = {
    overlayPanels: true,
    inspectorOpen: true,
    hasPendingNodeDelete: false,
    hasPendingEdgeDelete: false,
    hasNodeDeleteKeyboardMessage: false,
};

describe('shouldOpenCompactExplorerForInspectorSignals', () => {
    it('is false when overlayPanels is false', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                overlayPanels: false,
                hasPendingNodeDelete: true,
            }),
        ).toBe(false);
    });

    it('is false when inspectorOpen is false', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                inspectorOpen: false,
                hasPendingNodeDelete: true,
            }),
        ).toBe(false);
    });

    it('is false when overlay and inspector are on but no signals', () => {
        expect(shouldOpenCompactExplorerForInspectorSignals({ ...base })).toBe(false);
    });

    it('is true when pending node delete', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                hasPendingNodeDelete: true,
            }),
        ).toBe(true);
    });

    it('is true when pending edge delete', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                hasPendingEdgeDelete: true,
            }),
        ).toBe(true);
    });

    it('is true when node delete keyboard message', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                hasNodeDeleteKeyboardMessage: true,
            }),
        ).toBe(true);
    });

    it('is true when multiple signals are set', () => {
        expect(
            shouldOpenCompactExplorerForInspectorSignals({
                ...base,
                hasPendingNodeDelete: true,
                hasPendingEdgeDelete: true,
                hasNodeDeleteKeyboardMessage: true,
            }),
        ).toBe(true);
    });
});
