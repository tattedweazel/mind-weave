import type { ReactElement } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { OutputExplorerV1 } from '../../api/types';
import { ClipboardFeedbackProvider } from '../../contexts/ClipboardFeedbackContext';
import { OutputExplorer } from './OutputExplorer';

function wrap(ui: ReactElement) {
    return render(<ClipboardFeedbackProvider>{ui}</ClipboardFeedbackProvider>);
}

describe('OutputExplorer start_outputs', () => {
    const explorer: OutputExplorerV1 = {
        version: 1,
        kind: 'start_outputs',
        summary: { line: 'Start outputs', detail_lines: ['2 output slot(s)'] },
        items: [
            {
                index: 0,
                row_state: 'ok',
                primary_line: 'a',
                secondary_line: 'string',
                teaser: '"x"',
                badges: [],
                inferred_primitive: 'string',
            },
            {
                index: 1,
                row_state: 'ok',
                primary_line: 'b',
                secondary_line: 'int',
                teaser: '1',
                badges: [],
                inferred_primitive: 'int',
            },
        ],
    };

    const nodeOutput = {
        kind: 'start',
        node_id: 'n1',
        outputs: { a: 'x', b: 1 },
        text: 'x\n\n1',
    };

    it('resolves row payload from outputs and shows dictionary header copy', async () => {
        const user = userEvent.setup();
        wrap(<OutputExplorer explorer={explorer} nodeOutput={nodeOutput} />);

        expect(screen.getByText('Start outputs')).toBeInTheDocument();
        const headerBtn = screen.getByRole('button', {
            name: /copy entire dictionary as json for a dictionary input/i,
        });
        await user.click(headerBtn);
        expect(await screen.findByRole('status')).toHaveTextContent(/copied to clipboard/i);
    });

    it('opens modal with value for a slot', async () => {
        const user = userEvent.setup();
        wrap(<OutputExplorer explorer={explorer} nodeOutput={nodeOutput} />);

        await user.click(screen.getByRole('button', { name: /open details: b/i }));

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'Start output' })).toBeInTheDocument();
        expect(within(dialog).getByText('b')).toBeInTheDocument();
    });
});
