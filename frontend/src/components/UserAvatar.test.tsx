import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UserAvatar, getInitials } from './UserAvatar';

describe('getInitials', () => {
    it('returns first two letters for single-word username', () => {
        expect(getInitials('admin')).toBe('AD');
    });

    it('returns first letter of each part for underscore-separated username', () => {
        expect(getInitials('john_doe')).toBe('JD');
    });

    it('returns first letter of each part for dot-separated username', () => {
        expect(getInitials('john.doe')).toBe('JD');
    });

    it('returns first letter of each part for space-separated username', () => {
        expect(getInitials('john doe')).toBe('JD');
    });

    it('returns first letter of each part for hyphen-separated username', () => {
        expect(getInitials('john-doe')).toBe('JD');
    });

    it('returns single letter for single-char username', () => {
        expect(getInitials('a')).toBe('A');
    });

    it('returns question mark for empty string', () => {
        expect(getInitials('')).toBe('?');
    });
});

describe('UserAvatar', () => {
    it('renders initials when no avatarUrl', () => {
        render(<UserAvatar username="john_doe" />);
        expect(screen.getByText('JD')).toBeInTheDocument();
    });

    it('renders data URL image when avatarUrl is data URL', () => {
        const dataUrl = 'data:image/png;base64,iVBORw0KGgo=';
        render(<UserAvatar username="john" avatarUrl={dataUrl} />);
        const img = screen.getByRole('img', { name: /Avatar for john/i });
        expect(img).toBeInTheDocument();
        expect(img.querySelector('img')).toHaveAttribute('src', dataUrl);
    });

    it('renders external URL image when avatarUrl is http', () => {
        const url = 'https://example.com/avatar.png';
        render(<UserAvatar username="john" avatarUrl={url} />);
        const img = screen.getByRole('img', { name: /Avatar for john/i });
        expect(img).toBeInTheDocument();
        expect(img.querySelector('img')).toHaveAttribute('src', url);
    });

    it('falls back to initials when avatarUrl is null', () => {
        render(<UserAvatar username="admin" avatarUrl={null} />);
        expect(screen.getByText('AD')).toBeInTheDocument();
    });

    it('falls back to initials when avatarUrl is undefined', () => {
        render(<UserAvatar username="admin" />);
        expect(screen.getByText('AD')).toBeInTheDocument();
    });

    it('applies size class for sm', () => {
        const { container } = render(<UserAvatar username="a" size="sm" />);
        const el = container.querySelector('.w-8.h-8');
        expect(el).toBeInTheDocument();
    });

    it('applies size class for md (default)', () => {
        const { container } = render(<UserAvatar username="a" />);
        const el = container.querySelector('.w-10.h-10');
        expect(el).toBeInTheDocument();
    });

    it('applies size class for lg', () => {
        const { container } = render(<UserAvatar username="a" size="lg" />);
        const el = container.querySelector('.w-12.h-12');
        expect(el).toBeInTheDocument();
    });

    it('applies custom className', () => {
        const { container } = render(<UserAvatar username="a" className="custom-class" />);
        const el = container.querySelector('.custom-class');
        expect(el).toBeInTheDocument();
    });

    it('has accessible role and label', () => {
        render(<UserAvatar username="testuser" />);
        expect(screen.getByRole('img', { name: /Avatar for testuser/i })).toBeInTheDocument();
    });
});
