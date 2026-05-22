import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { SandboxItemJson } from '../../domain/sandbox/types';
import { SandboxItemInspectorSection } from './SandboxItemInspectorSection';

const foodItem: SandboxItemJson = {
    id: 'food-1',
    type: 'food',
    position: { x: 2, y: 3 },
    energy: 48,
};

const wallItem: SandboxItemJson = {
    id: 'wall-1',
    type: 'wall',
    position: { x: 1, y: 1 },
};

describe('SandboxItemInspectorSection', () => {
    it('shows read-only energy text in read-only mode', () => {
        render(<SandboxItemInspectorSection item={foodItem} readOnly />);

        expect(screen.getByText('Energy')).toBeTruthy();
        expect(screen.getByText('48')).toBeTruthy();
        expect(screen.queryByRole('spinbutton')).toBeNull();
    });

    it('shows editable energy input in builder mode', () => {
        render(<SandboxItemInspectorSection item={foodItem} readOnly={false} onItemChange={vi.fn()} />);

        expect(screen.getByRole('spinbutton', { name: 'Energy' })).toBeTruthy();
    });

    it('calls onItemChange when energy is edited', async () => {
        const user = userEvent.setup();
        const onItemChange = vi.fn();
        render(<SandboxItemInspectorSection item={foodItem} readOnly={false} onItemChange={onItemChange} />);

        const input = screen.getByRole('spinbutton', { name: 'Energy' });
        await user.clear(input);
        await user.type(input, '72');

        expect(onItemChange).toHaveBeenCalledWith('food-1', { energy: 72 });
    });

    it('does not show editable fields for wall items', () => {
        render(<SandboxItemInspectorSection item={wallItem} readOnly={false} onItemChange={vi.fn()} />);

        expect(screen.getByText('wall')).toBeTruthy();
        expect(screen.queryByRole('spinbutton')).toBeNull();
    });
});
