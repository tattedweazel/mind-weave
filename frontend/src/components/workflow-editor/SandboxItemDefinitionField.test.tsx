import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { ItemDefinitionRead } from '../../api/types';
import { SandboxItemDefinitionField } from './SandboxItemDefinitionField';

const defs: ItemDefinitionRead[] = [
    {
        id: 'def-key',
        name: 'Key',
        label: 'Key',
        shape: 'square',
        pickable: true,
        is_system: false,
    },
    {
        id: 'def-reward',
        name: 'Reward',
        label: 'Reward',
        shape: 'circle',
        pickable: true,
        is_system: false,
    },
];

describe('SandboxItemDefinitionField', () => {
    it('selects a definition from the dropdown', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(
            <SandboxItemDefinitionField
                id="spawn-def"
                value=""
                onChange={onChange}
                itemDefinitions={defs}
            />,
        );
        await user.selectOptions(screen.getByLabelText('Item definition'), 'def-key');
        expect(onChange).toHaveBeenCalledWith('def-key');
    });

    it('supports manual UUID override', async () => {
        const user = userEvent.setup();
        function Harness() {
            const [value, setValue] = React.useState('');
            return (
                <SandboxItemDefinitionField
                    id="spawn-def"
                    value={value}
                    onChange={setValue}
                    itemDefinitions={defs}
                />
            );
        }
        render(<Harness />);
        const input = screen.getByLabelText('Definition ID (manual override)');
        await user.clear(input);
        await user.type(input, 'custom-uuid');
        expect(input).toHaveValue('custom-uuid');
    });

    it('shows manual value when id is not in the dropdown list', () => {
        render(
            <SandboxItemDefinitionField
                id="spawn-def"
                value="orphan-id"
                onChange={() => {}}
                itemDefinitions={defs}
            />,
        );
        expect(screen.getByLabelText('Definition ID (manual override)')).toHaveValue('orphan-id');
        expect(screen.getByLabelText('Item definition')).toHaveValue('');
    });
});
