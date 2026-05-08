import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnnotationStackOrderControls } from './AnnotationStackOrderControls';

describe('AnnotationStackOrderControls', () => {
    it('calls onMoveBack and onMoveForward', async () => {
        const user = userEvent.setup();
        const onMoveBack = vi.fn();
        const onMoveForward = vi.fn();
        render(
            <AnnotationStackOrderControls kind="note" onMoveBack={onMoveBack} onMoveForward={onMoveForward} />,
        );
        await user.click(screen.getByRole('button', { name: 'Move back' }));
        await user.click(screen.getByRole('button', { name: 'Move forward' }));
        expect(onMoveBack).toHaveBeenCalledTimes(1);
        expect(onMoveForward).toHaveBeenCalledTimes(1);
    });

    it('shows region-specific helper text', () => {
        render(
            <AnnotationStackOrderControls kind="region" onMoveBack={() => {}} onMoveForward={() => {}} />,
        );
        expect(screen.getByText(/Regions stay behind workflow notes/)).toBeInTheDocument();
    });
});
