import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from './AuthContext';
import { AuthClient } from '../api/authClient';

vi.mock('../api/authClient', () => ({
    AuthClient: {
        getMe: vi.fn(),
        login: vi.fn(),
        logout: vi.fn(),
        completeGoogleSession: vi.fn(),
    },
}));

function Probe() {
    const { isLoading, checkAuth } = useAuth();
    return (
        <div>
            <span data-testid="loading">{isLoading ? 'loading' : 'idle'}</span>
            <button type="button" onClick={() => void checkAuth({ silent: true })}>
                silent-refresh
            </button>
            <button type="button" onClick={() => void checkAuth()}>
                full-refresh
            </button>
        </div>
    );
}

const mockUser = {
    id: '1',
    username: 'tester',
    is_admin: false,
    settings: {},
    api_keys: {},
};

describe('AuthContext', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(AuthClient.getMe).mockResolvedValue(mockUser);
    });

    it('checkAuth with silent keeps isLoading false after initial load', async () => {
        const user = userEvent.setup();
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>
        );

        await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('idle'));
        expect(AuthClient.getMe).toHaveBeenCalledTimes(1);

        await user.click(screen.getByRole('button', { name: /silent-refresh/i }));
        expect(screen.getByTestId('loading')).toHaveTextContent('idle');
        await waitFor(() => expect(AuthClient.getMe).toHaveBeenCalledTimes(2));
        expect(screen.getByTestId('loading')).toHaveTextContent('idle');
    });

    it('checkAuth without silent toggles isLoading during refresh', async () => {
        const user = userEvent.setup();
        let resolveGetMe: (u: typeof mockUser) => void = () => {};
        const getMePromise = new Promise<typeof mockUser>(resolve => {
            resolveGetMe = resolve;
        });
        vi.mocked(AuthClient.getMe).mockImplementationOnce(() =>
            Promise.resolve(mockUser),
        );
        vi.mocked(AuthClient.getMe).mockImplementationOnce(() => getMePromise as Promise<typeof mockUser>);

        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>
        );

        await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('idle'));

        await user.click(screen.getByRole('button', { name: /full-refresh/i }));
        await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('loading'));

        resolveGetMe(mockUser);
        await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('idle'));
    });
});
