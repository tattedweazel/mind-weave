import { describe, expect, it } from 'vitest';
import {
    immersivePanelArrowShortcutResult,
    immersivePanelEdgeTapResult,
} from './workflowEditorImmersivePanelArrow';

const base = {
    immersive: true,
    targetIsTextEntry: false,
    runInputWizardOpen: false,
    workflowImportModalOpen: false,
    outputOverrideModalOpen: false,
    compactPaletteOpen: false,
    compactExplorerOpen: false,
    event: { key: 'ArrowLeft', metaKey: false, ctrlKey: false, altKey: false, shiftKey: false },
};

describe('immersivePanelArrowShortcutResult', () => {
    it('returns null when not immersive', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                immersive: false,
                event: { ...base.event, key: 'ArrowLeft' },
            }),
        ).toBeNull();
    });

    it('returns null for non-arrow keys', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                event: { ...base.event, key: 'a' },
            }),
        ).toBeNull();
    });

    it('returns null when metaKey', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                event: { ...base.event, key: 'ArrowRight', metaKey: true },
            }),
        ).toBeNull();
    });

    it('returns null when ctrlKey', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                event: { ...base.event, key: 'ArrowRight', ctrlKey: true },
            }),
        ).toBeNull();
    });

    it('returns null when altKey', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                event: { ...base.event, key: 'ArrowRight', altKey: true },
            }),
        ).toBeNull();
    });

    it('returns null when shiftKey', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                event: { ...base.event, key: 'ArrowRight', shiftKey: true },
            }),
        ).toBeNull();
    });

    it('returns null when targetIsTextEntry', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                targetIsTextEntry: true,
                event: { ...base.event, key: 'ArrowLeft' },
            }),
        ).toBeNull();
    });

    it('returns null when runInputWizardOpen', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                runInputWizardOpen: true,
                event: { ...base.event, key: 'ArrowLeft' },
            }),
        ).toBeNull();
    });

    it('returns null when workflowImportModalOpen', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                workflowImportModalOpen: true,
                event: { ...base.event, key: 'ArrowLeft' },
            }),
        ).toBeNull();
    });

    it('returns null when outputOverrideModalOpen', () => {
        expect(
            immersivePanelArrowShortcutResult({
                ...base,
                outputOverrideModalOpen: true,
                event: { ...base.event, key: 'ArrowLeft' },
            }),
        ).toBeNull();
    });

    describe('ArrowLeft', () => {
        it('closes palette when palette is open', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: true,
                    compactExplorerOpen: false,
                    event: { ...base.event, key: 'ArrowLeft' },
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: false });
        });

        it('keeps explorer state when closing palette and explorer was open', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: true,
                    compactExplorerOpen: true,
                    event: { ...base.event, key: 'ArrowLeft' },
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: true });
        });

        it('opens palette and closes explorer when palette closed', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: false,
                    compactExplorerOpen: true,
                    event: { ...base.event, key: 'ArrowLeft' },
                }),
            ).toEqual({ nextPaletteOpen: true, nextExplorerOpen: false });
        });

        it('opens palette when both closed', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: false,
                    compactExplorerOpen: false,
                    event: { ...base.event, key: 'ArrowLeft' },
                }),
            ).toEqual({ nextPaletteOpen: true, nextExplorerOpen: false });
        });
    });

    describe('ArrowRight', () => {
        it('closes explorer when explorer is open', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: false,
                    compactExplorerOpen: true,
                    event: { ...base.event, key: 'ArrowRight' },
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: false });
        });

        it('keeps palette state when closing explorer and palette was open', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: true,
                    compactExplorerOpen: true,
                    event: { ...base.event, key: 'ArrowRight' },
                }),
            ).toEqual({ nextPaletteOpen: true, nextExplorerOpen: false });
        });

        it('opens explorer and closes palette when explorer closed', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: true,
                    compactExplorerOpen: false,
                    event: { ...base.event, key: 'ArrowRight' },
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: true });
        });

        it('opens explorer when both closed', () => {
            expect(
                immersivePanelArrowShortcutResult({
                    ...base,
                    compactPaletteOpen: false,
                    compactExplorerOpen: false,
                    event: { ...base.event, key: 'ArrowRight' },
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: true });
        });
    });
});

const edgeBase = {
    immersive: true,
    runInputWizardOpen: false,
    workflowImportModalOpen: false,
    outputOverrideModalOpen: false,
    compactPaletteOpen: false,
    compactExplorerOpen: false,
};

describe('immersivePanelEdgeTapResult', () => {
    it('returns null when not immersive', () => {
        expect(
            immersivePanelEdgeTapResult('left', {
                ...edgeBase,
                immersive: false,
            }),
        ).toBeNull();
    });

    it('returns null when runInputWizardOpen', () => {
        expect(
            immersivePanelEdgeTapResult('left', {
                ...edgeBase,
                runInputWizardOpen: true,
            }),
        ).toBeNull();
    });

    it('returns null when workflowImportModalOpen', () => {
        expect(
            immersivePanelEdgeTapResult('right', {
                ...edgeBase,
                workflowImportModalOpen: true,
            }),
        ).toBeNull();
    });

    it('returns null when outputOverrideModalOpen', () => {
        expect(
            immersivePanelEdgeTapResult('right', {
                ...edgeBase,
                outputOverrideModalOpen: true,
            }),
        ).toBeNull();
    });

    describe('left edge (palette)', () => {
        it('mirrors ArrowLeft when palette open', () => {
            expect(
                immersivePanelEdgeTapResult('left', {
                    ...edgeBase,
                    compactPaletteOpen: true,
                    compactExplorerOpen: false,
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: false });
        });

        it('mirrors ArrowLeft when opening palette from explorer', () => {
            expect(
                immersivePanelEdgeTapResult('left', {
                    ...edgeBase,
                    compactPaletteOpen: false,
                    compactExplorerOpen: true,
                }),
            ).toEqual({ nextPaletteOpen: true, nextExplorerOpen: false });
        });
    });

    describe('right edge (explorer)', () => {
        it('mirrors ArrowRight when explorer open', () => {
            expect(
                immersivePanelEdgeTapResult('right', {
                    ...edgeBase,
                    compactPaletteOpen: false,
                    compactExplorerOpen: true,
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: false });
        });

        it('mirrors ArrowRight when opening explorer from palette', () => {
            expect(
                immersivePanelEdgeTapResult('right', {
                    ...edgeBase,
                    compactPaletteOpen: true,
                    compactExplorerOpen: false,
                }),
            ).toEqual({ nextPaletteOpen: false, nextExplorerOpen: true });
        });
    });
});
