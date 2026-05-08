import { describe, it, expect } from 'vitest';
import {
    CENTER_PANEL_MIN_PX,
    clampPanelWidths,
    DEFAULT_LEFT_PANEL_WIDTH_PX,
    DEFAULT_RIGHT_PANEL_WIDTH_PX,
    LEFT_PANEL_MIN_PX,
    PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS,
    RIGHT_PANEL_MIN_PX,
    workflowEditorOverlayPanels,
} from './workflowEditorPanelLayout';

describe('workflowEditorPanelLayout', () => {
    it('exports palette section scroll cap (50% taller than legacy 9rem Workflows cap)', () => {
        expect(PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS).toBe('max-h-[13.5rem]');
    });
});

describe('workflowEditorOverlayPanels', () => {
    it('is true when viewport is compact', () => {
        expect(workflowEditorOverlayPanels(true, false)).toBe(true);
    });

    it('is true when immersive fullscreen is on', () => {
        expect(workflowEditorOverlayPanels(false, true)).toBe(true);
    });

    it('is true when both compact and immersive', () => {
        expect(workflowEditorOverlayPanels(true, true)).toBe(true);
    });

    it('is false when neither compact nor immersive', () => {
        expect(workflowEditorOverlayPanels(false, false)).toBe(false);
    });
});

describe('clampPanelWidths', () => {
    it('returns defaults for non-positive viewport', () => {
        expect(clampPanelWidths(0, 400, 400, true)).toEqual({
            left: DEFAULT_LEFT_PANEL_WIDTH_PX,
            right: DEFAULT_RIGHT_PANEL_WIDTH_PX,
        });
        expect(clampPanelWidths(NaN, 400, 400, true).left).toBe(DEFAULT_LEFT_PANEL_WIDTH_PX);
    });

    it('keeps defaults at wide viewport with inspector open', () => {
        const r = clampPanelWidths(1600, LEFT_PANEL_MIN_PX, RIGHT_PANEL_MIN_PX, true);
        expect(r.left).toBe(LEFT_PANEL_MIN_PX);
        expect(r.right).toBe(RIGHT_PANEL_MIN_PX);
    });

    it('caps each side at half viewport when center min allows', () => {
        const r = clampPanelWidths(1200, 700, 700, true);
        expect(r.left).toBeLessThanOrEqual(600);
        expect(r.right).toBeLessThanOrEqual(600);
        expect(r.left + r.right + CENTER_PANEL_MIN_PX).toBeLessThanOrEqual(1200 + 0.01);
    });

    it('shrinks sidebars so center is at least CENTER_PANEL_MIN_PX', () => {
        const r = clampPanelWidths(900, 400, 400, true);
        expect(r.left + r.right).toBeLessThanOrEqual(900 - CENTER_PANEL_MIN_PX + 0.001);
        expect(r.left).toBeGreaterThanOrEqual(LEFT_PANEL_MIN_PX);
    });

    it('treats right as zero for center constraint when inspector closed', () => {
        const r = clampPanelWidths(700, 500, DEFAULT_RIGHT_PANEL_WIDTH_PX, false);
        expect(r.left).toBeLessThanOrEqual(700 - CENTER_PANEL_MIN_PX);
        expect(r.right).toBe(DEFAULT_RIGHT_PANEL_WIDTH_PX);
    });

    it('allows wide left when inspector closed', () => {
        const r = clampPanelWidths(2000, 700, DEFAULT_RIGHT_PANEL_WIDTH_PX, false);
        expect(r.left).toBe(700);
    });

    it('narrows panels on tight viewport with inspector open', () => {
        const w = LEFT_PANEL_MIN_PX + RIGHT_PANEL_MIN_PX + CENTER_PANEL_MIN_PX;
        const r = clampPanelWidths(w, 400, 400, true);
        expect(r.left + r.right + CENTER_PANEL_MIN_PX).toBeLessThanOrEqual(w + 0.01);
    });
});
