/**
 * When Text-to-Speech playback runs during workflow Build runs (SSE `GET …/workflow-runs/…/events`).
 */
export type TtsPlaybackWhen = 'inline' | 'manual' | 'after_workflow';

const VALID_PLAYBACK: ReadonlySet<string> = new Set(['inline', 'manual', 'after_workflow']);

function parsePlaybackWhen(raw: unknown): TtsPlaybackWhen | null {
    if (raw === undefined || raw === null) return null;
    if (typeof raw !== 'string') return null;
    return VALID_PLAYBACK.has(raw) ? (raw as TtsPlaybackWhen) : null;
}

/**
 * User default for TTS playback timing (My Settings), with legacy boolean support.
 */
function userDefaultPlaybackWhen(settings: Record<string, unknown> | undefined): TtsPlaybackWhen {
    if (!settings || typeof settings !== 'object') return 'inline';
    const fromEnum = parsePlaybackWhen(settings.tts_playback_when);
    if (fromEnum) return fromEnum;
    const raw = settings.auto_play_tts_on_node_end;
    if (raw === undefined || raw === null) return 'inline';
    if (typeof raw !== 'boolean') return 'inline';
    return raw ? 'inline' : 'manual';
}

/**
 * Resolved playback timing for a TTS node during a Build SSE run.
 * Per-node `tts_playback_when` or legacy `auto_play_tts_on_node_end` overrides user default.
 */
export function resolveTtsPlaybackWhen(
    userSettings: Record<string, unknown> | undefined,
    nodeData: Record<string, unknown> | undefined,
): TtsPlaybackWhen {
    if (!nodeData || typeof nodeData !== 'object') {
        return userDefaultPlaybackWhen(userSettings);
    }
    const nodeEnum = parsePlaybackWhen(nodeData.tts_playback_when);
    if (nodeEnum) return nodeEnum;
    const rawBool = nodeData.auto_play_tts_on_node_end;
    if (rawBool === true) return 'inline';
    if (rawBool === false) return 'manual';
    return userDefaultPlaybackWhen(userSettings);
}

/**
 * View setting legacy helper: True only when default timing is inline (matches backend name).
 * Prefer {@link resolveTtsPlaybackWhen} for the full model.
 */
export function resolveAutoPlayTtsOnNodeEnd(settings: Record<string, unknown> | undefined): boolean {
    return userDefaultPlaybackWhen(settings) === 'inline';
}

/**
 * Per-node legacy helper: True when this node should play inline on node_end (not manual, not after_workflow).
 */
export function resolveAutoPlayTtsForNode(
    userSettings: Record<string, unknown> | undefined,
    nodeData: Record<string, unknown> | undefined,
): boolean {
    return resolveTtsPlaybackWhen(userSettings, nodeData) === 'inline';
}
