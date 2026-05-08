import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PaletteManager } from './PaletteManager';
import { AuthProvider } from '../contexts/AuthContext';
import { ThemeProvider } from '../contexts/ThemeContext';
import { ApiClient } from '../api/client';
import { AuthClient } from '../api/authClient';

const mockSystemThemeRow = vi.hoisted(() => ({
    id: 'sp-default',
    user_id: null as string | null,
    name: 'Default',
    slug: 'default',
    colors: { light: { page_bg: '#f9fafb' }, dark: { page_bg: '#030712' } },
    created_at: '',
    updated_at: '',
}));

vi.mock('../api/client', () => ({
    ApiClient: {
        getPalettes: vi.fn().mockResolvedValue([
            { id: 'p1', user_id: null, name: 'Default', colors: { string: '#38bdf8' }, created_at: '', updated_at: '' },
        ]),
        getSystemPalettes: vi.fn().mockResolvedValue([mockSystemThemeRow]),
        getSystemPalette: vi.fn(),
        createPalette: vi.fn().mockResolvedValue({ id: 'new1', user_id: 'u1', name: '', colors: {}, created_at: '', updated_at: '' }),
        updatePalette: vi.fn(),
        deletePalette: vi.fn(),
        createSystemPalette: vi.fn().mockResolvedValue({ ...mockSystemThemeRow, id: 'new-sp', user_id: 'u1' }),
        updateSystemPalette: vi.fn(),
        deleteSystemPalette: vi.fn(),
    },
}));

vi.mock('../api/authClient', () => ({
    AuthClient: {
        getMe: vi.fn().mockRejectedValue(new Error('no token')),
        updateMe: vi.fn().mockResolvedValue({}),
    },
}));

const renderWithProviders = (props: { isOpen: boolean; onClose: () => void }) =>
    render(
        <AuthProvider>
            <ThemeProvider>
                <PaletteManager {...props} />
            </ThemeProvider>
        </AuthProvider>
    );

describe('PaletteManager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(AuthClient.getMe).mockRejectedValue(new Error('no token'));
    });

    it('renders nothing when closed', () => {
        const { container } = renderWithProviders({ isOpen: false, onClose: () => {} });
        expect(container.firstChild).toBeNull();
    });

    it('renders Manage Palettes header when open', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        expect(await screen.findByText('Manage Palettes')).toBeInTheDocument();
    });

    it('shows Editor and System tabs when open', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        expect(await screen.findByText('Editor')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /^system$/i })).toBeInTheDocument();
    });

    it('switches to System tab when clicked', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('Manage Palettes');
        await user.click(screen.getByRole('button', { name: /system/i }));
        expect(await screen.findByText('New Theme')).toBeInTheDocument();
        expect(screen.getByText('Default')).toBeInTheDocument();
    });

    it('New System Theme keeps name field enabled (not mistaken for built-in)', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('Manage Palettes');
        await user.click(screen.getByRole('button', { name: /system/i }));
        await user.click(await screen.findByRole('button', { name: /new theme/i }));
        expect(screen.getByPlaceholderText('e.g. My theme')).not.toBeDisabled();
    });

    it('Use as my theme calls updateMe with system_palette_id', async () => {
        vi.mocked(AuthClient.getMe).mockResolvedValue({
            id: 'u1',
            username: 'tester',
            is_admin: false,
            settings: {},
            api_keys: {},
        });
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('Manage Palettes');
        await user.click(screen.getByRole('button', { name: /system/i }));
        await user.click(await screen.findByText('Default'));
        await user.click(screen.getByRole('button', { name: /^use as my theme$/i }));
        expect(AuthClient.updateMe).toHaveBeenCalledWith({
            settings: expect.objectContaining({ system_palette_id: 'sp-default' }),
        });
    });

    it('System theme list row check icon calls updateMe without opening editor flow', async () => {
        vi.mocked(AuthClient.getMe).mockResolvedValue({
            id: 'u1',
            username: 'tester',
            is_admin: false,
            settings: {},
            api_keys: {},
        });
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('Manage Palettes');
        await user.click(screen.getByRole('button', { name: /system/i }));
        await screen.findByText('Default');
        await user.click(screen.getByRole('button', { name: /use as my theme from list/i }));
        expect(AuthClient.updateMe).toHaveBeenCalledWith({
            settings: expect.objectContaining({ system_palette_id: 'sp-default' }),
        });
    });

    it('shows Editor content by default', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        expect(screen.getByText('New Palette')).toBeInTheDocument();
    });

    it('shows step family color section and saves family keys', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        await user.click(screen.getByText('New Palette'));

        expect(await screen.findByText('Step family colors (optional)')).toBeInTheDocument();
        expect(screen.getByText('Primitives')).toBeInTheDocument();
        expect(screen.getByText('Skills')).toBeInTheDocument();
        expect(screen.getByText('Utilities')).toBeInTheDocument();
        expect(screen.getByText('Controls')).toBeInTheDocument();
        expect(screen.getByText('Specific step colors')).toBeInTheDocument();

        await user.type(screen.getByPlaceholderText('e.g. Default'), 'My Palette');

        const familyHexInputs = screen.getAllByPlaceholderText('optional — inherit per step');
        expect(familyHexInputs.length).toBe(4);
        await user.type(familyHexInputs[3], '#aabbcc');

        await user.click(screen.getByRole('button', { name: /save palette/i }));

        expect(ApiClient.createPalette).toHaveBeenCalledWith(
            expect.objectContaining({
                name: 'My Palette',
                colors: expect.objectContaining({ control: '#aabbcc' }),
            })
        );
    });

    it('imports JSON from file and creates palette on save', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        const fileInput = document.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
        const json = JSON.stringify({
            schema_version: 1,
            name: 'From File',
            colors: { primitive: '#112233' },
        });
        await user.upload(fileInput, new File([json], 'pal.json', { type: 'application/json' }));
        expect(await screen.findByDisplayValue('From File')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /save palette/i }));
        expect(ApiClient.createPalette).toHaveBeenCalledWith(
            expect.objectContaining({
                name: 'From File',
                colors: expect.objectContaining({ primitive: '#112233' }),
            })
        );
    });

    it('disables Export JSON until name is non-empty', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        await user.click(screen.getByText('New Palette'));
        const exportBtn = screen.getByRole('button', { name: /export json/i });
        expect(exportBtn).toBeDisabled();
        await user.type(screen.getByPlaceholderText('e.g. Default'), 'Named');
        expect(exportBtn).not.toBeDisabled();
    });

    it('confirm decline keeps draft when importing over existing editor content', async () => {
        const user = userEvent.setup();
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        await user.click(screen.getByText('New Palette'));
        await user.type(screen.getByPlaceholderText('e.g. Default'), 'Draft');
        const fileInput = document.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
        const json = JSON.stringify({ schema_version: 1, name: 'Replaced', colors: {} });
        await user.upload(fileInput, new File([json], 'p.json', { type: 'application/json' }));
        expect(screen.getByDisplayValue('Draft')).toBeInTheDocument();
        expect(screen.queryByDisplayValue('Replaced')).not.toBeInTheDocument();
        confirmSpy.mockRestore();
    });

    it('shows import error on invalid JSON when no editor form is open', async () => {
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await screen.findByText('New Palette');
        const fileInput = document.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
        await user.upload(fileInput, new File(['{'], 'bad.json', { type: 'application/json' }));
        expect(await screen.findByText(/invalid json file/i)).toBeInTheDocument();
    });
});
