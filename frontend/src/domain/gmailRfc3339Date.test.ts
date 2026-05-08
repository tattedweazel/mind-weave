import { describe, it, expect } from 'vitest';
import {
    formatCalendarBoundaryForDisplay,
    formatCalendarEventRangeForZone,
    formatYmdInZone,
    parseHtmlTimeToHms,
    parseRfc3339ToUtcMs,
    resolveWorkflowTimeZone,
    startOfZonedDayToRfc3339Utc,
    startOfZonedDayUtcMs,
    utcCalendarDayFromRfc3339,
    ymdHmsInZone,
    zonedWallTimeToRfc3339Utc,
    zonedWallTimeToUtcMs,
} from './gmailRfc3339Date';

describe('utcCalendarDayFromRfc3339', () => {
    it('matches backend rfc3339_to_gmail_date vectors', () => {
        expect(utcCalendarDayFromRfc3339('2026-03-01T00:00:00Z')).toBe('2026/03/01');
        expect(utcCalendarDayFromRfc3339('2026-03-31T23:59:59Z')).toBe('2026/03/31');
        expect(utcCalendarDayFromRfc3339('2026-03-01T12:00:00Z')).toBe('2026/03/01');
    });

    it('treats naive datetimes as UTC like the Python backend', () => {
        expect(utcCalendarDayFromRfc3339('2026-03-01T12:00:00')).toBe('2026/03/01');
    });

    it('returns null for empty or invalid', () => {
        expect(utcCalendarDayFromRfc3339('')).toBeNull();
        expect(utcCalendarDayFromRfc3339('not-a-date')).toBeNull();
    });
});

describe('parseRfc3339ToUtcMs', () => {
    it('parses offset forms', () => {
        const ms = parseRfc3339ToUtcMs('2026-03-01T12:00:00+00:00');
        expect(ms).not.toBeNull();
        expect(utcCalendarDayFromRfc3339('2026-03-01T12:00:00+00:00')).toBe('2026/03/01');
    });
});

describe('resolveWorkflowTimeZone', () => {
    it('returns explicit IANA from settings', () => {
        expect(resolveWorkflowTimeZone({ workflow_time_zone: 'Europe/Paris' })).toBe('Europe/Paris');
    });

    it('uses browser zone for system or missing', () => {
        const a = resolveWorkflowTimeZone({ workflow_time_zone: 'system' });
        const b = resolveWorkflowTimeZone(undefined);
        expect(typeof a).toBe('string');
        expect(a.length).toBeGreaterThan(0);
        expect(typeof b).toBe('string');
        expect(b.length).toBeGreaterThan(0);
    });
});

describe('startOfZonedDayUtcMs', () => {
    it('yields Chicago local midnight for 2026-03-01 and UTC day Gmail expects', () => {
        const ms = startOfZonedDayUtcMs(2026, 3, 1, 'America/Chicago');
        const hms = ymdHmsInZone(ms, 'America/Chicago');
        expect(hms.y).toBe(2026);
        expect(hms.m).toBe(3);
        expect(hms.d).toBe(1);
        expect(hms.h).toBe(0);
        expect(hms.mi).toBe(0);
        expect(hms.s).toBe(0);
        expect(utcCalendarDayFromRfc3339(new Date(ms).toISOString())).toBe('2026/03/01');
    });

    it('round-trips through startOfZonedDayToRfc3339Utc', () => {
        const iso = startOfZonedDayToRfc3339Utc('2026-03-10', 'UTC');
        expect(iso).toBe('2026-03-10T00:00:00.000Z');
        expect(utcCalendarDayFromRfc3339(iso!)).toBe('2026/03/10');
    });
});

describe('formatYmdInZone', () => {
    it('formats instant in zone for date inputs', () => {
        const ms = parseRfc3339ToUtcMs('2026-03-01T12:00:00Z')!;
        expect(formatYmdInZone(ms, 'UTC')).toBe('2026-03-01');
    });
});

describe('parseHtmlTimeToHms', () => {
    it('parses HH:mm and HH:mm:ss', () => {
        expect(parseHtmlTimeToHms('15:30')).toEqual({ h: 15, mi: 30, s: 0 });
        expect(parseHtmlTimeToHms('09:05:07')).toEqual({ h: 9, mi: 5, s: 7 });
    });

    it('returns null for invalid', () => {
        expect(parseHtmlTimeToHms('')).toBeNull();
        expect(parseHtmlTimeToHms('25:00')).toBeNull();
    });
});

describe('zonedWallTimeToUtcMs / zonedWallTimeToRfc3339Utc', () => {
    it('maps Chicago wall time to UTC', () => {
        const ms = zonedWallTimeToUtcMs(2026, 6, 1, 15, 30, 0, 'America/Chicago');
        expect(ms).not.toBeNull();
        const hms = ymdHmsInZone(ms!, 'America/Chicago');
        expect(hms.y).toBe(2026);
        expect(hms.m).toBe(6);
        expect(hms.d).toBe(1);
        expect(hms.h).toBe(15);
        expect(hms.mi).toBe(30);
    });

    it('round-trips to RFC3339 UTC', () => {
        const iso = zonedWallTimeToRfc3339Utc(2026, 3, 10, 9, 15, 0, 'UTC');
        expect(iso).toBe('2026-03-10T09:15:00.000Z');
    });
});

describe('formatCalendarBoundaryForDisplay / formatCalendarEventRangeForZone', () => {
    it('formats dateTime in the given IANA zone', () => {
        const s = formatCalendarBoundaryForDisplay('2026-03-20T21:00:00Z', 'America/Chicago');
        expect(s).toMatch(/2026/);
        expect(s).toMatch(/4:00/);
    });

    it('formats all-day date in zone', () => {
        const s = formatCalendarBoundaryForDisplay('2026-03-20', 'America/New_York');
        expect(s).toMatch(/20/);
        expect(s).toMatch(/2026/);
        expect(s).toMatch(/Mar/);
    });

    it('joins range for explorer subtitle', () => {
        const r = formatCalendarEventRangeForZone('2026-03-20T21:00:00Z', '2026-03-20T23:00:00Z', 'America/Chicago');
        expect(r).toContain('→');
    });
});
