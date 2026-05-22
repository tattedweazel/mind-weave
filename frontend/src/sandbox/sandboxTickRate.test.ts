import { describe, expect, it } from 'vitest';

import { DEFAULT_TICK_RATE_MS } from './sandboxVisualDefaults';
import {
    clampTickRateMs,
    isSandboxStateVersionMismatchError,
    parseTickRateMsInput,
    tickRateMsFromPlayback,
    TICK_RATE_MS_MAX,
    TICK_RATE_MS_MIN,
} from './sandboxTickRate';

describe('sandboxTickRate', () => {
    describe('clampTickRateMs', () => {
        it('clamps to min and max bounds', () => {
            expect(clampTickRateMs(50)).toBe(TICK_RATE_MS_MIN);
            expect(clampTickRateMs(99_999)).toBe(TICK_RATE_MS_MAX);
            expect(clampTickRateMs(1500)).toBe(1500);
        });

        it('rounds and falls back for non-finite values', () => {
            expect(clampTickRateMs(1500.7)).toBe(1501);
            expect(clampTickRateMs(Number.NaN)).toBe(DEFAULT_TICK_RATE_MS);
        });
    });

    describe('parseTickRateMsInput', () => {
        it('returns null for empty or invalid input', () => {
            expect(parseTickRateMsInput('', 1000)).toBeNull();
            expect(parseTickRateMsInput('   ', 1000)).toBeNull();
            expect(parseTickRateMsInput('abc', 1000)).toBeNull();
        });

        it('returns clamped value for valid input', () => {
            expect(parseTickRateMsInput('2000', 1000)).toBe(2000);
            expect(parseTickRateMsInput('2', 1000)).toBe(TICK_RATE_MS_MIN);
        });
    });

    describe('tickRateMsFromPlayback', () => {
        it('reads playback tick_rate_ms when valid', () => {
            expect(tickRateMsFromPlayback({ tick_rate_ms: 2500 })).toBe(2500);
        });

        it('falls back to default when missing or invalid', () => {
            expect(tickRateMsFromPlayback({})).toBe(DEFAULT_TICK_RATE_MS);
            expect(tickRateMsFromPlayback({ tick_rate_ms: Number.NaN })).toBe(DEFAULT_TICK_RATE_MS);
        });
    });

    describe('isSandboxStateVersionMismatchError', () => {
        it('detects state_version mismatch API errors', () => {
            expect(isSandboxStateVersionMismatchError(new Error('state_version mismatch'))).toBe(true);
            expect(isSandboxStateVersionMismatchError(new Error('API Error 409: Conflict'))).toBe(false);
            expect(isSandboxStateVersionMismatchError('nope')).toBe(false);
        });
    });
});
