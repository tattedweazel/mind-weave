/**
 * AdminControlsContent
 * ====================
 * Shared admin UI: Create User form and Manage Users table.
 * Used by UserManagement (Configure section) and MySettings (Admin Controls).
 */

import React, { useState, useEffect } from 'react';
import { AuthClient } from '../../api/authClient';
import { Plus, Edit2, Trash2, Unlink } from 'lucide-react';
import { MANAGER_INPUT_CLS, MANAGER_LABEL_CLS } from '../managerShellStyles';

const inputCls = MANAGER_INPUT_CLS;
const labelCls = MANAGER_LABEL_CLS;

export interface ListUser {
    id: string;
    username: string;
    is_admin: boolean;
    google_email?: string | null;
}

export type AdminSectionId = 'create' | 'manage';

export interface AdminControlsContentProps {
    currentUser: { id: string; username: string; is_admin: boolean };
    onUserUpdated?: () => void;
    /** Which section to show when used with left nav (create vs manage). */
    selectedSection?: AdminSectionId;
    onSectionChange?: (id: AdminSectionId) => void;
    /** When true, show Create User and Manage Users as separate left-panel options. */
    showSectionNav?: boolean;
}

export const AdminControlsContent: React.FC<AdminControlsContentProps> = ({
    currentUser,
    onUserUpdated,
    selectedSection = 'create',
    onSectionChange,
    showSectionNav = false,
}) => {
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newIsAdmin, setNewIsAdmin] = useState(false);
    const [allUsers, setAllUsers] = useState<ListUser[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const [editingUserId, setEditingUserId] = useState<string | null>(null);
    const [editUsername, setEditUsername] = useState('');
    const [editPassword, setEditPassword] = useState('');
    const [editIsAdmin, setEditIsAdmin] = useState(false);
    const [isUpdatingUser, setIsUpdatingUser] = useState(false);

    const loadUsers = async () => {
        try {
            const users = await AuthClient.getUsers();
            setAllUsers(users);
        } catch (err) {
            console.error(err);
        }
    };

    useEffect(() => {
        loadUsers();
    }, []);

    const handleCreateUser = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSuccess(null);
        try {
            await AuthClient.adminCreateUser(newUsername, newPassword, newIsAdmin);
            setSuccess(`User ${newUsername} created successfully.`);
            setNewUsername('');
            setNewPassword('');
            setNewIsAdmin(false);
            loadUsers();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to create user');
        }
    };

    const handleDeleteUser = async (userId: string) => {
        if (!window.confirm('Are you sure you want to delete this user? This cannot be undone.')) return;
        setError(null);
        setSuccess(null);
        try {
            await AuthClient.deleteUser(userId);
            setSuccess('User deleted successfully.');
            setEditingUserId(null);
            loadUsers();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to delete user');
        }
    };

    const handleAdminDisassociateGoogle = async (userId: string) => {
        if (!window.confirm('Remove Google association for this user? They will need to log in with username/password until they associate again.')) return;
        setError(null);
        setSuccess(null);
        try {
            await AuthClient.adminDisassociateGoogle(userId);
            setSuccess('Google association removed for user.');
            loadUsers();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to remove Google association');
        }
    };

    const handleStartEdit = (u: ListUser) => {
        setEditingUserId(u.id);
        setEditUsername(u.username);
        setEditPassword('');
        setEditIsAdmin(u.is_admin);
        setError(null);
    };

    const handleCancelEdit = () => {
        setEditingUserId(null);
        setEditUsername('');
        setEditPassword('');
        setEditIsAdmin(false);
    };

    const handleSaveUser = async () => {
        if (!editingUserId) return;
        setIsUpdatingUser(true);
        setError(null);
        setSuccess(null);
        try {
            const updates: { username?: string; password?: string; is_admin?: boolean } = {};
            const existing = allUsers.find(u => u.id === editingUserId);
            if (existing && editUsername !== existing.username) updates.username = editUsername;
            if (editPassword) updates.password = editPassword;
            if (existing && editIsAdmin !== existing.is_admin) updates.is_admin = editIsAdmin;
            if (Object.keys(updates).length === 0) {
                setEditingUserId(null);
                return;
            }
            await AuthClient.adminUpdateUser(editingUserId, updates);
            setSuccess('User updated successfully.');
            setEditingUserId(null);
            loadUsers();
            if (editingUserId === currentUser.id && updates.username && onUserUpdated) {
                await onUserUpdated();
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to update user');
        } finally {
            setIsUpdatingUser(false);
        }
    };

    const effectiveSection = showSectionNav ? selectedSection : 'create';
    const showCreate = !showSectionNav || effectiveSection === 'create';
    const showManage = !showSectionNav || effectiveSection === 'manage';

    const content = (
        <>
            {error && <div className="text-sm text-mw-error bg-mw-error-muted border border-mw-error px-3 py-2 rounded-lg mb-4">{error}</div>}
            {success && <div className="text-sm text-mw-success bg-mw-success-muted border border-mw-success px-3 py-2 rounded-lg mb-4">{success}</div>}

            {showCreate && (
                <form onSubmit={handleCreateUser} className="space-y-4 p-4 rounded-lg border border-mw-border bg-mw-sidebar">
                    <h4 className="text-sm font-semibold text-mw-text-primary">Create New User</h4>
                    <div className="grid grid-cols-2 gap-4">
                        <input type="text" value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder="Username" required className={inputCls} />
                        <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Password" required className={inputCls} />
                        <div className="col-span-2 flex items-center">
                            <input type="checkbox" id="new_is_admin" checked={newIsAdmin} onChange={e => setNewIsAdmin(e.target.checked)} className="h-4 w-4 text-mw-primary focus:ring-mw-primary border-mw-border rounded" />
                            <label htmlFor="new_is_admin" className="ml-2 text-sm text-mw-text-primary">Administrator</label>
                        </div>
                    </div>
                    <button type="submit" className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors">
                        <Plus size={16} />
                        Create User
                    </button>
                </form>
            )}

            {showManage && (
                <div>
                    <h4 className="text-sm font-semibold text-mw-text-primary mb-3">All Users</h4>
                    <div className="rounded-lg border border-mw-border overflow-hidden">
                        <table className="min-w-full divide-y divide-mw-border">
                            <thead className="bg-mw-sidebar">
                                <tr>
                                    <th className="px-4 py-2.5 text-left text-xs font-medium text-mw-text-secondary uppercase tracking-wider">Username</th>
                                    <th className="px-4 py-2.5 text-left text-xs font-medium text-mw-text-secondary uppercase tracking-wider">Role</th>
                                    <th className="px-4 py-2.5 text-left text-xs font-medium text-mw-text-secondary uppercase tracking-wider">Google</th>
                                    <th className="px-4 py-2.5 text-right text-xs font-medium text-mw-text-secondary uppercase tracking-wider">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-mw-border">
                                {allUsers.map((u) => (
                                    <React.Fragment key={u.id}>
                                        <tr className={editingUserId === u.id ? 'bg-mw-primary-muted' : 'bg-mw-card'}>
                                            {editingUserId === u.id ? (
                                                <td colSpan={4} className="px-4 py-3">
                                                    <div className="space-y-3">
                                                        <div className="grid grid-cols-2 gap-3">
                                                            <div>
                                                                <label htmlFor="edit_username" className={labelCls}>Username</label>
                                                                <input id="edit_username" type="text" value={editUsername} onChange={e => setEditUsername(e.target.value)} className={inputCls} />
                                                            </div>
                                                            <div>
                                                                <label htmlFor="edit_password" className={labelCls}>New Password (leave blank to keep)</label>
                                                                <input id="edit_password" type="password" value={editPassword} onChange={e => setEditPassword(e.target.value)} placeholder="Optional" className={inputCls} />
                                                            </div>
                                                            <div className="col-span-2 flex items-center">
                                                                <input type="checkbox" id="edit_is_admin" checked={editIsAdmin} onChange={e => setEditIsAdmin(e.target.checked)} className="h-4 w-4 text-mw-primary focus:ring-mw-primary border-mw-border rounded" />
                                                                <label htmlFor="edit_is_admin" className="ml-2 text-sm text-mw-text-primary">Administrator</label>
                                                            </div>
                                                        </div>
                                                        <div className="flex gap-2 pt-2">
                                                            <button type="button" onClick={handleCancelEdit} className="px-4 py-2 text-sm font-medium text-mw-text-secondary hover:bg-mw-card-alt rounded-lg transition-colors">Cancel</button>
                                                            <button type="button" onClick={handleSaveUser} disabled={isUpdatingUser} className="px-4 py-2 text-sm font-medium text-white bg-mw-primary hover:bg-mw-primary-hover rounded-lg transition-colors disabled:opacity-50">
                                                                Save
                                                            </button>
                                                        </div>
                                                    </div>
                                                </td>
                                            ) : (
                                                <>
                                                    <td className="px-4 py-2.5 text-sm font-medium text-mw-text-primary">{u.username}</td>
                                                    <td className="px-4 py-2.5">
                                                        <span className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium ${u.is_admin ? 'bg-mw-primary-muted text-mw-primary' : 'bg-mw-card-alt text-mw-text-secondary'}`}>
                                                            {u.is_admin ? 'Admin' : 'User'}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-2.5 text-sm text-mw-text-secondary">
                                                        {u.google_email || '—'}
                                                    </td>
                                                    <td className="px-4 py-2.5 text-right">
                                                        <div className="flex items-center justify-end gap-1">
                                                            <button type="button" onClick={() => handleStartEdit(u)} className="p-1.5 text-mw-text-secondary hover:text-mw-primary rounded hover:bg-mw-card-alt transition-colors" title="Edit user">
                                                                <Edit2 size={16} />
                                                            </button>
                                                            {u.id !== currentUser.id && u.google_email && (
                                                                <button type="button" onClick={() => handleAdminDisassociateGoogle(u.id)} className="p-1.5 text-mw-text-secondary hover:bg-mw-card-alt rounded transition-colors" title="Remove Google">
                                                                    <Unlink size={16} />
                                                                </button>
                                                            )}
                                                            {u.id !== currentUser.id && (
                                                                <button type="button" onClick={() => handleDeleteUser(u.id)} className="p-1.5 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors" title="Delete user">
                                                                    <Trash2 size={16} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </td>
                                                </>
                                            )}
                                        </tr>
                                    </React.Fragment>
                                ))}
                                {allUsers.length === 0 && (
                                    <tr>
                                        <td colSpan={4} className="px-4 py-8 text-center text-sm text-mw-text-secondary">No users found.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </>
    );

    if (showSectionNav && onSectionChange) {
        return (
            <div className="flex flex-1 overflow-hidden">
                <div className="w-1/3 border-r border-mw-border bg-mw-sidebar flex flex-col">
                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        <div
                            className={`flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${selectedSection === 'create' ? 'bg-mw-primary-muted border border-mw-primary' : 'hover:bg-mw-card border border-transparent'}`}
                            onClick={() => onSectionChange('create')}
                        >
                            <Plus size={16} className="text-mw-text-secondary shrink-0" />
                            <span className="text-sm font-medium text-mw-text-primary truncate">Create User</span>
                        </div>
                        <div
                            className={`flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${selectedSection === 'manage' ? 'bg-mw-primary-muted border border-mw-primary' : 'hover:bg-mw-card border border-transparent'}`}
                            onClick={() => onSectionChange('manage')}
                        >
                            <span className="text-sm font-medium text-mw-text-primary truncate">Manage Users</span>
                        </div>
                    </div>
                </div>
                <div className="w-2/3 bg-mw-card p-6 overflow-y-auto">
                    {content}
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <h3 className="text-lg font-bold text-mw-text-primary border-b border-mw-border pb-2">Admin Controls</h3>
            {content}
        </div>
    );
};
