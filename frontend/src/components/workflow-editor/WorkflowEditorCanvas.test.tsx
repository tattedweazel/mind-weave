import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, createEvent } from '@testing-library/react';
import type { Node, Edge } from '@xyflow/react';
import {
    WorkflowEditorCanvas,
    PALETTE_DROP_NODE_OFFSET,
    type WorkflowEditorCanvasProps,
} from './WorkflowEditorCanvas';
import type { WorkflowGraphUndoContextValue } from './workflowGraphUndoContext';

const mockScreenToFlowPosition = vi.fn(({ x, y }: { x: number; y: number }) => ({
    x: x + 50,
    y: y + 25,
}));

vi.mock('@xyflow/react', async importOriginal => {
    const mod = await importOriginal<typeof import('@xyflow/react')>();
    return {
        ...mod,
        useReactFlow: () => ({
            screenToFlowPosition: mockScreenToFlowPosition,
            fitView: vi.fn(),
            viewportInitialized: true,
        }),
        useNodesInitialized: () => true,
    };
});

const noopUndoContext: WorkflowGraphUndoContextValue = {
    recordBeforeGraphMutation: () => {},
    interactionRef: { current: { nodeDrag: false, nodeResize: false } },
};

function renderCanvas(onPaletteDrop: WorkflowEditorCanvasProps['onPaletteDrop']) {
    const props = {
        fitKey: 'wf-test',
        flowEdgesReady: true,
        flowEdgesDeferToken: 0,
        pendingFlowEdgesRef: { current: null },
        onCommitFlowEdges: vi.fn(),
        nodes: [
            {
                id: 'start',
                type: 'start',
                position: { x: 0, y: 0 },
                data: { label: 'Start' },
            },
        ] as Node[],
        edges: [] as Edge[],
        onNodesChange: vi.fn(),
        onEdgesChange: vi.fn(),
        onNodeDragStart: vi.fn(),
        onNodeDragStop: vi.fn(),
        onConnect: vi.fn(),
        onNodeClick: vi.fn(),
        onEdgeClick: vi.fn(),
        onPaneClick: vi.fn(),
        isValidConnection: () => true,
        onPaletteDrop,
        undoContextValue: noopUndoContext,
    };
    return render(
        <div style={{ width: 640, height: 480 }}>
            <WorkflowEditorCanvas {...props} />
        </div>,
    );
}

function makeDataTransfer(payload: Record<string, string>) {
    return {
        dropEffect: 'move',
        effectAllowed: 'move',
        getData: (key: string) => payload[key] ?? '',
        setData: vi.fn(),
    };
}

function dispatchDrop(
    target: Element,
    clientX: number,
    clientY: number,
    dataTransfer: ReturnType<typeof makeDataTransfer>,
) {
    const event = createEvent.drop(target);
    Object.defineProperty(event, 'clientX', { value: clientX, configurable: true });
    Object.defineProperty(event, 'clientY', { value: clientY, configurable: true });
    Object.defineProperty(event, 'dataTransfer', { value: dataTransfer, configurable: true });
    fireEvent(target, event);
}

function dispatchDragOver(
    target: Element,
    clientX: number,
    clientY: number,
    dataTransfer: ReturnType<typeof makeDataTransfer>,
) {
    const event = createEvent.dragOver(target);
    Object.defineProperty(event, 'clientX', { value: clientX, configurable: true });
    Object.defineProperty(event, 'clientY', { value: clientY, configurable: true });
    Object.defineProperty(event, 'dataTransfer', { value: dataTransfer, configurable: true });
    fireEvent(target, event);
}

describe('WorkflowEditorCanvas palette drop', () => {
    beforeEach(() => {
        mockScreenToFlowPosition.mockClear();
    });

    it('calls onPaletteDrop with flow position offset from screenToFlowPosition', () => {
        const onPaletteDrop = vi.fn();
        const { container } = renderCanvas(onPaletteDrop);

        const pane = container.querySelector('.react-flow');
        expect(pane).toBeTruthy();

        const clientX = 120;
        const clientY = 80;
        const dataTransfer = makeDataTransfer({
            nodeType: 'string',
            nodeExtra: JSON.stringify({ label: 'String' }),
        });

        dispatchDragOver(pane!, clientX, clientY, dataTransfer);
        dispatchDrop(pane!, clientX, clientY, dataTransfer);

        expect(mockScreenToFlowPosition).toHaveBeenCalledWith({ x: clientX, y: clientY });
        expect(onPaletteDrop).toHaveBeenCalledTimes(1);
        expect(onPaletteDrop).toHaveBeenCalledWith(
            'string',
            {
                x: clientX + 50 - PALETTE_DROP_NODE_OFFSET.x,
                y: clientY + 25 - PALETTE_DROP_NODE_OFFSET.y,
            },
            { label: 'String' },
        );
    });

    it('does not call onPaletteDrop when nodeType is missing', () => {
        const onPaletteDrop = vi.fn();
        const { container } = renderCanvas(onPaletteDrop);

        const pane = container.querySelector('.react-flow');
        dispatchDrop(pane!, 100, 100, makeDataTransfer({ nodeExtra: '{}' }));

        expect(onPaletteDrop).not.toHaveBeenCalled();
    });
});

describe('PALETTE_DROP_NODE_OFFSET', () => {
    it('matches legacy palette drop centering', () => {
        expect(PALETTE_DROP_NODE_OFFSET).toEqual({ x: 80, y: 40 });
    });
});
