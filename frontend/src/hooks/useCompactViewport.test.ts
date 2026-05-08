import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { COMPACT_VIEWPORT_MEDIA_QUERY, useCompactViewport } from './useCompactViewport';

describe('COMPACT_VIEWPORT_MEDIA_QUERY', () => {
    it('matches Tailwind lg breakpoint (below 1024px)', () => {
        expect(COMPACT_VIEWPORT_MEDIA_QUERY).toBe('(max-width: 1023px)');
    });
});

describe('useCompactViewport', () => {
    beforeEach(() => {
        vi.stubGlobal('matchMedia', vi.fn());
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('returns false when matchMedia reports not compact', () => {
        vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
            media: query,
            matches: false,
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList);

        const { result } = renderHook(() => useCompactViewport());
        expect(result.current).toBe(false);
    });

    it('returns true when matchMedia reports compact', () => {
        vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
            media: query,
            matches: true,
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList);

        const { result } = renderHook(() => useCompactViewport());
        expect(result.current).toBe(true);
    });

    it('updates when media query change fires', () => {
        let changeHandler: ((e: MediaQueryListEvent) => void) | null = null;
        const mql = {
            media: COMPACT_VIEWPORT_MEDIA_QUERY,
            matches: false,
            addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => {
                changeHandler = cb;
            },
            removeEventListener: vi.fn(),
        };
        vi.mocked(window.matchMedia).mockReturnValue(mql as unknown as MediaQueryList);

        const { result } = renderHook(() => useCompactViewport());
        expect(result.current).toBe(false);

        mql.matches = true;
        act(() => {
            changeHandler?.({ matches: true } as MediaQueryListEvent);
        });
        expect(result.current).toBe(true);
    });
});
