/**
 * Calls React Flow's fitView when the canvas "session" key changes (workflow or run selection),
 * matching the bottom-left Controls fit button.
 *
 * Do not call fitView until useNodesInitialized() is true: fitView() only includes nodes that
 * already have measured width/height; running it early can collapse the bounds to the first
 * measured node (often Start) instead of the full graph.
 *
 * {@link FitViewOnWorkflowCanvasResize} refits only when the canvas **container** resizes (e.g.
 * overlay panels, sidebar drag). It does not depend on node measurement, so adding nodes does not
 * trigger a refit.
 */
import { useEffect, useRef, type RefObject } from 'react';
import { useNodesInitialized, useReactFlow } from '@xyflow/react';

export const WORKFLOW_CANVAS_FIT_VIEW_OPTIONS = { padding: 0.12, duration: 200 } as const;

/** Deeper zoom-out than React Flow’s default minZoom (0.5) for large DAGs. */
export const WORKFLOW_CANVAS_MIN_ZOOM = 0.05;

export function FitViewOnWorkflowCanvasKey({ fitKey }: { fitKey: string | null }) {
    const { fitView } = useReactFlow();
    const nodesInitialized = useNodesInitialized();
    const lastFittedForKeyRef = useRef<string | null>(null);

    useEffect(() => {
        if (!fitKey) {
            lastFittedForKeyRef.current = null;
            return;
        }
        if (!nodesInitialized) return;
        if (lastFittedForKeyRef.current === fitKey) return;
        const raf = requestAnimationFrame(() => {
            fitView({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
            lastFittedForKeyRef.current = fitKey;
        });
        return () => cancelAnimationFrame(raf);
    }, [fitKey, fitView, nodesInitialized]);
    return null;
}

/**
 * Refits the viewport when the canvas wrapper element is resized (sidebar overlays, rotation).
 * Debounced to avoid fighting continuous drags.
 */
export function FitViewOnWorkflowCanvasResize({
    fitKey,
    containerRef,
}: {
    fitKey: string | null;
    containerRef: RefObject<HTMLElement | null>;
}) {
    const { fitView } = useReactFlow();

    useEffect(() => {
        const el = containerRef.current;
        if (!el || !fitKey) return;

        let timeoutId = 0;
        const scheduleFit = () => {
            window.clearTimeout(timeoutId);
            timeoutId = window.setTimeout(() => {
                requestAnimationFrame(() => {
                    void fitView({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
                });
            }, 120);
        };

        const ro = new ResizeObserver(scheduleFit);
        ro.observe(el);

        return () => {
            window.clearTimeout(timeoutId);
            ro.disconnect();
        };
    }, [fitKey, fitView, containerRef]);

    return null;
}
