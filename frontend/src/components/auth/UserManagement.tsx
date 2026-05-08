/**
 * UserManagement
 * ==============
 * Admin-only modal for creating and managing users. Opened from Configure section.
 * Contains Create User and Manage Users via AdminControlsContent.
 */

import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { ManagerModal } from '../ManagerModal';
import { AdminControlsContent, AdminSectionId } from './AdminControlsContent';

export const UserManagement: React.FC<{ isOpen: boolean; onClose: () => void }> = ({ isOpen, onClose }) => {
    const { user, checkAuth } = useAuth();
    const [selectedSection, setSelectedSection] = useState<AdminSectionId>('create');

    if (!isOpen || !user || !user.is_admin) return null;

    return (
        <ManagerModal isOpen={isOpen} onClose={onClose} title="Manage Users" maxWidth="4xl">
            <AdminControlsContent
                currentUser={{ id: user.id, username: user.username, is_admin: user.is_admin }}
                onUserUpdated={() => void checkAuth({ silent: true })}
                showSectionNav={true}
                selectedSection={selectedSection}
                onSectionChange={setSelectedSection}
            />
        </ManagerModal>
    );
};
