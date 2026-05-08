import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MySettings } from './MySettings';
import { AuthProvider } from '../../contexts/AuthContext';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { AuthClient } from '../../api/authClient';
import { ApiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
    ApiClient: {
        getSystemPalettes: vi.fn(),
        getPalettes: vi.fn(),
        getGoogleWorkflowConnections: vi.fn(),
    },
}));

vi.mock('../../api/authClient', () => ({
    AuthClient: {
        getMe: vi.fn(),
        updateMe: vi.fn(),
        getGoogleAuthorizeUrl: vi.fn(),
        disassociateGoogle: vi.fn(),
        getUsers: vi.fn().mockResolvedValue([]),
    },
}));

const mockGetMe = vi.mocked(AuthClient.getMe);

const renderWithProviders = (props: { isOpen: boolean; onClose: () => void }) =>
    render(
        <AuthProvider>
            <ThemeProvider>
                <MySettings {...props} />
            </ThemeProvider>
        </AuthProvider>
    );

describe('MySettings', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockGetMe.mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: {},
        });
        vi.mocked(ApiClient.getSystemPalettes).mockResolvedValue([
            {
                id: 'sp1',
                user_id: null,
                name: 'Default',
                slug: 'default',
                colors: { light: {}, dark: {} },
                created_at: '',
                updated_at: '',
            },
        ]);
        vi.mocked(ApiClient.getPalettes).mockResolvedValue([
            {
                id: 'wp1',
                user_id: null,
                name: 'Default',
                slug: 'default',
                colors: {},
                created_at: '',
                updated_at: '',
            },
        ]);
        vi.mocked(ApiClient.getGoogleWorkflowConnections).mockResolvedValue([]);
    });

    it('renders nothing when closed', async () => {
        renderWithProviders({ isOpen: false, onClose: () => {} });
        await waitFor(() => expect(mockGetMe).toHaveBeenCalled());
        expect(screen.queryByText('My Settings')).not.toBeInTheDocument();
    });

    it('renders My Settings modal when open', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByRole('heading', { name: 'My Settings' })).toBeInTheDocument());
        expect(screen.getAllByText('My Profile').length).toBeGreaterThan(0);
        expect(screen.getByText('Google Account')).toBeInTheDocument();
        expect(screen.getByText('API Settings')).toBeInTheDocument();
        expect(screen.getByText('View Settings')).toBeInTheDocument();
        expect(screen.getByText('System Settings')).toBeInTheDocument();
    });

    it('shows My Profile section by default', async () => {
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('testuser')).toBeInTheDocument());
        expect(screen.getByText('Sign Out')).toBeInTheDocument();
    });

    it('shows timezone on profile and saves when changed', async () => {
        const ue = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: { workflow_time_zone: 'Europe/Berlin' },
            api_keys: {},
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByLabelText(/^timezone$/i)).toBeInTheDocument());
        expect(screen.queryByRole('button', { name: /^save$/i })).not.toBeInTheDocument();
        await ue.selectOptions(screen.getByLabelText(/^timezone$/i), 'Europe/Berlin');
        await waitFor(() => expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument());
        await ue.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                settings: expect.objectContaining({ workflow_time_zone: 'Europe/Berlin' }),
            }),
        );
    });

    it('save view settings calls updateMe with theme and palette keys', async () => {
        const user = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: {},
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('View Settings')).toBeInTheDocument());
        await user.click(screen.getByText('View Settings'));
        await waitFor(() => expect(screen.getByRole('button', { name: /save view settings/i })).toBeInTheDocument());
        await user.selectOptions(screen.getByLabelText(/appearance/i), 'dark');
        await user.selectOptions(screen.getByLabelText(/^system palette$/i), 'sp1');
        await user.selectOptions(screen.getByLabelText(/^preferred editor palette$/i), 'wp1');
        await user.click(screen.getByRole('button', { name: /save view settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                settings: expect.objectContaining({
                    theme_mode: 'dark',
                    system_palette_id: 'sp1',
                    preferred_editor_palette_id: 'wp1',
                    workflow_editor_remember_panel_widths: true,
                }),
            }),
        );
    });

    it('save view settings sends workflow_editor_remember_panel_widths false when unchecked', async () => {
        const user = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: {},
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('View Settings')).toBeInTheDocument());
        await user.click(screen.getByText('View Settings'));
        await waitFor(() =>
            expect(screen.getByRole('checkbox', { name: /remember workflow editor panel widths/i })).toBeInTheDocument(),
        );
        await user.click(screen.getByRole('checkbox', { name: /remember workflow editor panel widths/i }));
        await user.click(screen.getByRole('button', { name: /save view settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                settings: expect.objectContaining({
                    workflow_editor_remember_panel_widths: false,
                }),
            }),
        );
    });

    it('save system settings calls updateMe with max_concurrent_lm_studio_calls', async () => {
        const user = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: { max_concurrent_lm_studio_calls: 5 },
            api_keys: {},
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getAllByText('System Settings').length).toBeGreaterThan(0));
        await user.click(screen.getAllByText('System Settings')[0]);
        const input = await screen.findByLabelText(/^max concurrent lm studio calls$/i);
        fireEvent.change(input, { target: { value: '5' } });
        await waitFor(() =>
            expect(screen.getByRole('button', { name: /save system settings/i })).toBeInTheDocument(),
        );
        await user.click(screen.getByRole('button', { name: /save system settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                settings: expect.objectContaining({ max_concurrent_lm_studio_calls: 5 }),
            }),
        );
    });

    it('save API settings does not call updateMe when all key fields are empty', async () => {
        const ue = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('API Settings')).toBeInTheDocument());
        await ue.click(screen.getByText('API Settings'));
        await ue.click(screen.getByRole('button', { name: /save settings/i }));
        await waitFor(() => expect(screen.getByText(/No new keys entered/i)).toBeInTheDocument());
        expect(updateMe).not.toHaveBeenCalled();
    });

    it('save API settings reads LM Studio key from input and sends updateMe', async () => {
        const ue = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: { lmstudio_api_key: '[stored]' },
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('API Settings')).toBeInTheDocument());
        await ue.click(screen.getByText('API Settings'));
        const lmInput = await screen.findByLabelText(/^LM Studio API Key$/i);
        await ue.type(lmInput, 'sk-lm-test-from-ref');
        await ue.click(screen.getByRole('button', { name: /save settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                api_keys: { lmstudio_api_key: 'sk-lm-test-from-ref' },
            }),
        );
    });

    it('save API settings reads AssemblyAI key from input and sends updateMe', async () => {
        const ue = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: { assemblyai: '[stored]' },
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('API Settings')).toBeInTheDocument());
        await ue.click(screen.getByText('API Settings'));
        const aaInput = await screen.findByLabelText(/^AssemblyAI API Key$/i);
        await ue.type(aaInput, 'aai-test-key');
        await ue.click(screen.getByRole('button', { name: /save settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                api_keys: { assemblyai: 'aai-test-key' },
            }),
        );
    });

    it('save API settings strips Bearer prefix from LM Studio key before updateMe', async () => {
        const ue = userEvent.setup();
        const updateMe = vi.mocked(AuthClient.updateMe).mockResolvedValue({
            id: 'u1',
            username: 'testuser',
            is_admin: true,
            settings: {},
            api_keys: { lmstudio_api_key: '[stored]' },
        } as never);
        renderWithProviders({ isOpen: true, onClose: () => {} });
        await waitFor(() => expect(screen.getByText('API Settings')).toBeInTheDocument());
        await ue.click(screen.getByText('API Settings'));
        const lmInput = await screen.findByLabelText(/^LM Studio API Key$/i);
        await ue.type(lmInput, 'Bearer sk-ui-strip');
        await ue.click(screen.getByRole('button', { name: /save settings/i }));
        await waitFor(() =>
            expect(updateMe).toHaveBeenCalledWith({
                api_keys: { lmstudio_api_key: 'sk-ui-strip' },
            }),
        );
    });

    it('calls onClose when close button is clicked', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        renderWithProviders({ isOpen: true, onClose });
        await waitFor(() => expect(screen.getByText('My Settings')).toBeInTheDocument());
        const closeButton = screen.getByRole('button', { name: 'Close' });
        await user.click(closeButton);
        expect(onClose).toHaveBeenCalled();
    });
});
