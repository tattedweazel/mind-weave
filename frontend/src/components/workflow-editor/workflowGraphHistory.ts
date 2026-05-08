import type { Edge, Node } from '@xyflow/react';

/** Single knob for how many graph snapshots are kept for Undo. */
export const WORKFLOW_GRAPH_UNDO_PAST_MAX = 10;

export type WorkflowGraphSnapshot = {
    nodes: Node[];
    edges: Edge[];
};

/** Clone and drop run/selection UI so undo does not resurrect transient canvas chrome. */
export function normalizeGraphForHistorySnapshot(nodes: Node[], edges: Edge[]): WorkflowGraphSnapshot {
    const raw = structuredClone({ nodes, edges }) as WorkflowGraphSnapshot;
    for (const n of raw.nodes) {
        n.selected = false;
        if (n.data && typeof n.data === 'object' && 'isRunning' in (n.data as object)) {
            delete (n.data as Record<string, unknown>).isRunning;
        }
    }
    for (const e of raw.edges) {
        e.animated = false;
        e.selected = false;
    }
    return raw;
}

export type WorkflowGraphHistory = {
    pushSnapshot: (nodes: Node[], edges: Edge[]) => void;
    undo: (currentNodes: Node[], currentEdges: Edge[]) => WorkflowGraphSnapshot | null;
    redo: (currentNodes: Node[], currentEdges: Edge[]) => WorkflowGraphSnapshot | null;
    clear: () => void;
    canUndo: () => boolean;
    canRedo: () => boolean;
};

export function createWorkflowGraphHistory(): WorkflowGraphHistory {
    let past: WorkflowGraphSnapshot[] = [];
    let future: WorkflowGraphSnapshot[] = [];

    const trimPast = () => {
        while (past.length > WORKFLOW_GRAPH_UNDO_PAST_MAX) {
            past.shift();
        }
    };

    return {
        pushSnapshot(nodes, edges) {
            past.push(normalizeGraphForHistorySnapshot(nodes, edges));
            trimPast();
            future = [];
        },

        undo(currentNodes, currentEdges) {
            if (past.length === 0) return null;
            const restored = past.pop()!;
            future.push(normalizeGraphForHistorySnapshot(currentNodes, currentEdges));
            return restored;
        },

        redo(currentNodes, currentEdges) {
            if (future.length === 0) return null;
            const restored = future.pop()!;
            past.push(normalizeGraphForHistorySnapshot(currentNodes, currentEdges));
            trimPast();
            return restored;
        },

        clear() {
            past = [];
            future = [];
        },

        canUndo: () => past.length > 0,
        canRedo: () => future.length > 0,
    };
}
