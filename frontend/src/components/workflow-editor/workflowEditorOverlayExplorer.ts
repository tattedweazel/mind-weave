/**
 * Overlay / immersive mode uses slide-over Explorer; keyboard-driven delete confirmation
 * and validation messages render inside that panel — it must be open for them to be visible and clickable.
 */
export function shouldOpenCompactExplorerForInspectorSignals(args: {
    overlayPanels: boolean;
    inspectorOpen: boolean;
    hasPendingNodeDelete: boolean;
    hasPendingEdgeDelete: boolean;
    hasNodeDeleteKeyboardMessage: boolean;
}): boolean {
    if (!args.overlayPanels || !args.inspectorOpen) return false;
    return (
        args.hasPendingNodeDelete ||
        args.hasPendingEdgeDelete ||
        args.hasNodeDeleteKeyboardMessage
    );
}
