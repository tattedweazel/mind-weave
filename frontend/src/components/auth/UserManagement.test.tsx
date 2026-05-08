import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { UserManagement } from './UserManagement';
import { AuthProvider } from '../../contexts/AuthContext';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { AuthClient } from '../../api/authClient';

vi.mock('../../api/authClient', () => ({
    AuthClient: {
        getMe: vi.fn(),
        getUsers: vi.fn().mockResolvedValue([
            { id: 'u1', username: 'admin', is_admin: true, google_email: null },
        ]),
        adminCreateUser: vi.fn(),
        adminUpdateUser: vi.fn(),
        deleteUser: vi.fn(),
        adminDisassociateGoogle: vi.fn(),
    },
}));

const mockGetMe = vi.mocked(AuthClient.getMe);

const renderWithProviders = (props: { isOpen: boolean; onClose: () => void }) =>
    render(
        <AuthProvider>
            <ThemeProvider>
                <UserManagement {...props} />
            </ThemeProvider>
        </AuthProvider>
    );

describe('UserManagement', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 'admin',
            is_admin: true,
            settings: {},
            api_keys: {},
        });
    });

    it('renders nothing when closed', () => {
        const { container } = renderWithProviders({ isOpen: false, onClose: () => {} });
        expect(container.firstChild).toBeNull();
    });

    it('renders nothing when user is not admin', async () => {
        mockGetMe.mockResolvedValue({
            id: 'u2',
            username: 'user',
            is_admin: false,
            settings: {},
            api_keys: {},
        });
        const { container } = renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(mockGetMe).toHaveBeenCalled());
        expect(container.firstChild).toBeNull();
    });

    it('renders Manage Users modal when open and user is admin', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(
            () => expect(screen.getByRole('heading', { name: 'Manage Users' })).toBeInTheDocument(),
            { timeout: 3000 }
        );
        expect(screen.getByRole('button', { name: /Create User/i })).toBeInTheDocument();
        expect(screen.getAllByText('Manage Users')).toHaveLength(2);
    });
});
