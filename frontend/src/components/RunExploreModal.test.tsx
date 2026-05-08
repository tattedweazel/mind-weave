import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunExploreModal } from './RunExploreModal';
import { ApiClient } from '../api/client';

vi.mock('../contexts/AuthContext', () => ({
    useAuth: () => ({ user: { settings: {} as Record<string, unknown> } }),
}));

vi.mock('../api/client', () => ({
    ApiClient: {
        getMyWorkflowRuns: vi.fn(),
        getWorkflows: vi.fn(),
        getPalettes: vi.fn(),
        getStructures: vi.fn(),
        getDocuments: vi.fn(),
        getWorkflow: vi.fn(),
        getWorkflowRunLogs: vi.fn(),
        deleteWorkflowRun: vi.fn(),
        runWorkflowStream: vi.fn(),
    },
}));

const mockGetMyWorkflowRuns = vi.mocked(ApiClient.getMyWorkflowRuns);
const mockGetWorkflows = vi.mocked(ApiClient.getWorkflows);
const mockGetPalettes = vi.mocked(ApiClient.getPalettes);
const mockGetStructures = vi.mocked(ApiClient.getStructures);
const mockGetDocuments = vi.mocked(ApiClient.getDocuments);
const mockGetWorkflow = vi.mocked(ApiClient.getWorkflow);
const mockGetWorkflowRunLogs = vi.mocked(ApiClient.getWorkflowRunLogs);
const mockDeleteWorkflowRun = vi.mocked(ApiClient.deleteWorkflowRun);

const sampleRun = {
    id: 'run-1',
    workflow_id: 'wf-1',
    workflow_name: 'My Workflow',
    status: 'ok',
    created_at: '2025-01-15T10:00:00Z',
    updated_at: '2025-01-15T10:00:00Z',
};

const sampleRun2 = {
    id: 'run-2',
    workflow_id: 'wf-2',
    workflow_name: 'Other Workflow',
    status: 'ok',
    created_at: '2025-01-15T11:00:00Z',
    updated_at: '2025-01-15T11:00:00Z',
};

function makeWorkflow(id: string, name: string) {
    return {
        id,
        user_id: 'u1',
        name,
        description: null,
        graph: { nodes: [] as unknown[], edges: [] as unknown[] },
        created_at: '',
        updated_at: '',
    };
}

