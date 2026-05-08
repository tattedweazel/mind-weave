import { describe, expect, it } from 'vitest';
import { formatApiErrorMessage, parseFastApiDetail } from './http';

describe('parseFastApiDetail', () => {
    it('returns string detail', () => {
        expect(parseFastApiDetail({ detail: 'use_google_login' })).toBe('use_google_login');
    });

    it('joins validation list messages', () => {
        expect(
            parseFastApiDetail({
                detail: [
                    { msg: 'field required', type: 'missing' },
                    { msg: 'too short', type: 'value_error' },
                ],
            }),
        ).toBe('field required; too short');
    });

    it('returns undefined when no detail', () => {
        expect(parseFastApiDetail({})).toBeUndefined();
        expect(parseFastApiDetail(null)).toBeUndefined();
    });
});

describe('formatApiErrorMessage', () => {
    it('prefers detail over status', () => {
        expect(formatApiErrorMessage(400, 'Bad Request', 'not allowed')).toBe('not allowed');
    });

    it('falls back to status line', () => {
        expect(formatApiErrorMessage(500, 'Internal Server Error')).toBe('API Error 500: Internal Server Error');
    });
});
