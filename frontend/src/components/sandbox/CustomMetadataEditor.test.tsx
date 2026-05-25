import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomMetadataEditor, rowsToMetadata, metadataToRows } from './CustomMetadataEditor';

describe('CustomMetadataEditor helpers', () => {
    it('round-trips metadata through rows', () => {
        const meta = { energy: 25, ingredients: ['Milk', 'Powder'] };
        const { metadata, error } = rowsToMetadata(metadataToRows(meta));
        expect(error).toBeNull();
        expect(metadata).toEqual(meta);
    });

    it('reports duplicate keys', () => {
        const { error } = rowsToMetadata([
            { id: '1', key: 'a', valueText: '1' },
            { id: '2', key: 'a', valueText: '2' },
        ]);
        expect(error).toContain('Duplicate');
    });
});

describe('CustomMetadataEditor', () => {
    it('calls onChange when a valid row is added', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<CustomMetadataEditor value={{}} onChange={onChange} />);
        await user.click(screen.getByRole('button', { name: /add entry/i }));
        const keyInput = screen.getByPlaceholderText('key');
        await user.type(keyInput, 'energy');
        const valueInput = screen.getByPlaceholderText('JSON value');
        await user.type(valueInput, '25');
        expect(onChange).toHaveBeenCalled();
        const last = onChange.mock.calls.at(-1)?.[0];
        expect(last).toEqual({ energy: 25 });
    });
});
