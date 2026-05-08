import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { WorkflowDefinition } from '../../api/types';
import { ClipboardFeedbackProvider } from '../../contexts/ClipboardFeedbackContext';
import { WorkflowExplorerWorkflowMetadata } from './WorkflowExplorerWorkflowMetadata';

const writeTextToSystemClipboard = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock('../../systemClipboard', () => ({
    writeTextToSystemClipboard: (text: string) => writeTextToSystemClipboard(text),
}));

function wrap(ui: ReactElement) {
    return render(<ClipboardFeedbackProvider>{ui}</ClipboardFeedbackProvider>);
}

describe('WorkflowExplorerWorkflowMetadata', () => {
    beforeEach(() => {
        writeTextToSystemClipboard.mockClear();
        writeTextToSystemClipboard.mockResolvedValue(undefined);
    });

    afterEach(() => {
        writeTextToSystemClipboard.mockReset();
        writeTextToSystemClipboard.mockResolvedValue(undefined);
    });

    const base: WorkflowDefinition = {
        id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        user_id: '11111111-2222-3333-4444-555555555555',
        name: 'Sort Workflow Test',
        description: 'Example',
        palette_id: null,
        graph: { nodes: [], edges: [], schema_version: 1 },
    };

    it('renders workflow name and definition id', () => {
        wrap(
            <WorkflowExplorerWorkflowMetadata workflow={base} nodeCount={3} edgeCount={2} lastRunId={null} />,
        );
        expect(screen.getByText('Sort Workflow Test')).toBeInTheDocument();
        expect(screen.getByText(base.id)).toBeInTheDocument();
        expect(screen.getByText((_, el) => el?.textContent === 'Graph: 3 nodes, 2 edges')).toBeInTheDocument();
    });

    it('shows last run id when provided', () => {
        const rid = 'run-uuid-here';
        wrap(<WorkflowExplorerWorkflowMetadata workflow={base} nodeCount={0} edgeCount={0} lastRunId={rid} />);
        expect(screen.getByText(rid)).toBeInTheDocument();
    });

    it('copy debug JSON includes workflow id and name', async () => {
        const user = userEvent.setup();
        wrap(
            <WorkflowExplorerWorkflowMetadata workflow={base} nodeCount={0} edgeCount={0} lastRunId="run-1" />,
        );
        await user.click(screen.getByRole('button', { name: /Copy debug JSON/i }));
        await waitFor(() => {
            expect(writeTextToSystemClipboard).toHaveBeenCalled();
        });
        const arg = writeTextToSystemClipboard.mock.calls[0][0] as string;
        expect(arg).toContain('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
        expect(arg).toContain('Sort Workflow Test');
        expect(arg).toContain('last_run_id');
        expect(await screen.findByRole('status')).toHaveTextContent(/Copied to clipboard/i);
    });

    it('shows Expose as Custom Skill and calls handler when not exposed', async () => {
        const user = userEvent.setup();
        const onExpose = vi.fn();
        wrap(
            <WorkflowExplorerWorkflowMetadata
                workflow={base}
                nodeCount={1}
                edgeCount={0}
                lastRunId={null}
                onExposeAsCustomSkillChange={onExpose}
            />,
        );
        await user.click(screen.getByRole('button', { name: /Expose as Custom Skill/i }));
        expect(onExpose).toHaveBeenCalledWith(true);
    });

    it('shows Remove from Custom Skills when exposed', async () => {
        const user = userEvent.setup();
        const onExpose = vi.fn();
        wrap(
            <WorkflowExplorerWorkflowMetadata
                workflow={{ ...base, expose_as_custom_skill: true }}
                nodeCount={1}
                edgeCount={0}
                lastRunId={null}
                onExposeAsCustomSkillChange={onExpose}
            />,
        );
        await user.click(screen.getByRole('button', { name: /Remove from Custom Skills/i }));
        expect(onExpose).toHaveBeenCalledWith(false);
    });
});
