import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { WorkflowGraphIssuesPanel } from './WorkflowGraphIssuesPanel';
import type { WorkflowGraphWiringIssue } from './workflowGraphWiringIssues';

const sampleIssue: WorkflowGraphWiringIssue = {
    edgeId: 'e1',
    kind: 'invalid_source_handle',
    sourceNodeId: 'start',
    targetNodeId: 'pos',
    sourceHandle: 'sandbox_tick',
    targetHandle: 'input',
    message: 'Edge e1: Start has no output `sandbox_tick`.',
    validSourceHandles: ['signal_out', 'output'],
};

describe('WorkflowGraphIssuesPanel', () => {
    it('returns null when there are no issues', () => {
        const { container } = render(
            <WorkflowGraphIssuesPanel
                issues={[]}
                visibleEdgeCount={2}
                hiddenEdgeCount={0}
                onFocusNode={() => {}}
                onDeleteEdge={() => {}}
            />,
        );
        expect(container.firstChild).toBeNull();
    });

    it('renders summary and issue messages when issues exist', () => {
        render(
            <WorkflowGraphIssuesPanel
                issues={[sampleIssue]}
                visibleEdgeCount={1}
                hiddenEdgeCount={1}
                onFocusNode={() => {}}
                onDeleteEdge={() => {}}
            />,
        );
        expect(screen.getByText('Graph issues')).toBeTruthy();
        expect(
            screen.getByText(/1 graph wiring issue — broken connections are hidden from the canvas/i),
        ).toBeTruthy();
        expect(screen.getByText(sampleIssue.message)).toBeTruthy();
    });

    it('calls focus and delete callbacks from action buttons', () => {
        const onFocusNode = vi.fn();
        const onDeleteEdge = vi.fn();
        render(
            <WorkflowGraphIssuesPanel
                issues={[sampleIssue]}
                visibleEdgeCount={0}
                hiddenEdgeCount={1}
                onFocusNode={onFocusNode}
                onDeleteEdge={onDeleteEdge}
            />,
        );
        fireEvent.click(screen.getByRole('button', { name: 'Focus source' }));
        fireEvent.click(screen.getByRole('button', { name: 'Focus target' }));
        fireEvent.click(screen.getByRole('button', { name: 'Delete connection' }));
        expect(onFocusNode).toHaveBeenCalledWith('start');
        expect(onFocusNode).toHaveBeenCalledWith('pos');
        expect(onDeleteEdge).toHaveBeenCalledWith('e1');
    });
});
