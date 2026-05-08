import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthClient } from './api/authClient';

vi.mock('./api/authClient', () => ({
    AuthClient: {
        getMe: vi.fn(),
        login: vi.fn(),
        getGoogleLoginUrl: vi.fn(),
        getUsers: vi.fn().mockResolvedValue([]),
    },
}));

const mockGetMe = vi.mocked(AuthClient.getMe);

const renderApp = () =>
    render(
        <AuthProvider>
            <ThemeProvider>
                <App />
            </ThemeProvider>
        </AuthProvider>
    );

describe('App', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 'admin',
            is_admin: true,
            settings: {},
            api_keys: {},
        });
    });

    it('shows Workspace first; Build with Workflows and Replays; Configure with Personas, Structures, and Palettes', async () => {
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        expect(screen.getByTitle('Workflows')).toBeInTheDocument();
        expect(screen.getByTitle('Replays')).toBeInTheDocument();
        expect(screen.getByTitle('Personas')).toBeInTheDocument();
        expect(screen.getByTitle('Structures')).toBeInTheDocument();
        expect(screen.getByTitle('Palettes')).toBeInTheDocument();
    });

    it('shows Configure section with Palettes; appearance is in My Settings', async () => {
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        expect(screen.getByTitle('Palettes')).toBeInTheDocument();
        expect(screen.getByTitle('My Settings')).toBeInTheDocument();
    });

    it('shows User Management when user is admin', async () => {
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        expect(screen.getByTitle('User Management')).toBeInTheDocument();
    });

    it('hides User Management when user is not admin', async () => {
        mockGetMe.mockResolvedValue({
            id: 'u2',
            username: 'user',
            is_admin: false,
            settings: {},
            api_keys: {},
        });
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        expect(screen.queryByTitle('User Management')).not.toBeInTheDocument();
    });

    it('opens My Settings when avatar is clicked', async () => {
        const user = userEvent.setup();
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        const avatar = screen.getByTitle('My Settings');
        await user.click(avatar);
        await waitFor(() => expect(screen.getByText('My Settings')).toBeInTheDocument());
    });

    it('uses semantic mw theme classes on the authenticated shell', async () => {
        renderApp();
        await waitFor(() => expect(screen.getByTitle('Workspace')).toBeInTheDocument());
        const shell = document.querySelector('.flex.h-screen.overflow-hidden');
        expect(shell).toBeTruthy();
        expect(shell?.classList.contains('bg-mw-page')).toBe(true);
        expect(shell?.classList.contains('text-mw-text-primary')).toBe(true);
    });
});