describe('RunExploreModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun]);
        mockGetWorkflows.mockResolvedValue([]);
        mockGetPalettes.mockResolvedValue([]);
        mockGetStructures.mockResolvedValue([]);
        mockGetDocuments.mockResolvedValue([]);
        mockGetWorkflow.mockImplementation(async (wid: string) => {
            if (wid === 'wf-1') return makeWorkflow('wf-1', 'My Workflow') as never;
            if (wid === 'wf-2') return makeWorkflow('wf-2', 'Other Workflow') as never;
            return makeWorkflow(wid, 'Workflow') as never;
        });
        mockGetWorkflowRunLogs.mockResolvedValue([]);
    });

    it('loads and displays runs when open', async () => {
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => {
            expect(mockGetMyWorkflowRuns).toHaveBeenCalled();
        });
        expect(screen.getByText('My Workflow')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /Select My Workflow/ })).toBeInTheDocument();
        expect(screen.getByTitle('Delete run')).toBeInTheDocument();
    });

    it('shows inline Delete and Cancel when trash is clicked, without calling window.confirm', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByTitle('Delete run'));

        expect(confirmSpy).not.toHaveBeenCalled();
        expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
        expect(screen.queryByTitle('Delete run')).not.toBeInTheDocument();

        confirmSpy.mockRestore();
    });

    it('hides Delete/Cancel and shows trash when Cancel is clicked', async () => {
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByTitle('Delete run'));
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Cancel' }));
        expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
        expect(screen.getByTitle('Delete run')).toBeInTheDocument();
        expect(mockDeleteWorkflowRun).not.toHaveBeenCalled();
    });

    it('calls deleteWorkflowRun when Delete is clicked and refreshes list', async () => {
        mockDeleteWorkflowRun.mockResolvedValue(undefined);
        mockGetMyWorkflowRuns.mockResolvedValueOnce([sampleRun]).mockResolvedValueOnce([]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByTitle('Delete run'));
        await user.click(screen.getByRole('button', { name: 'Delete' }));

        await waitFor(() => {
            expect(mockDeleteWorkflowRun).toHaveBeenCalledWith('wf-1', 'run-1');
        });
        await waitFor(() => {
            expect(mockGetMyWorkflowRuns).toHaveBeenCalledTimes(2);
        });
    });

    it('returns null when isOpen is false', () => {
        const { container } = render(<RunExploreModal isOpen={false} onClose={() => {}} />);
        expect(container.firstChild).toBeNull();
    });

    it('ctrl+click adds a second selection and shows bulk bar with count', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        const rowMy = screen.getByText('My Workflow').closest('[role="button"]')!;
        const rowOther = screen.getByText('Other Workflow').closest('[role="button"]')!;
        await user.click(rowMy);
        fireEvent.click(rowOther, { ctrlKey: true });

        expect(await screen.findByText('2 selected')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /delete selected/i })).toBeInTheDocument();
    });

    it('bulk delete confirms then calls deleteWorkflowRun for each selected id', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        mockDeleteWorkflowRun.mockResolvedValue(undefined);
        mockGetMyWorkflowRuns.mockResolvedValueOnce([sampleRun, sampleRun2]).mockResolvedValueOnce([]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        const rowMy = screen.getByText('My Workflow').closest('[role="button"]')!;
        const rowOther = screen.getByText('Other Workflow').closest('[role="button"]')!;
        await user.click(rowMy);
        fireEvent.click(rowOther, { ctrlKey: true });

        await user.click(screen.getByRole('button', { name: /delete selected/i }));
        expect(screen.getByText(/delete 2 runs/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^delete all$/i }));

        await waitFor(() => {
            expect(mockDeleteWorkflowRun).toHaveBeenCalledTimes(2);
        });
        expect(mockDeleteWorkflowRun).toHaveBeenCalledWith('wf-1', 'run-1');
        expect(mockDeleteWorkflowRun).toHaveBeenCalledWith('wf-2', 'run-2');
        expect(mockGetMyWorkflowRuns.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('checkbox toggles selection and bulk bar appears when two are checked', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByRole('checkbox', { name: /Select My Workflow/ }));
        await user.click(screen.getByRole('checkbox', { name: /Select Other Workflow/ }));

        expect(await screen.findByText('2 selected')).toBeInTheDocument();
    });

    it('hides per-row delete while multiple rows are selected', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByRole('checkbox', { name: /Select My Workflow/ }));
        await user.click(screen.getByRole('checkbox', { name: /Select Other Workflow/ }));

        const myRow = screen.getByText('My Workflow').closest('.group')! as HTMLElement;
        expect(within(myRow).queryByTitle('Delete run')).not.toBeInTheDocument();
    });

    it('select all loaded selects every row and shows bulk bar', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByRole('checkbox', { name: /Select all runs in this list/i }));

        expect(screen.getByRole('checkbox', { name: /Select My Workflow/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /Select Other Workflow/ })).toBeChecked();
        expect(await screen.findByText('2 selected')).toBeInTheDocument();
    });

    it('reports partial failures after bulk delete', async () => {
        mockGetMyWorkflowRuns.mockResolvedValue([sampleRun, sampleRun2]);
        mockDeleteWorkflowRun.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('nope'));
        mockGetMyWorkflowRuns
            .mockResolvedValueOnce([sampleRun, sampleRun2])
            .mockResolvedValueOnce([sampleRun2]);
        const user = userEvent.setup();
        render(<RunExploreModal isOpen={true} onClose={() => {}} />);
        await waitFor(() => expect(screen.getByText('My Workflow')).toBeInTheDocument());

        await user.click(screen.getByRole('checkbox', { name: /Select My Workflow/ }));
        await user.click(screen.getByRole('checkbox', { name: /Select Other Workflow/ }));
        await user.click(screen.getByRole('button', { name: /delete selected/i }));
        await user.click(screen.getByRole('button', { name: /^delete all$/i }));

        await waitFor(() => {
            expect(screen.getByText(/Failed to delete 1 run/i)).toBeInTheDocument();
        });
    });
});
