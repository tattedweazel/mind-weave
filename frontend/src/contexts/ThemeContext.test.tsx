import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { ThemeProvider, useTheme } from './ThemeContext';
import { AuthProvider } from './AuthContext';

const mockGetMe = vi.fn().mockRejectedValue(new Error('no token'));
const mockGetSystemPalette = vi.fn();

vi.mock('../api/authClient', () => ({
    AuthClient: {
        getMe: (...args: unknown[]) => mockGetMe(...args),
    },
}));

vi.mock('../api/client', () => ({
    ApiClient: {
        getSystemPalette: (...args: unknown[]) => mockGetSystemPalette(...args),
    },
}));

const TestConsumer: React.FC = () => {
    const { systemColors, isDarkMode, getColor, refreshActiveSystemPalette } = useTheme();
    return (
        <div>
            <span data-testid="page-bg">{getColor('page_bg')}</span>
            <span data-testid="primary">{getColor('primary')}</span>
            <span data-testid="is-dark">{String(isDarkMode)}</span>
            <span data-testid="has-colors">{Object.keys(systemColors).length}</span>
            <button type="button" data-testid="refresh-preset" onClick={() => refreshActiveSystemPalette()}>
                refresh
            </button>
        </div>
    );
};

describe('ThemeContext', () => {
    beforeEach(() => {
        localStorage.removeItem('theme');
        document.documentElement.classList.remove('dark');
        mockGetMe.mockReset();
        mockGetMe.mockRejectedValue(new Error('no token'));
        mockGetSystemPalette.mockReset();
    });

    it('provides default system colors when no user settings', () => {
        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );
        const pageBg = screen.getByTestId('page-bg').textContent;
        const primary = screen.getByTestId('primary').textContent;
        expect(pageBg).toBeTruthy();
        expect(primary).toBeTruthy();
        expect(pageBg).toMatch(/^#/);
        expect(primary).toMatch(/^#/);
    });

    it('getColor returns correct value for known token', () => {
        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );
        const pageBg = screen.getByTestId('page-bg').textContent;
        expect(pageBg).toBe('#f9fafb');
    });

    it('isDarkMode defaults to false when localStorage is absent', () => {
        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );
        expect(screen.getByTestId('is-dark').textContent).toBe('false');
    });

    it('isDarkMode follows user.settings.theme_mode when signed in', async () => {
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 't',
            is_admin: false,
            settings: { theme_mode: 'dark' },
            api_keys: {},
        });
        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );
        await waitFor(() => expect(screen.getByTestId('is-dark').textContent).toBe('true'));
    });

    it('isDarkMode false when signed in with theme_mode light', async () => {
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 't',
            is_admin: false,
            settings: { theme_mode: 'light' },
            api_keys: {},
        });
        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );
        await waitFor(() => expect(screen.getByTestId('is-dark').textContent).toBe('false'));
    });

    it('loads active system palette and refreshActiveSystemPalette triggers a second fetch', async () => {
        const user = userEvent.setup();
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 't',
            is_admin: false,
            settings: { theme_mode: 'light', system_palette_id: 'abc-123' },
            api_keys: {},
        });
        mockGetSystemPalette
            .mockResolvedValueOnce({
                id: 'abc-123',
                name: 'T',
                slug: 't',
                user_id: null,
                colors: { light: { primary: '#111111' }, dark: {} },
                created_at: '',
                updated_at: '',
            })
            .mockResolvedValueOnce({
                id: 'abc-123',
                name: 'T',
                slug: 't',
                user_id: null,
                colors: { light: { primary: '#222222' }, dark: {} },
                created_at: '',
                updated_at: '',
            });

        render(
            <AuthProvider>
                <ThemeProvider>
                    <TestConsumer />
                </ThemeProvider>
            </AuthProvider>
        );

        await waitFor(() => expect(mockGetSystemPalette).toHaveBeenCalledTimes(1));
        await waitFor(() => expect(screen.getByTestId('primary').textContent).toBe('#111111'));

        await user.click(screen.getByTestId('refresh-preset'));
        await waitFor(() => expect(mockGetSystemPalette).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(screen.getByTestId('primary').textContent).toBe('#222222'));
    });
});
