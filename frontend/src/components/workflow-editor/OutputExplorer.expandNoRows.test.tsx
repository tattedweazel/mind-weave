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

describe('OutputExplorer expandNoRowsDetail', () => {
    const long = `${'a'.repeat(600)}END`;

    it('opens modal from header click and shows full string in preview (not card teaser)', async () => {
        const user = userEvent.setup();
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'string_primitive',
            summary: {
                line: 'user_prompt',
                detail_lines: [`${long.slice(0, 499)}…`],
            },
            items: [],
        };
        const nodeOutput = { kind: 'string', node_id: '', text: long };

        wrap(
            <OutputExplorer
                explorer={explorer}
                nodeOutput={nodeOutput}
                headerClipboardText={long}
                headerClipboardAriaLabel="Copy input value"
                expandNoRowsDetail={{ payload: long, title: 'user_prompt', subtitle: 'string' }}
            />,
        );

        await user.click(screen.getByRole('button', { name: /open full value: user_prompt/i }));

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'user_prompt' })).toBeInTheDocument();
        expect(within(dialog).getByText(/END$/)).toBeInTheDocument();

        await user.click(within(dialog).getByRole('button', { name: 'View raw' }));
        expect(within(dialog).getByText(new RegExp(`${long.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`))).toBeInTheDocument();
    });

    it('opens modal from header click when items are non-empty and expandNoRowsDetail is full nodeOutput', async () => {
        const user = userEvent.setup();
        const nodeOutput = { kind: 'list', node_id: 'n1', data: ['x', 'y'] };
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'list_primitive',
            summary: { line: 'my_list', detail_lines: ['2 item(s)'] },
            items: [
                {
                    index: 0,
                    row_state: 'ok',
                    primary_line: '[0]',
                    secondary_line: 'string',
                    teaser: '"x"',
                    badges: [],
                    inferred_primitive: 'string',
                },
            ],
        };

        wrap(
            <OutputExplorer
                explorer={explorer}
                nodeOutput={nodeOutput}
                expandNoRowsDetail={{
                    payload: nodeOutput,
                    title: 'my_list',
                    subtitle: 'Full output',
                }}
            />,
        );

        await user.click(screen.getByRole('button', { name: /open full value: my_list/i }));

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'my_list' })).toBeInTheDocument();
        await user.click(within(dialog).getByRole('button', { name: 'View raw' }));
        expect(within(dialog).getByText(/"x"/)).toBeInTheDocument();
        expect(within(dialog).getByText(/"y"/)).toBeInTheDocument();
    });
});
