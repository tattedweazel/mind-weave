import { useState, useRef } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { ReactFlow, ReactFlowProvider } from '@xyflow/react';
import {
    FitViewOnWorkflowCanvasKey,
    FitViewOnWorkflowCanvasResize,
    WORKFLOW_CANVAS_FIT_VIEW_OPTIONS,
    WORKFLOW_CANVAS_MIN_ZOOM,
} from './FitViewOnWorkflowCanvas';

const mockFitView = vi.fn();
const mockUseNodesInitialized = vi.fn(() => true);

vi.mock('@xyflow/react', async importOriginal => {
    const mod = await importOriginal<typeof import('@xyflow/react')>();
    return {
        ...mod,
        useReactFlow: () => ({
            fitView: mockFitView,
        }),
        useNodesInitialized: () => mockUseNodesInitialized(),
    };
});

function FlowWithFit({ fitKey }: { fitKey: string | null }) {
    const [ready, setReady] = useState(false);
    return (
        <ReactFlowProvider>
            <div style={{ width: 400, height: 300 }}>
                <ReactFlow nodes={[]} edges={[]} onInit={() => setReady(true)}>
                    {ready ? <FitViewOnWorkflowCanvasKey fitKey={fitKey} /> : null}
                </ReactFlow>
            </div>
        </ReactFlowProvider>
    );
}

function FlowWithResize({ fitKey }: { fitKey: string | null }) {
    const [ready, setReady] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    return (
        <ReactFlowProvider>
            <div ref={ref} style={{ width: 400, height: 300 }}>
                <ReactFlow nodes={[]} edges={[]} onInit={() => setReady(true)}>
                    {ready ? <FitViewOnWorkflowCanvasResize fitKey={fitKey} containerRef={ref} /> : null}
                </ReactFlow>
            </div>
        </ReactFlowProvider>
    );
}

describe('WORKFLOW_CANVAS_FIT_VIEW_OPTIONS', () => {
    it('matches the shared fit padding and duration', () => {
        expect(WORKFLOW_CANVAS_FIT_VIEW_OPTIONS).toEqual({ padding: 0.12, duration: 200 });
    });
});

describe('WORKFLOW_CANVAS_MIN_ZOOM', () => {
    it('is below React Flow default minZoom so large graphs can zoom out further', () => {
        expect(WORKFLOW_CANVAS_MIN_ZOOM).toBe(0.05);
        expect(WORKFLOW_CANVAS_MIN_ZOOM).toBeLessThan(0.5);
    });
});

describe('FitViewOnWorkflowCanvasKey', () => {
    beforeEach(() => {
        mockFitView.mockClear();
        mockUseNodesInitialized.mockReturnValue(true);
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

    it('does not call fitView when fitKey is null', async () => {
        render(<FlowWithFit fitKey={null} />);
        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
        });
        expect(mockFitView).not.toHaveBeenCalled();
    });

    it('calls fitView with shared options when fitKey is set', async () => {
        render(<FlowWithFit fitKey="wf-1" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledWith({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
        });
    });

    it('calls fitView again when fitKey changes', async () => {
        const { rerender } = render(<FlowWithFit fitKey="wf-1" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledTimes(1);
        });
        mockFitView.mockClear();
        rerender(<FlowWithFit fitKey="wf-2" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledWith({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
        });
    });

    it('does not call fitView until nodesInitialized is true', async () => {
        mockUseNodesInitialized.mockReturnValue(false);
        const { rerender } = render(<FlowWithFit fitKey="wf-1" />);
        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
        });
        expect(mockFitView).not.toHaveBeenCalled();

        mockUseNodesInitialized.mockReturnValue(true);
        rerender(<FlowWithFit fitKey="wf-1" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledWith({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
        });
    });
});

describe('FitViewOnWorkflowCanvasResize', () => {
    beforeEach(() => {
        mockFitView.mockClear();
        mockUseNodesInitialized.mockReturnValue(true);
        vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
            return window.setTimeout(() => cb(0), 0) as unknown as number;
        });
        vi.stubGlobal('cancelAnimationFrame', (id: number) => {
            clearTimeout(id);
        });
        vi.stubGlobal(
            'ResizeObserver',
            class {
                constructor(private readonly cb: ResizeObserverCallback) {}
                observe() {
                    queueMicrotask(() => {
                        this.cb([], this as unknown as ResizeObserver);
                    });
                }
                disconnect() {}
                unobserve() {}
            },
        );
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('calls fitView when ResizeObserver reports a container resize (debounced)', async () => {
        render(<FlowWithResize fitKey="wf-1" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledWith({ ...WORKFLOW_CANVAS_FIT_VIEW_OPTIONS });
        });
    });

    it('does not call fitView again when useNodesInitialized toggles (resize is container-driven only)', async () => {
        const { rerender } = render(<FlowWithResize fitKey="wf-1" />);
        await waitFor(() => {
            expect(mockFitView).toHaveBeenCalledTimes(1);
        });
        mockFitView.mockClear();
        mockUseNodesInitialized.mockReturnValue(false);
        rerender(<FlowWithResize fitKey="wf-1" />);
        await act(async () => {
            await new Promise(r => setTimeout(r, 0));
        });
        mockUseNodesInitialized.mockReturnValue(true);
        rerender(<FlowWithResize fitKey="wf-1" />);
        await act(async () => {
            await new Promise(r => setTimeout(r, 200));
        });
        expect(mockFitView).not.toHaveBeenCalled();
    });
});
