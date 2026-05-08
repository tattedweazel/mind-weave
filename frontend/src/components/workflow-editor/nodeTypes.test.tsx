import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NODE_MIN_HEIGHT, NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX } from './constants';
import { StartNodeComp, nodeTypes } from './nodeTypes';

vi.mock('@xyflow/react', () => ({
    Handle: ({ id }: { id?: string }) => <div data-testid="flow-handle" data-handle-id={id ?? ''} />,
    Position: { Left: 'left', Right: 'right' },
    useNodeId: () => 'test-node',
    useUpdateNodeInternals: () => vi.fn(),
}));

describe('StartNodeComp', () => {
    it('renders signal_out and one source handle per required_inputs slot with distinct ids', () => {
        render(
            <StartNodeComp
                data={{
                    label: 'Start',
                    required_inputs: [
                        { key: 'user_input', type: 'string', value: null },
                        { key: 'input_2', type: 'string', value: null },
                        { key: 'input_3', type: 'string', value: null },
                    ],
                }}
            />,
        );
        const handles = screen.getAllByTestId('flow-handle');
        const ids = handles.map(h => h.getAttribute('data-handle-id'));
        expect(ids).toEqual(['signal_out', 'user_input', 'input_2', 'input_3']);
    });
});

describe('StyledNodeBase canvas layout (via transcribeFile)', () => {
    const TranscribeFileNode = nodeTypes.transcribeFile;

    it('adds top reserve padding and taller min-height when session output override is active', () => {
        const { container, rerender } = render(
            <TranscribeFileNode data={{ label: 'Transcribe', outputOverrideActive: false }} />,
        );
        const rootInactive = container.firstElementChild as HTMLElement;
        expect(rootInactive.style.paddingTop).toBe('');
        expect(rootInactive.style.minHeight).toBe(`${NODE_MIN_HEIGHT.double}px`);

        rerender(<TranscribeFileNode data={{ label: 'Transcribe', outputOverrideActive: true }} />);
        screen.getByText('Overridden');
        const rootActive = container.firstElementChild as HTMLElement;
        expect(rootActive.style.paddingTop).toBe(`${NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX}px`);
        expect(rootActive.style.minHeight).toBe(`${NODE_MIN_HEIGHT.double + NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX}px`);
    });
});
