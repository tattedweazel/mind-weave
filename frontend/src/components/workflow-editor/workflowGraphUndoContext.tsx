import React, { createContext, useContext } from 'react';
import type { EdgeChange, NodeChange } from '@xyflow/react';

/** Tracks high-frequency canvas gestures so we do not push undo on every frame. */
export type WorkflowCanvasInteractionFlags = {
    nodeDrag: boolean;
    nodeResize: boolean;
};

export type WorkflowGraphUndoContextValue = {
    recordBeforeGraphMutation: () => void;
    interactionRef: React.MutableRefObject<WorkflowCanvasInteractionFlags>;
};

export const WorkflowGraphUndoContext = createContext<WorkflowGraphUndoContextValue | null>(null);

export function useWorkflowGraphUndo(): WorkflowGraphUndoContextValue | null {
    return useContext(WorkflowGraphUndoContext);
}

/** No-op when used outside WorkflowEditor (e.g. read-only replay). */
export function useRecordGraphBeforeMutation(): () => void {
    const ctx = useContext(WorkflowGraphUndoContext);
    return ctx?.recordBeforeGraphMutation ?? (() => {});
}

export function reactFlowNodeChangesSkipUndoRecord(
    changes: NodeChange[],
    interaction: WorkflowCanvasInteractionFlags,
): boolean {
    if (changes.length === 0) return true;
    if (changes.every(c => c.type === 'select')) return true;
    /** `replace` is used when embedded nodes call `useReactFlow().setNodes` (e.g. annotation note body); undo is bounded via `onFocus` there. */
    if (changes.every(c => c.type === 'replace')) return true;
    if (changes.every(c => c.type === 'position') && interaction.nodeDrag) return true;
    if (changes.every(c => c.type === 'dimensions') && interaction.nodeResize) return true;
    return false;
}

export function reactFlowEdgeChangesSkipUndoRecord(changes: EdgeChange[]): boolean {
    return changes.length === 0 || changes.every(c => c.type === 'select');
}
