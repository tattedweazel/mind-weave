/** One TTS clip waiting for end-of-workflow sequential playback (run_stream UX). */
export interface TtsQueuedClip {
    audio_base64: string;
    mime_type: string;
    step_number: number;
    node_id: string;
}

/**
 * Order by execution order (`step_number`), then stable tie-break (`node_id`).
 */
export function sortTtsQueuedClips(clips: TtsQueuedClip[]): TtsQueuedClip[] {
    return [...clips].sort((a, b) => {
        const sn = (a.step_number ?? 0) - (b.step_number ?? 0);
        if (sn !== 0) return sn;
        return a.node_id.localeCompare(b.node_id);
    });
}
