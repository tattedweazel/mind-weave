/**
 * TTS node outputs streamed live include WAV base64; persisted run logs redact `audio_base64`
 * to `[redacted]`. The events tail may re-emit persisted `node.completed` rows after the live
 * payload — helpers here detect playable vs redacted audio and merge duplicates safely.
 */

import type { NodeRunResult } from '../api/types';

export const TTS_AUDIO_BASE64_REDACTED = '[redacted]' as const;

export function isPlayableTtsAudioOutput(output: unknown): boolean {
    if (output == null || typeof output !== 'object') {
        return false;
    }
    const o = output as { kind?: unknown; audio_base64?: unknown };
    if (o.kind !== 'audio' || typeof o.audio_base64 !== 'string') {
        return false;
    }
    const b64 = o.audio_base64.trim();
    return b64.length > 0 && b64 !== TTS_AUDIO_BASE64_REDACTED;
}

/** Persisted replay: same shape as live but bytes replaced for at-rest storage. */
export function isRedactedTtsAudioOutput(output: unknown): boolean {
    if (output == null || typeof output !== 'object') {
        return false;
    }
    const o = output as { kind?: unknown; audio_base64?: unknown };
    return o.kind === 'audio' && o.audio_base64 === TTS_AUDIO_BASE64_REDACTED;
}

/**
 * Merge an incoming `node_end` into the per-node last-run map entry.
 * Same `(step_number)` + redacted replay after live playable audio keeps the live row.
 */
export function mergeLastRunNodeResult(prev: NodeRunResult | undefined, incoming: NodeRunResult): NodeRunResult {
    if (prev == null) {
        return incoming;
    }
    const prevSn = prev.step_number ?? 0;
    const incSn = incoming.step_number ?? 0;
    if (incSn < prevSn) {
        return prev;
    }
    if (incSn > prevSn) {
        return incoming;
    }
    if (isPlayableTtsAudioOutput(prev.output) && isRedactedTtsAudioOutput(incoming.output)) {
        return prev;
    }
    return incoming;
}
