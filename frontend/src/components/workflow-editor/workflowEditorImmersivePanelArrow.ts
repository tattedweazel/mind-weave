/**
 * Immersive workflow editor: keyboard arrows and edge taps toggle slide-over
 * Palette / Explorer, mirroring the toolbar buttons.
 */

export type ImmersivePanelArrowKeyEvent = Pick<
    KeyboardEvent,
    'key' | 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey'
>;

export type ImmersivePanelArrowOptions = {
    immersive: boolean;
    targetIsTextEntry: boolean;
    runInputWizardOpen: boolean;
    workflowImportModalOpen: boolean;
    outputOverrideModalOpen: boolean;
    compactPaletteOpen: boolean;
    compactExplorerOpen: boolean;
    event: ImmersivePanelArrowKeyEvent;
};

export type ImmersivePanelToggleResult = {
    nextPaletteOpen: boolean;
    nextExplorerOpen: boolean;
};

/** Same behavior as the toolbar Palette control. */
export function nextImmersivePanelStatePaletteToggle(
    compactPaletteOpen: boolean,
    compactExplorerOpen: boolean,
): ImmersivePanelToggleResult {
    const p = compactPaletteOpen;
    const x = compactExplorerOpen;
    if (p) return { nextPaletteOpen: false, nextExplorerOpen: x };
    return { nextPaletteOpen: true, nextExplorerOpen: false };
}

/** Same behavior as the toolbar Explorer control. */
export function nextImmersivePanelStateExplorerToggle(
    compactPaletteOpen: boolean,
    compactExplorerOpen: boolean,
): ImmersivePanelToggleResult {
    const p = compactPaletteOpen;
    const x = compactExplorerOpen;
    if (x) return { nextPaletteOpen: p, nextExplorerOpen: false };
    return { nextPaletteOpen: false, nextExplorerOpen: true };
}

export type ImmersivePanelEdgeTapOptions = {
    immersive: boolean;
    runInputWizardOpen: boolean;
    workflowImportModalOpen: boolean;
    outputOverrideModalOpen: boolean;
    compactPaletteOpen: boolean;
    compactExplorerOpen: boolean;
};

/**
 * Edge tap (left = Palette, right = Explorer) when immersive and no blocking modals.
 */
export function immersivePanelEdgeTapResult(
    edge: 'left' | 'right',
    options: ImmersivePanelEdgeTapOptions,
): ImmersivePanelToggleResult | null {
    if (!options.immersive) return null;
    if (
        options.runInputWizardOpen ||
        options.workflowImportModalOpen ||
        options.outputOverrideModalOpen
    ) {
        return null;
    }
    const { compactPaletteOpen: p, compactExplorerOpen: x } = options;
    if (edge === 'left') return nextImmersivePanelStatePaletteToggle(p, x);
    return nextImmersivePanelStateExplorerToggle(p, x);
}

/**
 * If the event should toggle overlay panels (immersive only), returns the next open flags.
 * Otherwise returns null.
 */
export function immersivePanelArrowShortcutResult(
    options: ImmersivePanelArrowOptions,
): ImmersivePanelToggleResult | null {
    const { immersive, targetIsTextEntry, event } = options;
    if (!immersive) return null;
    if (
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        event.shiftKey
    ) {
        return null;
    }
    if (targetIsTextEntry) return null;
    if (
        options.runInputWizardOpen ||
        options.workflowImportModalOpen ||
        options.outputOverrideModalOpen
    ) {
        return null;
    }

    const { key } = event;
    if (key !== 'ArrowLeft' && key !== 'ArrowRight') return null;

    const { compactPaletteOpen: p, compactExplorerOpen: x } = options;

    if (key === 'ArrowLeft') {
        return nextImmersivePanelStatePaletteToggle(p, x);
    }
    return nextImmersivePanelStateExplorerToggle(p, x);
}

/** Max pointer movement (px) for an edge strip interaction to count as a tap. */
export const IMMERSIVE_PANEL_EDGE_TAP_MOVE_THRESHOLD_PX = 10;
