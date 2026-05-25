/**
 * Workflow editor React Flow canvas with palette drag-and-drop.
 * Uses ReactFlowProvider + useReactFlow (official DnD pattern) so screenToFlowPosition
 * is always available; drop handlers live on ReactFlow, not a wrapper div.
 */
import React, { useCallback, useRef, type RefObject } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    ConnectionMode,
    ReactFlowProvider,
    useReactFlow,
    type Node,
    type Edge,
    type Connection,
    type NodeChange,
    type EdgeChange,
    type OnConnect,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { FlowEdgesDeferredCommitGate } from './FlowEdgesDeferredCommitGate';
import {
    FitViewOnWorkflowCanvasKey,
    FitViewOnWorkflowCanvasResize,
    WORKFLOW_CANVAS_MIN_ZOOM,
} from './FitViewOnWorkflowCanvas';
import { nodeTypes } from './nodeTypes';
import {
    WorkflowGraphUndoContext,
    type WorkflowGraphUndoContextValue,
} from './workflowGraphUndoContext';

/** Node center offset applied after screenToFlowPosition (matches legacy palette drop). */
export const PALETTE_DROP_NODE_OFFSET = { x: 80, y: 40 } as const;

export type WorkflowEditorCanvasProps = {
    fitKey: string | null;
    flowEdgesReady: boolean;
    flowEdgesDeferToken: number;
    pendingFlowEdgesRef: RefObject<Edge[] | null>;
    onCommitFlowEdges: (edges: Edge[]) => void;
    nodes: Node[];
    edges: Edge[];
    onNodesChange: (changes: NodeChange[]) => void;
    onEdgesChange: (changes: EdgeChange[]) => void;
    onNodeDragStart: () => void;
    onNodeDragStop: () => void;
    onConnect: OnConnect;
    onNodeClick: (event: React.MouseEvent, node: Node) => void;
    onEdgeClick: (event: React.MouseEvent, edge: Edge) => void;
    onPaneClick: (event: React.MouseEvent) => void;
    isValidConnection: (connection: Connection | Edge) => boolean;
    onPaletteDrop: (
        type: string,
        position: { x: number; y: number },
        extra: Record<string, unknown>,
    ) => void;
    undoContextValue: WorkflowGraphUndoContextValue;
};

function WorkflowEditorCanvasInner({
    fitKey,
    flowEdgesReady,
    flowEdgesDeferToken,
    pendingFlowEdgesRef,
    onCommitFlowEdges,
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onNodeDragStart,
    onNodeDragStop,
    onConnect,
    onNodeClick,
    onEdgeClick,
    onPaneClick,
    isValidConnection,
    onPaletteDrop,
    undoContextValue,
}: WorkflowEditorCanvasProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const { screenToFlowPosition } = useReactFlow();

    const onDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            const type = e.dataTransfer.getData('nodeType');
            if (!type) return;
            const extra = JSON.parse(e.dataTransfer.getData('nodeExtra') || '{}') as Record<string, unknown>;
            const p = screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const position = {
                x: p.x - PALETTE_DROP_NODE_OFFSET.x,
                y: p.y - PALETTE_DROP_NODE_OFFSET.y,
            };
            onPaletteDrop(type, position, extra);
        },
        [screenToFlowPosition, onPaletteDrop],
    );

    return (
        <div ref={containerRef} className="flex-1 min-h-0 overflow-hidden touch-none">
            <WorkflowGraphUndoContext.Provider value={undoContextValue}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    defaultEdgeOptions={{ zIndex: 1000 }}
                    connectionMode={ConnectionMode.Loose}
                    deleteKeyCode={null}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeDragStart={onNodeDragStart}
                    onNodeDragStop={onNodeDragStop}
                    onConnect={onConnect}
                    onNodeClick={onNodeClick}
                    onEdgeClick={onEdgeClick}
                    onPaneClick={onPaneClick}
                    isValidConnection={isValidConnection}
                    nodeTypes={nodeTypes}
                    minZoom={WORKFLOW_CANVAS_MIN_ZOOM}
                    zoomOnScroll
                    zoomOnPinch
                    panOnScroll={false}
                    zoomOnDoubleClick={false}
                    preventScrolling
                    onDragOver={onDragOver}
                    onDrop={onDrop}
                    colorMode={
                        typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
                            ? 'dark'
                            : 'light'
                    }
                    proOptions={{ hideAttribution: true }}
                    className="bg-mw-page"
                >
                    <FlowEdgesDeferredCommitGate
                        deferToken={flowEdgesDeferToken}
                        pendingEdgesRef={pendingFlowEdgesRef}
                        onCommit={onCommitFlowEdges}
                    />
                    <FitViewOnWorkflowCanvasKey fitKey={fitKey} edgesReady={flowEdgesReady} />
                    <FitViewOnWorkflowCanvasResize
                        fitKey={fitKey}
                        edgesReady={flowEdgesReady}
                        containerRef={containerRef}
                    />
                    <Background />
                    <Controls />
                </ReactFlow>
            </WorkflowGraphUndoContext.Provider>
        </div>
    );
}

export function WorkflowEditorCanvas(props: WorkflowEditorCanvasProps) {
    return (
        <ReactFlowProvider>
            <WorkflowEditorCanvasInner {...props} />
        </ReactFlowProvider>
    );
}
