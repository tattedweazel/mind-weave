import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { WorkflowDefinition } from '../../api/types';
import { WorkflowPaletteStepSections, paletteStepIcon } from './WorkflowPaletteStepSections';
import { DEFAULT_PALETTE_COLORS } from '../../domain/paletteDefaults';

const noop = () => {};

const baseProps = {
    paletteColors: DEFAULT_PALETTE_COLORS,
    flowOpen: true,
    onFlowOpenChange: noop,
    primitivesOpen: true,
    onPrimitivesOpenChange: noop,
    skillsOpen: true,
    onSkillsOpenChange: noop,
    utilitiesOpen: true,
    onUtilitiesOpenChange: noop,
    sandboxUtilitiesOpen: true,
    onSandboxUtilitiesOpenChange: noop,
    controlsOpen: true,
    onControlsOpenChange: noop,
    annotationsOpen: true,
    onAnnotationsOpenChange: noop,
};

describe('WorkflowPaletteStepSections', () => {
    it('renders a primitive label in edit mode', () => {
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        expect(screen.getByText('String')).toBeInTheDocument();
    });

    it('renders Sandbox Utilities section with a sandbox tile', () => {
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        expect(screen.getByText('Sandbox Utilities')).toBeInTheDocument();
        expect(screen.getByText('Tick Input')).toBeInTheDocument();
        expect(screen.getByText('Move Forward')).toBeInTheDocument();
        expect(screen.getByText('Get Cell Items')).toBeInTheDocument();
        expect(screen.getByText('Remove Item')).toBeInTheDocument();
        expect(screen.getByText('Spawn Item')).toBeInTheDocument();
        expect(screen.queryByText('Fixture Utilities')).not.toBeInTheDocument();
    });

    it('renders Flow section with Stop tile', () => {
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        expect(screen.getByText('Flow')).toBeInTheDocument();
        expect(screen.getByText('Stop')).toBeInTheDocument();
    });

    it('renders Annotation section with Note and Region tiles', () => {
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        expect(screen.getByText('Annotation')).toBeInTheDocument();
        expect(screen.getByText('Note')).toBeInTheDocument();
        expect(screen.getByText('Region')).toBeInTheDocument();
    });

    it('filters primitives by prefix (case-insensitive)', async () => {
        const user = userEvent.setup();
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        const filter = screen.getByLabelText('Filter Primitives');
        await user.type(filter, 'st');
        expect(screen.getByText('String')).toBeInTheDocument();
        expect(screen.getByText('Structure')).toBeInTheDocument();
        expect(screen.queryByText('List')).not.toBeInTheDocument();
    });

    it('shows No matches when filter excludes all items', async () => {
        const user = userEvent.setup();
        render(<WorkflowPaletteStepSections {...baseProps} mode="edit" />);
        const filter = screen.getByLabelText('Filter Primitives');
        await user.type(filter, 'zzz');
        expect(screen.getByText('No matches')).toBeInTheDocument();
    });

    it('reference mode renders tiles without draggable', () => {
        render(<WorkflowPaletteStepSections {...baseProps} mode="reference" />);
        const stringTile = screen.getByLabelText('String (reference only)');
        expect(stringTile).toBeInTheDocument();
        expect(stringTile).toHaveAttribute('draggable', 'false');
    });

    it('Custom Skills row disables drag for the active workflow', () => {
        const wf: WorkflowDefinition = {
            id: 'wf-active',
            user_id: null,
            name: 'Active Skill',
            description: null,
            palette_id: null,
            project_id: 'p1',
            expose_as_custom_skill: true,
            graph: { nodes: [], edges: [], schema_version: 1 },
        };
        render(
            <WorkflowPaletteStepSections
                {...baseProps}
                mode="edit"
                customSkillWorkflows={[wf]}
                customSkillsOpen
                onCustomSkillsOpenChange={vi.fn()}
                activeWorkflowId="wf-active"
                onCustomSkillWorkflowOpen={vi.fn()}
                moveProjectPickerFor={null}
                onToggleMoveProjectPicker={vi.fn()}
                workflowProjects={[
                    {
                        id: 'p1',
                        name: 'Shared',
                        sort_order: 0,
                        sandbox_enabled: false,
                        user_id: 'u1',
                        workflow_count: 0,
                        created_at: '',
                        updated_at: '',
                    },
                ]}
                sharedProjectId="p1"
                onMoveWorkflowToProject={vi.fn().mockResolvedValue(true)}
                onAfterMoveWorkflowFromPalette={vi.fn()}
            />,
        );
        const nameBtn = screen.getByText('Active Skill').closest('[draggable]');
        expect(nameBtn).toHaveAttribute('draggable', 'false');
    });

    it('renders icons for sandbox navigation utility palette types', () => {
        const sandboxTypes = [
            'sandboxTickPrimitive',
            'sandboxGetPosition',
            'sandboxGetFacing',
            'sandboxGetNearby',
            'sandboxMoveForward',
            'sandboxTurnLeft',
            'sandboxTurnRight',
            'sandboxIdle',
        ] as const;
        for (const type of sandboxTypes) {
            const icon = paletteStepIcon(type);
            expect(icon).not.toBeNull();
            const { container } = render(<>{icon}</>);
            expect(container.querySelector('svg')).not.toBeNull();
        }
    });

    it('renders icons for sandbox inventory and user-action utility palette types', () => {
        const sandboxTypes = [
            'sandboxPickUpItem',
            'sandboxPlaceItem',
            'sandboxGetInventory',
            'sandboxPromptUserAction',
        ] as const;
        for (const type of sandboxTypes) {
            const icon = paletteStepIcon(type);
            expect(icon).not.toBeNull();
            const { container } = render(<>{icon}</>);
            expect(container.querySelector('svg')).not.toBeNull();
        }
    });
});
