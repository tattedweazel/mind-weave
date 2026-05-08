import { describe, it, expect, vi, afterEach } from 'vitest';
import {
    audioBase64ToBlob,
    downloadAudioBase64,
    normalizeAudioBase64Payload,
    playTtsAudioFromBase64,
} from './ttsAudioPlayback';

describe('normalizeAudioBase64Payload', () => {
    it('strips data URL prefix and interior whitespace', () => {
        const raw = ` data:audio/wav;base64,${btoa('hi')} \n `;
        expect(normalizeAudioBase64Payload(raw)).toBe(btoa('hi'));
    });
});

describe('audioBase64ToBlob', () => {
    it('decodes standard base64', () => {
        const blob = audioBase64ToBlob(btoa('hello'), 'application/octet-stream');
        expect(blob.size).toBe(5);
        expect(blob.type).toBe('application/octet-stream');
    });

    it('normalizes audio/wav blob type to audio/wave', () => {
        const blob = audioBase64ToBlob(btoa('x'), 'audio/wav');
        expect(blob.type).toBe('audio/wave');
    });

    it('trims whitespace around base64', () => {
        const blob = audioBase64ToBlob(`  ${btoa('x')}  `, 'audio/wav');
        expect(blob.size).toBe(1);
    });

    it('throws on invalid base64', () => {
        expect(() => audioBase64ToBlob('%%%', 'audio/wav')).toThrow(/Invalid base64/);
    });
});

describe('playTtsAudioFromBase64', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('resolves after ended and revokes object URL', async () => {
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => {
            queueMicrotask(() => handlers.ended?.());
            return Promise.resolve();
        });
        const removeEventListener = vi.fn();
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = removeEventListener;
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await playTtsAudioFromBase64(btoa('ab'), 'audio/wav');

        expect(play).toHaveBeenCalled();
        expect(revokeSpy).toHaveBeenCalled();
        revokeSpy.mockRestore();
    });
});

describe('downloadAudioBase64', () => {
    it('creates a temporary link and revokes the URL', () => {
        const click = vi.fn();
        const append = vi.fn();
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const anchor = {
            click,
            rel: '',
            href: '',
            download: '',
            remove: vi.fn(),
        } as unknown as HTMLAnchorElement;
        const createEl = vi.spyOn(document, 'createElement').mockReturnValue(anchor);
        vi.spyOn(document.body, 'appendChild').mockImplementation(append);

        downloadAudioBase64(btoa('z'), 'audio/wav', 'out.wav');

        expect(createEl).toHaveBeenCalledWith('a');
        expect(click).toHaveBeenCalled();
        expect(revokeSpy).toHaveBeenCalled();
        createEl.mockRestore();
        revokeSpy.mockRestore();
    });
});
