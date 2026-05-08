import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AdminControlsContent } from './AdminControlsContent';
import { AuthClient } from '../../api/authClient';

vi.mock('../../api/authClient');

const mockGetUsers = vi.mocked(AuthClient.getUsers);
const mockAdminCreateUser = vi.mocked(AuthClient.adminCreateUser);
const mockDeleteUser = vi.mocked(AuthClient.deleteUser);
const mockAdminUpdateUser = vi.mocked(AuthClient.adminUpdateUser);
const currentUser = {
    id: 'u1',
    username: 'admin',
    is_admin: true,
    settings: {},
    api_keys: {},
};

describe('AdminControlsContent', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockGetUsers.mockResolvedValue([
            {
                id: 'u1',
                username: 'admin',
                is_admin: true,
                google_email: null,
                settings: {},
                api_keys: {},
            },
            {
                id: 'u2',
                username: 'user1',
                is_admin: false,
                google_email: 'u@x.com',
                settings: {},
                api_keys: {},
            },
        ]);
        vi.spyOn(window, 'confirm').mockReturnValue(true);
    });

    it('loads and displays users', async () => {
        render(
            <AdminControlsContent
                currentUser={currentUser}
                showSectionNav={true}
                selectedSection="manage"
                onSectionChange={() => {}}
            />
        );
        await waitFor(() => {
            expect(mockGetUsers).toHaveBeenCalledWith();
        });
        await waitFor(() => {
            expect(screen.getByText('admin')).toBeInTheDocument();
            expect(screen.getByText('user1')).toBeInTheDocument();
        });
    });

    it('shows Create User and Manage Users when showSectionNav', async () => {
        render(
            <AdminControlsContent
                currentUser={currentUser}
                showSectionNav={true}
                selectedSection="create"
                onSectionChange={() => {}}
            />
        );
        expect(screen.getByRole('button', { name: /Create User/i })).toBeInTheDocument();
        expect(screen.getByText('Create New User')).toBeInTheDocument();
        expect(screen.getByText('Manage Users')).toBeInTheDocument();
    });

    it('creates user on form submit', async () => {
        mockAdminCreateUser.mockResolvedValue(undefined);
        const user = userEvent.setup();
        render(
            <AdminControlsContent
                currentUser={currentUser}
                showSectionNav={false}
            />
        );
        await waitFor(() => expect(mockGetUsers).toHaveBeenCalled());
        await user.type(screen.getByPlaceholderText('Username'), 'newuser');
        await user.type(screen.getByPlaceholderText('Password'), 'pass123');
        await user.click(screen.getByRole('button', { name: /Create User/i }));
        await waitFor(() => {
            expect(mockAdminCreateUser).toHaveBeenCalledWith('newuser', 'pass123', false);
        });
    });

    it('calls onUserUpdated when editing self', async () => {
        mockAdminUpdateUser.mockResolvedValue(undefined);
        const onUserUpdated = vi.fn();
        const user = userEvent.setup();
        render(
            <AdminControlsContent
                currentUser={currentUser}
                onUserUpdated={onUserUpdated}
                showSectionNav={false}
            />
        );
        await waitFor(() => expect(mockGetUsers).toHaveBeenCalled());
        const editBtn = screen.getAllByTitle('Edit user')[0];
        await user.click(editBtn);
        const usernameInput = screen.getByLabelText(/^Username$/);
        await user.clear(usernameInput);
        await user.type(usernameInput, 'newname');
        await user.click(screen.getByRole('button', { name: 'Save' }));
        await waitFor(() => {
            expect(mockAdminUpdateUser).toHaveBeenCalled();
            expect(onUserUpdated).toHaveBeenCalled();
        });
    });

    it('deletes user when confirm is accepted', async () => {
        mockDeleteUser.mockResolvedValue(undefined);
        const user = userEvent.setup();
        render(
            <AdminControlsContent
                currentUser={currentUser}
                showSectionNav={false}
            />
        );
        await waitFor(() => expect(mockGetUsers).toHaveBeenCalled());
        const deleteBtns = screen.getAllByTitle('Delete user');
        await user.click(deleteBtns[0]);
        await waitFor(() => {
            expect(mockDeleteUser).toHaveBeenCalledWith('u2');
        });
    });

    it('shows Admin Controls heading when not showSectionNav', () => {
        render(
            <AdminControlsContent
                currentUser={currentUser}
                showSectionNav={false}
            />
        );
        expect(screen.getByText('Admin Controls')).toBeInTheDocument();
    });
});
