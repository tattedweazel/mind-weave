import { useRef } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { ReactFlow, ReactFlowProvider, type Edge } from '@xyflow/react';
import { FlowEdgesDeferredCommitGate } from './FlowEdgesDeferredCommitGate';

const mockUseNodesInitialized = vi.fn(() => false);

vi.mock('@xyflow/react', async importOriginal => {
    const mod = await importOriginal<typeof import('@xyflow/react')>();
    return {
        ...mod,
        useNodesInitialized: () => mockUseNodesInitialized(),
    };
});

const pendingEdges: Edge[] = [
    {
        id: 'e1',
        source: 'start',
        target: 'nearby',
        sourceHandle: 'sandbox_tick',
        targetHandle: 'input',
    },
];

function GateHarness({
    deferToken,
    onCommit,
}: {
    deferToken: number;
    onCommit: (edges: Edge[]) => void;
}) {
    const pendingEdgesRef = useRef<Edge[] | null>(pendingEdges);
    return (
        <ReactFlowProvider>
            <ReactFlow nodes={[]} edges={[]}>
                <FlowEdgesDeferredCommitGate
                    deferToken={deferToken}
                    pendingEdgesRef={pendingEdgesRef}
                    onCommit={onCommit}
                />
            </ReactFlow>
        </ReactFlowProvider>
    );
}

describe('FlowEdgesDeferredCommitGate', () => {
    beforeEach(() => {
        mockUseNodesInitialized.mockReturnValue(false);
        vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
            return window.setTimeout(() => cb(0), 0) as unknown as number;
        });
        vi.stubGlobal('cancelAnimationFrame', (id: number) => {
            clearTimeout(id);
        });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('does not commit until nodes are initialized', async () => {
        const onCommit = vi.fn();
        render(<GateHarness deferToken={1} onCommit={onCommit} />);

        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
        });

        expect(onCommit).not.toHaveBeenCalled();
    });

    it('commits pending edges after nodes initialize and double rAF', async () => {
        mockUseNodesInitialized.mockReturnValue(true);
        const onCommit = vi.fn();
        render(<GateHarness deferToken={1} onCommit={onCommit} />);

        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
            await new Promise(r => setTimeout(r, 0));
        });

        expect(onCommit).toHaveBeenCalledTimes(1);
        expect(onCommit).toHaveBeenCalledWith(pendingEdges);
    });

    it('re-runs when deferToken changes', async () => {
        mockUseNodesInitialized.mockReturnValue(true);
        const onCommit = vi.fn();
        const { rerender } = render(<GateHarness deferToken={1} onCommit={onCommit} />);

        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
            await new Promise(r => setTimeout(r, 0));
        });
        expect(onCommit).toHaveBeenCalledTimes(1);

        rerender(<GateHarness deferToken={2} onCommit={onCommit} />);
        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
            await new Promise(r => setTimeout(r, 0));
        });
        expect(onCommit).toHaveBeenCalledTimes(2);
    });
});
