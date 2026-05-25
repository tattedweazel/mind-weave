import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { BroadcastMessageModal } from './BroadcastMessageModal';

describe('BroadcastMessageModal', () => {
    it('renders segments and calls onContinue', () => {
        const onContinue = vi.fn();
        render(
            <BroadcastMessageModal
                segments={[
                    { node_id: 'n1', body: 'Hello', severity: 'info', title: 'Debug' },
                ]}
                onContinue={onContinue}
            />,
        );
        expect(screen.getByRole('dialog')).toBeTruthy();
        expect(screen.getByText('Hello')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
        expect(onContinue).toHaveBeenCalledTimes(1);
    });

    it('renders source tag above title and body', () => {
        render(
            <BroadcastMessageModal
                segments={[
                    {
                        node_id: 'n1',
                        body: 'Hello',
                        severity: 'info',
                        title: 'Debug label',
                        source: 'Fixture: fixture-bc',
                    },
                ]}
                onContinue={() => {}}
            />,
        );
        const section = screen.getByRole('dialog').querySelector('section');
        expect(section).toBeTruthy();
        const text = section?.textContent ?? '';
        expect(text.indexOf('Fixture: fixture-bc')).toBeLessThan(text.indexOf('Debug label'));
        expect(text.indexOf('Debug label')).toBeLessThan(text.indexOf('Hello'));
    });
});
