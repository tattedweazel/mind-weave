import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SandboxSensoryProbePanel } from './SandboxSensoryProbePanel';

describe('SandboxSensoryProbePanel', () => {
    it('renders position coordinates', () => {
        render(<SandboxSensoryProbePanel kind="position" value={{ x: 4, y: 1 }} />);
        expect(screen.getByText('4')).toBeInTheDocument();
        expect(screen.getByText('1')).toBeInTheDocument();
        expect(screen.getByText('Position')).toBeInTheDocument();
    });

    it('renders facing compass with active direction', () => {
        render(<SandboxSensoryProbePanel kind="facing" value="E" />);
        const east = screen.getByLabelText('Facing E');
        expect(east).toBeInTheDocument();
        expect(east.querySelector('.bg-indigo-500')).toHaveTextContent('E');
    });

    it('renders food inventory with label and energy badge', () => {
        render(
            <SandboxSensoryProbePanel
                kind="inventory"
                value={[{ type: 'food', energy: 48 }]}
            />,
        );
        expect(screen.getByText('Food')).toBeInTheDocument();
        expect(screen.getByText('Energy 48')).toBeInTheDocument();
        expect(screen.queryByText(/Food \(energy 48\)/)).not.toBeInTheDocument();
    });

    it('renders ball inventory with colored label and swatch', () => {
        render(
            <SandboxSensoryProbePanel
                kind="inventory"
                value={[{ type: 'ball', color: '#EAF73B' }]}
            />,
        );
        expect(screen.getByText('Ball')).toBeInTheDocument();
        expect(screen.queryByText('#EAF73B')).not.toBeInTheDocument();
        expect(screen.getByLabelText('Ball color #EAF73B')).toBeInTheDocument();
    });

    it('uses default ball color when color is missing', () => {
        render(
            <SandboxSensoryProbePanel
                kind="inventory"
                value={[{ type: 'ball' }]}
            />,
        );
        expect(screen.getByLabelText('Ball color #3B82F6')).toBeInTheDocument();
    });

    it('renders empty inventory', () => {
        render(<SandboxSensoryProbePanel kind="inventory" value={[]} />);
        expect(screen.getByText('Empty')).toBeInTheDocument();
    });

    it('renders nearby kind badges in ring layout', () => {
        render(
            <SandboxSensoryProbePanel
                kind="nearby"
                value={[{ x: 3, y: 1, kind: 'wall', region_label: null }]}
                facing="N"
                origin={{ x: 3, y: 2 }}
            />,
        );
        expect(screen.getByText('Wall')).toBeInTheDocument();
        expect(screen.getByText('(3, 1)')).toBeInTheDocument();
        expect(screen.getByText('You')).toBeInTheDocument();
    });

    it('renders region chip for labeled region-only cell', () => {
        render(
            <SandboxSensoryProbePanel
                kind="nearby"
                value={[{ x: 3, y: 1, kind: 'empty', region_label: 'target' }]}
                facing="N"
                origin={{ x: 3, y: 2 }}
            />,
        );
        expect(screen.getByText('Empty')).toBeInTheDocument();
        expect(screen.getByText('target')).toBeInTheDocument();
    });

    it('renders generic Region chip when region_label is empty string', () => {
        render(
            <SandboxSensoryProbePanel
                kind="nearby"
                value={[{ x: 3, y: 1, kind: 'empty', region_label: '' }]}
                facing="N"
                origin={{ x: 3, y: 2 }}
            />,
        );
        expect(screen.getByText('Region')).toBeInTheDocument();
    });

    it('renders food and region chips when stacked', () => {
        render(
            <SandboxSensoryProbePanel
                kind="nearby"
                value={[{ x: 3, y: 1, kind: 'food', region_label: 'target' }]}
                facing="N"
                origin={{ x: 3, y: 2 }}
            />,
        );
        expect(screen.getByText('Food')).toBeInTheDocument();
        expect(screen.getByText('target')).toBeInTheDocument();
    });

    it('selectable inventory rows invoke onInventorySelect', async () => {
        const user = userEvent.setup();
        const onSelect = vi.fn();
        render(
            <SandboxSensoryProbePanel
                kind="inventory"
                value={[
                    { type: 'food', energy: 10 },
                    { type: 'ball', color: '#AABBCC' },
                ]}
                inventorySelectable
                selectedInventoryIndex={null}
                onInventorySelect={onSelect}
            />,
        );
        expect(screen.getByText('Choose an item to place')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /food/i }));
        expect(onSelect).toHaveBeenCalledWith(0);
    });

    it('keeps raw JSON collapsed by default and expands on click', async () => {
        const user = userEvent.setup();
        render(<SandboxSensoryProbePanel kind="position" value={{ x: 2, y: 2 }} />);
        expect(screen.queryByText(/"x": 2/)).not.toBeVisible();
        await user.click(screen.getByText('Raw JSON'));
        expect(screen.getByText(/"x": 2/)).toBeVisible();
    });
});
