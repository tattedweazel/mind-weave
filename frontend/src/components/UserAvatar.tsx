/**
 * UserAvatar
 * ==========
 * Renders a circular avatar for a user. Uses initials derived from username
 * with a deterministic color when no custom avatar_url is provided.
 * Custom avatars are stored in user.settings.avatar_url.
 */

import React from 'react';

const AVATAR_COLORS = [
    'bg-blue-500',
    'bg-green-500',
    'bg-amber-500',
    'bg-rose-500',
    'bg-violet-500',
    'bg-cyan-500',
    'bg-emerald-500',
    'bg-orange-500',
];

const SIZE_CLASSES = {
    sm: 'w-8 h-8 text-xs',
    md: 'w-10 h-10 text-sm',
    lg: 'w-12 h-12 text-base',
} as const;

/**
 * Derives initials from a username. Handles:
 * - "john_doe" -> "JD"
 * - "admin" -> "A"
 * - "a" -> "A"
 */
export function getInitials(username: string): string {
    if (!username || username.length === 0) return '?';
    const parts = username.split(/[._\s-]/).filter(Boolean);
    if (parts.length >= 2) {
        const first = parts[0][0] ?? '';
        const second = parts[1][0] ?? '';
        return (first + second).toUpperCase().slice(0, 2);
    }
    return username.slice(0, 2).toUpperCase();
}

/**
 * Returns a deterministic color class index from username.
 */
function getColorIndex(username: string): number {
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
        hash = ((hash << 5) - hash) + username.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash) % AVATAR_COLORS.length;
}

export interface UserAvatarProps {
    /** Username used for initials and color when no avatarUrl. */
    username: string;
    /** Optional custom avatar URL (data URL or external). */
    avatarUrl?: string | null;
    /** Size variant. */
    size?: 'sm' | 'md' | 'lg';
    /** Additional class names. */
    className?: string;
}

export const UserAvatar: React.FC<UserAvatarProps> = ({
    username,
    avatarUrl,
    size = 'md',
    className = '',
}) => {
    const sizeClass = SIZE_CLASSES[size];
    const initials = getInitials(username);
    const colorClass = AVATAR_COLORS[getColorIndex(username)];

    if (avatarUrl && typeof avatarUrl === 'string' && avatarUrl.startsWith('data:')) {
        return (
            <div
                className={`rounded-full overflow-hidden shrink-0 ${sizeClass} ${className}`}
                title={username}
                role="img"
                aria-label={`Avatar for ${username}`}
            >
                <img
                    src={avatarUrl}
                    alt=""
                    className="w-full h-full object-cover"
                />
            </div>
        );
    }

    if (avatarUrl && typeof avatarUrl === 'string' && (avatarUrl.startsWith('http://') || avatarUrl.startsWith('https://'))) {
        return (
            <div
                className={`rounded-full overflow-hidden shrink-0 ${sizeClass} ${className}`}
                title={username}
                role="img"
                aria-label={`Avatar for ${username}`}
            >
                <img
                    src={avatarUrl}
                    alt=""
                    className="w-full h-full object-cover"
                />
            </div>
        );
    }

    return (
        <div
            className={`rounded-full flex items-center justify-center font-semibold text-white shrink-0 ${sizeClass} ${colorClass} ${className}`}
            title={username}
            role="img"
            aria-label={`Avatar for ${username}`}
        >
            {initials}
        </div>
    );
};
