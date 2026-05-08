/** Classes and helpers for canvas selection chrome (Explorer sync). */

import type { Node } from '@xyflow/react';

export const FLOW_EDGE_SELECTED_CLASS = 'mw-flow-edge-selected';

export function canvasSelectedNodes(nodes: Node[]): Node[] {
    return nodes.filter(n => n.selected);
}

/** When exactly one node is selected on the canvas, return it; otherwise `null` (none or multi). */
export function explorerTargetNodeFromCanvasSelection(nodes: Node[]): Node | null {
    const s = canvasSelectedNodes(nodes);
    return s.length === 1 ? s[0]! : null;
}

export function multiCanvasSelectionActive(nodes: Node[]): boolean {
    return canvasSelectedNodes(nodes).length > 1;
}

/** One pass over `nodes` for Explorer vs multi-select UI. */
export function partitionCanvasSelection(nodes: Node[]): {
    selectedCanvasNodes: Node[];
    explorerTargetNode: Node | null;
    multiCanvasSelectActive: boolean;
} {
    const selectedCanvasNodes = canvasSelectedNodes(nodes);
    const k = selectedCanvasNodes.length;
    return {
        selectedCanvasNodes,
        explorerTargetNode: k === 1 ? selectedCanvasNodes[0]! : null,
        multiCanvasSelectActive: k > 1,
    };
}

export function mergeCanvasSelectionIntoNodeData<D extends Record<string, unknown>>(
    data: D,
    isCanvasSelected: boolean,
): D & { isCanvasSelected: boolean } {
    return {
        ...data,
        isCanvasSelected,
    };
}

export function flowEdgeSelectionClassName(
    existing: string | undefined,
    edgeId: string,
    selectedId: string | null | undefined,
): string | undefined {
    if (selectedId == null || selectedId !== edgeId) return existing;
    const parts = [FLOW_EDGE_SELECTED_CLASS, existing].filter(Boolean);
    return parts.length ? parts.join(' ') : undefined;
}
