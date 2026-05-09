import { describe, it, expect, vi, afterEach } from 'vitest';
import {
    audioBase64ToBlob,
    createObjectUrlForAudioBase64,
    downloadAudioBase64,
    normalizeAudioBase64Payload,
    normalizeWavBlobType,
    playTtsAudioFromBase64,
} from './ttsAudioPlayback';

describe('normalizeAudioBase64Payload', () => {
    it('strips data URL prefix and interior whitespace', () => {
        const raw = ` data:audio/wav;base64,${btoa('hi')} \n `;
        expect(normalizeAudioBase64Payload(raw)).toBe(btoa('hi'));
    });
});

describe('normalizeWavBlobType', () => {
    it('passes through non-wav MIME types', () => {
        expect(normalizeWavBlobType('audio/mp4')).toBe('audio/mp4');
    });
});

describe('createObjectUrlForAudioBase64', () => {
    it('delegates to URL.createObjectURL', () => {
        const spy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
        expect(createObjectUrlForAudioBase64(btoa('x'), 'audio/wav')).toBe('blob:mock');
        expect(spy).toHaveBeenCalled();
        spy.mockRestore();
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

    it('ignores second ended after already settled', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => {
            queueMicrotask(() => handlers.ended?.());
            queueMicrotask(() => handlers.ended?.());
            return Promise.resolve();
        });
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).resolves.toBeUndefined();
    });

    it('resolves when error fires after playback has started (playing)', async () => {
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => {
            queueMicrotask(() => {
                handlers.playing?.();
                handlers.error?.();
            });
            return Promise.resolve();
        });
        const removeEventListener = vi.fn();
        class MockAudio {
            error: MediaError | null = { code: 4, message: 'mock', MEDIA_ERR_ABORTED: 1,
                MEDIA_ERR_DECODE: 3,
                MEDIA_ERR_NETWORK: 2,
                MEDIA_ERR_SRC_NOT_SUPPORTED: 4 } as MediaError;
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

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).resolves.toBeUndefined();

        expect(revokeSpy).toHaveBeenCalled();
        revokeSpy.mockRestore();
    });

    it('resolves when play() rejects with AbortError', async () => {
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockRejectedValue(new DOMException('interrupted', 'AbortError'));
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

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).resolves.toBeUndefined();

        expect(revokeSpy).toHaveBeenCalled();
        revokeSpy.mockRestore();
    });

    it('resolves when play() fulfills without playing event then error fires', async () => {
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => {
            void Promise.resolve().then(() => {
                queueMicrotask(() => handlers.error?.());
            });
            return Promise.resolve();
        });
        class MockAudio {
            error: MediaError | null = { code: 4, message: 'mock', MEDIA_ERR_ABORTED: 1,
                MEDIA_ERR_DECODE: 3,
                MEDIA_ERR_NETWORK: 2,
                MEDIA_ERR_SRC_NOT_SUPPORTED: 4 } as MediaError;
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).resolves.toBeUndefined();

        expect(revokeSpy).toHaveBeenCalled();
        revokeSpy.mockRestore();
    });

    it('resolves on error when currentTime shows progress without playing or fulfilled play()', async () => {
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => new Promise<void>(() => {}));
        class MockAudio {
            currentTime = 0.05;
            played = { length: 0 } as TimeRanges;
            error: MediaError | null = { code: 4, message: 'mock', MEDIA_ERR_ABORTED: 1,
                MEDIA_ERR_DECODE: 3,
                MEDIA_ERR_NETWORK: 2,
                MEDIA_ERR_SRC_NOT_SUPPORTED: 4 } as MediaError;
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
                queueMicrotask(() => handlers.error?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).resolves.toBeUndefined();

        expect(revokeSpy).toHaveBeenCalled();
        revokeSpy.mockRestore();
    });

    it('rejects when play() rejects with NotAllowedError', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockRejectedValue(new DOMException('not allowed', 'NotAllowedError'));
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toMatchObject({
            name: 'NotAllowedError',
        });
    });

    it('rejects when media element error fires before playing', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockResolvedValue(undefined);
        class MockAudio {
            error: MediaError | null = { code: 4, message: 'mock', MEDIA_ERR_ABORTED: 1,
                MEDIA_ERR_DECODE: 3,
                MEDIA_ERR_NETWORK: 2,
                MEDIA_ERR_SRC_NOT_SUPPORTED: 4 } as MediaError;
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
                queueMicrotask(() => handlers.error?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toThrow(/Audio playback failed/);
    });

    it('ignores duplicate loadeddata/canplay dispatch (load gate)', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockImplementation(() => {
            queueMicrotask(() => handlers.ended?.());
            return Promise.resolve();
        });
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => {
                    handlers.loadeddata?.();
                    handlers.canplay?.();
                });
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await playTtsAudioFromBase64(btoa('ab'), 'audio/wav');

        expect(play).toHaveBeenCalledTimes(1);
    });

    it('rejects when play() rejects with a plain Error', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockRejectedValue(new Error('boom'));
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toThrow('boom');
    });

    it('rejects when play() rejects with a non-Error reason', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockRejectedValue('string-fail');
        class MockAudio {
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toThrow('string-fail');
    });

    it('rejects with generic message when media error has no details', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockResolvedValue(undefined);
        class MockAudio {
            error: MediaError | null = null;
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
                queueMicrotask(() => handlers.error?.());
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toThrow(/^Audio playback failed$/);
    });

    it('ignores duplicate onError after first rejection settles', async () => {
        const handlers: Record<string, () => void> = {};
        const addEventListener = vi.fn((ev: string, fn: () => void) => {
            handlers[ev] = fn;
        });
        const play = vi.fn().mockResolvedValue(undefined);
        class MockAudio {
            error: MediaError | null = null;
            play = play;
            addEventListener = addEventListener;
            removeEventListener = vi.fn();
            pause = vi.fn();
            removeAttribute = vi.fn();
            load = vi.fn().mockImplementation(() => {
                queueMicrotask(() => handlers.loadeddata?.());
                queueMicrotask(() => {
                    handlers.error?.();
                    handlers.error?.();
                });
            });
        }
        vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio);

        await expect(playTtsAudioFromBase64(btoa('ab'), 'audio/wav')).rejects.toThrow(/^Audio playback failed$/);
    });

    it('uses default wav MIME when given empty string', async () => {
        const blob = audioBase64ToBlob(btoa('z'), '');
        expect(blob.type).toBe('audio/wave');
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
