/**
 * Decode workflow TTS output (base64 WAV) and play or download in the browser.
 */

/** Normalize payload from API or pasted data URLs before `atob`. */
export function normalizeAudioBase64Payload(raw: string): string {
    let s = raw.trim();
    const dataPrefix = /^data:[^;]+;base64,/i;
    if (dataPrefix.test(s)) {
        s = s.replace(dataPrefix, '');
    }
    return s.replace(/\s/g, '');
}

/** Blob MIME for WAV; use `audio/wave` (RFC) — some engines treat it more reliably than `audio/wav`. */
export function normalizeWavBlobType(mimeType: string): string {
    const t = mimeType.trim();
    if (!t || t.toLowerCase() === 'audio/wav') {
        return 'audio/wave';
    }
    return t;
}

export function audioBase64ToBlob(base64: string, mimeType: string): Blob {
    const clean = normalizeAudioBase64Payload(base64);
    let binary: string;
    try {
        binary = atob(clean);
    } catch {
        throw new Error('Invalid base64 audio data');
    }
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    const blobType = normalizeWavBlobType(mimeType || 'audio/wav');
    return new Blob([bytes], { type: blobType });
}

export function createObjectUrlForAudioBase64(base64: string, mimeType: string): string {
    return URL.createObjectURL(audioBase64ToBlob(base64, mimeType));
}

/**
 * Play audio once; revokes the object URL after `ended` or `error`, or if `play()` rejects.
 */
export async function playTtsAudioFromBase64(base64: string, mimeType: string): Promise<void> {
    const blob = audioBase64ToBlob(base64, mimeType);
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);

    const teardown = () => {
        audio.pause();
        audio.removeAttribute('src');
        // Do not call audio.load() here — it can re-dispatch `loadeddata` and break tests or loop.
        URL.revokeObjectURL(url);
    };

    await new Promise<void>((resolve, reject) => {
        let playStarted = false;
        const onEnded = () => {
            audio.removeEventListener('ended', onEnded);
            audio.removeEventListener('error', onError);
            teardown();
            resolve();
        };
        const onError = () => {
            audio.removeEventListener('ended', onEnded);
            audio.removeEventListener('error', onError);
            audio.removeEventListener('loadeddata', onLoaded);
            audio.removeEventListener('canplay', onLoaded);
            teardown();
            const code = audio.error?.code;
            const msg = audio.error?.message;
            reject(
                new Error(
                    `Audio playback failed${code != null ? ` (MEDIA_ERR ${code})` : ''}${msg ? `: ${msg}` : ''}`,
                ),
            );
        };
        const onLoaded = () => {
            if (playStarted) {
                return;
            }
            playStarted = true;
            audio.removeEventListener('loadeddata', onLoaded);
            audio.removeEventListener('canplay', onLoaded);
            void audio.play().catch((err: unknown) => {
                audio.removeEventListener('ended', onEnded);
                audio.removeEventListener('error', onError);
                teardown();
                reject(err instanceof Error ? err : new Error(String(err)));
            });
        };
        audio.addEventListener('ended', onEnded);
        audio.addEventListener('error', onError);
        // WebKit often fires `canplay` when `loadeddata` is skipped for short clips.
        audio.addEventListener('loadeddata', onLoaded);
        audio.addEventListener('canplay', onLoaded);
        audio.load();
    });
}

export function downloadAudioBase64(base64: string, mimeType: string, filename: string): void {
    const blob = audioBase64ToBlob(base64, mimeType);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}
