import { DEFAULT_TICK_RATE_MS } from './sandboxVisualDefaults';

export const TICK_RATE_MS_MIN = 200;
export const TICK_RATE_MS_MAX = 60_000;

export function clampTickRateMs(value: number): number {
    if (!Number.isFinite(value)) {
        return DEFAULT_TICK_RATE_MS;
    }
    return Math.min(TICK_RATE_MS_MAX, Math.max(TICK_RATE_MS_MIN, Math.round(value)));
}

export function parseTickRateMsInput(raw: string, fallback: number): number | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) return null;
    return clampTickRateMs(parsed);
}

export function tickRateMsFromPlayback(playback?: { tick_rate_ms?: number }): number {
    const raw = playback?.tick_rate_ms;
    if (typeof raw === 'number' && Number.isFinite(raw)) {
        return clampTickRateMs(raw);
    }
    return DEFAULT_TICK_RATE_MS;
}

export function isSandboxStateVersionMismatchError(error: unknown): boolean {
    if (!(error instanceof Error)) return false;
    const msg = error.message.toLowerCase();
    return msg.includes('state_version') && msg.includes('mismatch');
}
