/** Layout constraints for workflow editor left / right panels (palette + inspector). */

/** True when the editor should use slide-over palette/Explorer (narrow viewport or app immersive fullscreen). */
export function workflowEditorOverlayPanels(compactViewport: boolean, immersiveMode: boolean): boolean {
    return compactViewport || immersiveMode;
}

export const LEFT_PANEL_MIN_PX = 256;
export const RIGHT_PANEL_MIN_PX = 320;
/** Minimum width of the center (canvas) column — matches historical default inspector width. */
export const CENTER_PANEL_MIN_PX = 320;
export const SIDE_PANEL_MAX_FRACTION = 0.5;

export const DEFAULT_LEFT_PANEL_WIDTH_PX = LEFT_PANEL_MIN_PX;
export const DEFAULT_RIGHT_PANEL_WIDTH_PX = RIGHT_PANEL_MIN_PX;

/** Max height for scrollable Primitives / Skills / Utilities / Controls lists (9rem × 1.5 = 13.5rem). */
export const PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS = 'max-h-[13.5rem]';

export interface PanelWidths {
    left: number;
    right: number;
}

/**
 * Clamp left and right panel widths so:
 * - each side stays within min and at most SIDE_PANEL_MAX_FRACTION of viewport width
 * - center column has at least CENTER_PANEL_MIN_PX when the right inspector is closed (right treated as 0)
 * - when the inspector is open, center has at least CENTER_PANEL_MIN_PX with both sidebars
 *
 * When the viewport is too narrow to satisfy all mins, a few iterations shrink the panels until the
 * center constraint holds (right may end below RIGHT_PANEL_MIN_PX in extreme cases).
 */
export function clampPanelWidths(
    viewportWidth: number,
    left: number,
    right: number,
    inspectorOpen: boolean,
): PanelWidths {
    if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) {
        return {
            left: DEFAULT_LEFT_PANEL_WIDTH_PX,
            right: inspectorOpen ? DEFAULT_RIGHT_PANEL_WIDTH_PX : right,
        };
    }

    let L = left;
    let R = right;

    for (let i = 0; i < 8; i++) {
        const rForCenter = inspectorOpen ? R : 0;
        const maxL = Math.min(viewportWidth * SIDE_PANEL_MAX_FRACTION, viewportWidth - rForCenter - CENTER_PANEL_MIN_PX);
        L = Math.min(Math.max(L, LEFT_PANEL_MIN_PX), Math.max(maxL, LEFT_PANEL_MIN_PX));

        if (!inspectorOpen) {
            return { left: L, right: R };
        }

        const maxR = Math.min(viewportWidth * SIDE_PANEL_MAX_FRACTION, viewportWidth - L - CENTER_PANEL_MIN_PX);
        R = Math.min(Math.max(R, RIGHT_PANEL_MIN_PX), Math.max(maxR, RIGHT_PANEL_MIN_PX));
    }

    return { left: L, right: R };
}
