import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { OutputExplorerItem } from '../../api/types';
import { OutputExplorerDetailModal } from './OutputExplorerDetailModal';

const baseItem: OutputExplorerItem = {
    index: 0,
    row_state: 'ok',
    primary_line: 'myKey',
    secondary_line: 'object',
    teaser: '',
    badges: [],
};

describe('OutputExplorerDetailModal', () => {
    it('uses pretty-printed preview for dictionary row and tree controls only on View raw', async () => {
        const user = userEvent.setup();
        render(
            <OutputExplorerDetailModal
                open
                onClose={() => {}}
                kind="dictionary_primitive"
                item={baseItem}
                payload={{ a: 1 }}
            />,
        );

        expect(screen.getByText(/pretty-printed JSON/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /expand/i })).not.toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /view raw/i }));
        expect(screen.getByRole('button', { name: /expand/i })).toBeInTheDocument();
        expect(screen.queryByText(/pretty-printed JSON/i)).not.toBeInTheDocument();
    });

    it('keeps Gmail record preview as structured layout, not primitive JSON block', () => {
        const item: OutputExplorerItem = {
            ...baseItem,
            primary_line: 'Re: hello',
            secondary_line: 'from x',
        };
        render(
            <OutputExplorerDetailModal
                open
                onClose={() => {}}
                kind="gmail_list_messages"
                item={item}
                payload={{
                    subject: 'Re: hello',
                    from: 'a@b.com',
                    body_text: 'Hi',
                }}
            />,
        );

        expect(screen.getByRole('heading', { name: /re: hello/i })).toBeInTheDocument();
        expect(screen.queryByText(/pretty-printed JSON/i)).not.toBeInTheDocument();
    });

    it('uses titleOverride and subtitleOverride for the dialog header', () => {
        render(
            <OutputExplorerDetailModal
                open
                onClose={() => {}}
                kind="generic"
                item={baseItem}
                payload={{ x: 1 }}
                titleOverride="resolved_field"
                subtitleOverride="object (1 key)"
            />,
        );

        expect(screen.getByRole('heading', { name: 'resolved_field' })).toBeInTheDocument();
        expect(screen.getByText('object (1 key)')).toBeInTheDocument();
    });
});
