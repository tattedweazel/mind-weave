import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiClient } from '../api/client';
import type { Persona, PersonaListItem } from '../api/types';
import { PersonaManager } from './PersonaManager';

vi.mock('../api/client', () => ({
    ApiClient: {
        getPersonas: vi.fn(),
        getPersona: vi.fn(),
        getModels: vi.fn(),
        createPersona: vi.fn(),
        updatePersona: vi.fn(),
        deletePersona: vi.fn(),
    },
}));

function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>(r => {
        resolve = r;
    });
    return { promise, resolve };
}

const models = { local: [] as string[], external: [] as string[] };

const baseListItem = (overrides: Partial<PersonaListItem>): PersonaListItem => ({
    id: 'p-default',
    user_id: 'u1',
    name: 'Default',
    type: 'custom',
    description: 'Desc',
    default_model: null,
    is_default: false,
    creativity: 0.2,
    suppress_lm_thinking: false,
    created_at: '2020-01-01T00:00:00Z',
    updated_at: '2020-01-01T00:00:00Z',
    ...overrides,
});

describe('PersonaManager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.getModels).mockResolvedValue(models);
    });

    it('fetches persona detail on select and fills system prompt from GET /personas/{id}', async () => {
        const user = userEvent.setup();
        const listItem = baseListItem({ id: 'p1', name: 'Reviewer', description: 'Does reviews' });
        const full: Persona = {
            ...listItem,
            system_prompt: 'You are a careful reviewer.',
        };
        vi.mocked(ApiClient.getPersonas).mockResolvedValue([listItem]);
        vi.mocked(ApiClient.getPersona).mockResolvedValue(full);

        render(<PersonaManager isOpen onClose={() => {}} />);

        await waitFor(() => expect(ApiClient.getPersonas).toHaveBeenCalled());
        await user.click(screen.getByText('Reviewer'));

        await waitFor(() => expect(ApiClient.getPersona).toHaveBeenCalledWith('p1'));
        await waitFor(() =>
            expect(screen.getByPlaceholderText('You are a …')).toHaveValue('You are a careful reviewer.'),
        );
    });

    it('shows loading state while persona detail is loading', async () => {
        const user = userEvent.setup();
        const listItem = baseListItem({ id: 'p1', name: 'Reviewer' });
        const full: Persona = { ...listItem, system_prompt: 'Loaded prompt.' };
        vi.mocked(ApiClient.getPersonas).mockResolvedValue([listItem]);
        const d = deferred<Persona>();
        vi.mocked(ApiClient.getPersona).mockReturnValue(d.promise);

        render(<PersonaManager isOpen onClose={() => {}} />);

        await waitFor(() => expect(ApiClient.getPersonas).toHaveBeenCalled());
        await user.click(screen.getByText('Reviewer'));

        expect(await screen.findByText('Loading persona…')).toBeInTheDocument();

        d.resolve(full);

        await waitFor(() => expect(screen.queryByText('Loading persona…')).not.toBeInTheDocument());
        expect(screen.getByPlaceholderText('You are a …')).toHaveValue('Loaded prompt.');
    });

    it('ignores stale getPersona result when selection changes before resolve', async () => {
        const user = userEvent.setup();
        const first = baseListItem({ id: 'p1', name: 'First' });
        const second = baseListItem({ id: 'p2', name: 'Second' });
        vi.mocked(ApiClient.getPersonas).mockResolvedValue([first, second]);

        const d1 = deferred<Persona>();
        const d2 = deferred<Persona>();
        vi.mocked(ApiClient.getPersona).mockImplementation((id: string) => {
            if (id === 'p1') return d1.promise;
            if (id === 'p2') return d2.promise;
            return Promise.reject(new Error(`unexpected id ${id}`));
        });

        render(<PersonaManager isOpen onClose={() => {}} />);

        await waitFor(() => expect(ApiClient.getPersonas).toHaveBeenCalled());
        await user.click(screen.getByText('First'));
        await user.click(screen.getByText('Second'));

        d1.resolve({ ...first, system_prompt: 'Stale from first' });
        await waitFor(() =>
            expect(screen.getByPlaceholderText('You are a …')).not.toHaveValue('Stale from first'),
        );

        d2.resolve({ ...second, system_prompt: 'Correct for second' });
        await waitFor(() =>
            expect(screen.getByPlaceholderText('You are a …')).toHaveValue('Correct for second'),
        );
    });
});
