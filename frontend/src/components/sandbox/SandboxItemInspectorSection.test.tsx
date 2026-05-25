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

const definitionBackedItem: SandboxItemJson = {
    id: 'key-1',
    definition_id: 'item-def-1',
    definition_kind: 'item',
    role: 'pickable',
    position: { x: 4, y: 5 },
    energy: 12,
};

const definitionContext = {
    itemDefinitions: [
        {
            id: 'item-def-1',
            name: 'golden_key',
            label: 'Golden Key',
            custom_metadata: { energy: 10 },
            default_color: '#FFD700',
            shape: 'square' as const,
            pickable: true,
            is_system: false,
        },
    ],
};

describe('SandboxItemInspectorSection', () => {
    it('shows read-only energy text in read-only mode', () => {
        render(<SandboxItemInspectorSection item={foodItem} readOnly />);

        expect(screen.getByRole('heading', { name: 'Food' })).toBeTruthy();
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

        expect(screen.getByRole('heading', { name: 'Terrain' })).toBeTruthy();
        expect(screen.queryByRole('spinbutton')).toBeNull();
    });

    it('shows definition-backed item with label instead of food type', () => {
        render(
            <SandboxItemInspectorSection
                item={definitionBackedItem}
                readOnly
                definitionContext={definitionContext}
            />,
        );

        expect(screen.getByText('Item · Golden Key')).toBeTruthy();
        expect(screen.getByText('Golden Key')).toBeTruthy();
        expect(screen.getByText('golden_key')).toBeTruthy();
        expect(screen.getByText('Pickable')).toBeTruthy();
        expect(screen.getByText('square')).toBeTruthy();
        expect(screen.queryByText('food')).toBeNull();
    });

    it('allows editing energy for definition-backed pickables in builder mode', () => {
        render(
            <SandboxItemInspectorSection
                item={definitionBackedItem}
                readOnly={false}
                definitionContext={definitionContext}
                onItemChange={vi.fn()}
            />,
        );

        expect(screen.getByRole('spinbutton', { name: 'Energy' })).toBeTruthy();
    });
});
