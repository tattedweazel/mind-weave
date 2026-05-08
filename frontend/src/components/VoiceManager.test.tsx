import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { VoiceManager } from './VoiceManager';
import { ApiClient } from '../api/client';

vi.mock('../domain/ttsAudioPlayback', () => ({
    createObjectUrlForAudioBase64: vi.fn(() => 'blob:mock'),
    playTtsAudioFromBase64: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../api/client', () => ({
    ApiClient: {
        getVoiceSamples: vi.fn(),
        getTtsModelsReady: vi.fn(),
        getVoiceSample: vi.fn(),
        getVoiceSampleAudioBlob: vi.fn(),
        previewVoiceDesign: vi.fn(),
        createVoiceSample: vi.fn(),
        deleteVoiceSample: vi.fn(),
    },
}));

describe('VoiceManager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(ApiClient.getVoiceSamples).mockResolvedValue([]);
        vi.mocked(ApiClient.getTtsModelsReady).mockResolvedValue([
            {
                id: 'm1',
                display_name: 'Qwen Design',
                engine: 'qwen_torch',
                status: 'ready',
                local_key: 'k',
                source: {},
                error_message: null,
                created_at: '',
                updated_at: '',
            },
        ]);
    });

    it('renders nothing when closed', () => {
        const { container } = render(<VoiceManager isOpen={false} onClose={() => {}} />);
        expect(container.firstChild).toBeNull();
    });

    it('lists samples and can run preview when open', async () => {
        const user = userEvent.setup();
        vi.mocked(ApiClient.getVoiceSamples).mockResolvedValue([
            { id: 's1', name: 'Alpha', language: 'English', created_at: '' },
        ]);
        vi.mocked(ApiClient.previewVoiceDesign).mockResolvedValue({
            mime_type: 'audio/wav',
            audio_base64: 'ZmFrZQ==',
        });
        render(<VoiceManager isOpen onClose={() => {}} />);
        expect(await screen.findByText('Alpha')).toBeInTheDocument();
        await user.type(screen.getByPlaceholderText(/e\.g\. narrator warm/i), 'My voice');
        await user.type(screen.getByPlaceholderText(/what voice design will speak/i), 'Hello world');
        await user.click(screen.getByRole('button', { name: /^generate$/i }));
        expect(ApiClient.previewVoiceDesign).toHaveBeenCalledWith(
            expect.objectContaining({
                design_model_id: 'm1',
                text: 'Hello world',
            }),
        );
    });
});
