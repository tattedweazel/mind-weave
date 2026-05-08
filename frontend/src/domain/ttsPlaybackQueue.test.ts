import { describe, it, expect } from 'vitest';
import { sortTtsQueuedClips, type TtsQueuedClip } from './ttsPlaybackQueue';

describe('sortTtsQueuedClips', () => {
    it('orders by step_number then node_id', () => {
        const a: TtsQueuedClip = {
            node_id: 'b',
            step_number: 2,
            audio_base64: 'YQ==',
            mime_type: 'audio/wav',
        };
        const b: TtsQueuedClip = {
            node_id: 'a',
            step_number: 2,
            audio_base64: 'Yg==',
            mime_type: 'audio/wav',
        };
        const c: TtsQueuedClip = {
            node_id: 'z',
            step_number: 1,
            audio_base64: 'Yw==',
            mime_type: 'audio/wav',
        };
        const out = sortTtsQueuedClips([a, b, c]);
        expect(out.map(x => x.node_id)).toEqual(['z', 'a', 'b']);
    });
});
