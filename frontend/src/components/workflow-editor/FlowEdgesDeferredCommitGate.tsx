/**
 * Defers mounting workflow edges until React Flow has measured nodes and dynamic
 * handles (e.g. Start sandbox_tick) are registered via updateNodeInternals.
 */
import { useEffect, type RefObject } from 'react';
import { useNodesInitialized, type Edge } from '@xyflow/react';

export type FlowEdgesDeferredCommitGateProps = {
    deferToken: number;
    pendingEdgesRef: RefObject<Edge[] | null>;
    onCommit: (edges: Edge[]) => void;
};

export function FlowEdgesDeferredCommitGate({
    deferToken,
    pendingEdgesRef,
    onCommit,
}: FlowEdgesDeferredCommitGateProps) {
    const nodesInitialized = useNodesInitialized();

    useEffect(() => {
        const pending = pendingEdgesRef.current;
        if (!pending?.length || !nodesInitialized) return;

        let raf1 = 0;
        let raf2 = 0;
        raf1 = requestAnimationFrame(() => {
            raf2 = requestAnimationFrame(() => {
                const edges = pendingEdgesRef.current;
                if (!edges?.length) return;
                onCommit(edges);
            });
        });

        return () => {
            cancelAnimationFrame(raf1);
            cancelAnimationFrame(raf2);
        };
    }, [deferToken, nodesInitialized, onCommit, pendingEdgesRef]);

    return null;
}
