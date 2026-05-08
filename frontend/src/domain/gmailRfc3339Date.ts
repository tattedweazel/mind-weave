/**
 * Gmail After/Before are stored as RFC3339 instants; the API maps them to Gmail
 * after:/before: YYYY/MM/DD using the UTC calendar day (see backend gmail_query.py).
 * These helpers use Intl + Date only (no date npm packages).
 */

const YMD_FORMATTER_CACHE = new Map<string, Intl.DateTimeFormat>();

function getYmdFormatter(timeZone: string): Intl.DateTimeFormat {
    let fmt = YMD_FORMATTER_CACHE.get(timeZone);
    if (!fmt) {
        fmt = new Intl.DateTimeFormat('en-US', {
            timeZone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hourCycle: 'h23',
        });
        YMD_FORMATTER_CACHE.set(timeZone, fmt);
    }
    return fmt;
}

/** Calendar + wall time (hour/min/sec) for an instant in an IANA zone. */
export function ymdHmsInZone(utcMs: number, timeZone: string): { y: number; m: number; d: number; h: number; mi: number; s: number } {
    const parts = getYmdFormatter(timeZone).formatToParts(new Date(utcMs));
    let y = 0;
    let m = 0;
    let d = 0;
    let h = 0;
    let mi = 0;
    let s = 0;
    for (const p of parts) {
        if (p.type === 'year') {
            y = +p.value;
        } else if (p.type === 'month') {
            m = +p.value;
        } else if (p.type === 'day') {
            d = +p.value;
        } else if (p.type === 'hour') {
            h = +p.value;
        } else if (p.type === 'minute') {
            mi = +p.value;
        } else if (p.type === 'second') {
            s = +p.value;
        }
    }
    return { y, m, d, h, mi, s };
}

function cmpYmd(
    a: { y: number; m: number; d: number },
    b: { y: number; m: number; d: number },
): number {
    if (a.y !== b.y) {
        return a.y - b.y;
    }
    if (a.m !== b.m) {
        return a.m - b.m;
    }
    return a.d - b.d;
}

/**
 * UTC millisecond instant for the first moment of `year-month-day` in `timeZone`
 * (local midnight when it exists).
 */
export function startOfZonedDayUtcMs(year: number, month: number, day: number, timeZone: string): number {
    const target = { y: year, m: month, d: day };

    // Widen bracket so extreme offsets (UTC±14) still contain local midnight for this calendar day.
    let lo = Date.UTC(year, month - 1, day - 3, 12, 0, 0, 0);
    let hi = Date.UTC(year, month - 1, day + 3, 12, 0, 0, 0);

    for (let iter = 0; iter < 64 && lo < hi; iter++) {
        const mid = Math.floor((lo + hi) / 2);
        const { y, m, d } = ymdHmsInZone(mid, timeZone);
        const cmp = cmpYmd({ y, m, d }, target);
        if (cmp < 0) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }

    const { y, m, d } = ymdHmsInZone(lo, timeZone);
    if (y !== year || m !== month || d !== day) {
        throw new RangeError(`No start-of-day for ${year}-${month}-${day} in ${timeZone}`);
    }
    return lo;
}

const DISPLAY_YMD_CACHE = new Map<string, Intl.DateTimeFormat>();

function displayYmdFormatter(timeZone: string): Intl.DateTimeFormat {
    let f = DISPLAY_YMD_CACHE.get(timeZone);
    if (!f) {
        f = new Intl.DateTimeFormat('en-CA', {
            timeZone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        });
        DISPLAY_YMD_CACHE.set(timeZone, f);
    }
    return f;
}

/** yyyy-mm-dd string for an instant when viewed in `timeZone`. */
export function formatYmdInZone(utcMs: number, timeZone: string): string {
    return displayYmdFormatter(timeZone).format(new Date(utcMs));
}

/**
 * Parse RFC3339 / ISO-like strings the same way the Python backend treats naive times: as UTC.
 */
export function parseRfc3339ToUtcMs(iso: string): number | null {
    let t = iso.trim();
    if (!t) {
        return null;
    }
    if (t.endsWith('Z')) {
        // ok
    } else if (/[+-]\d{2}:\d{2}$/.test(t) || /[+-]\d{2}\d{2}$/.test(t)) {
        // offset present
    } else {
        if (!t.includes('T')) {
            t = `${t}T00:00:00`;
        }
        t = `${t}Z`;
    }
    const d = new Date(t);
    if (Number.isNaN(d.getTime())) {
        return null;
    }
    return d.getTime();
}

/**
 * Mirror backend `rfc3339_to_gmail_date`: UTC calendar date as YYYY/MM/DD, or null if invalid.
 */
export function utcCalendarDayFromRfc3339(iso: string): string | null {
    const ms = parseRfc3339ToUtcMs(iso);
    if (ms === null) {
        return null;
    }
    const d = new Date(ms);
    const y = d.getUTCFullYear();
    const m = d.getUTCMonth() + 1;
    const day = d.getUTCDate();
    return `${y}/${String(m).padStart(2, '0')}/${String(day).padStart(2, '0')}`;
}

/** Parse `HH:mm` or `HH:mm:ss` from an HTML time input. */
export function parseHtmlTimeToHms(timeStr: string): { h: number; mi: number; s: number } | null {
    const t = timeStr.trim();
    if (!t) {
        return null;
    }
    const m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(t);
    if (!m) {
        return null;
    }
    const h = +m[1];
    const mi = +m[2];
    const s = m[3] != null ? +m[3] : 0;
    if (h < 0 || h > 23 || mi < 0 || mi > 59 || s < 0 || s > 59) {
        return null;
    }
    return { h, mi, s };
}

/** Validate `yyyy-mm-dd` from an HTML date input. */
export function parseHtmlDateString(dateStr: string): { y: number; m: number; d: number } | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr.trim());
    if (!m) {
        return null;
    }
    const y = +m[1];
    const mo = +m[2];
    const d = +m[3];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) {
        return null;
    }
    const trial = Date.UTC(y, mo - 1, d);
    const back = new Date(trial);
    if (back.getUTCFullYear() !== y || back.getUTCMonth() + 1 !== mo || back.getUTCDate() !== d) {
        return null;
    }
    return { y, m: mo, d };
}

function cmpWallClock(
    a: { y: number; m: number; d: number; h: number; mi: number; s: number },
    b: { y: number; m: number; d: number; h: number; mi: number; s: number },
): number {
    const c = cmpYmd(a, b);
    if (c !== 0) {
        return c;
    }
    if (a.h !== b.h) {
        return a.h - b.h;
    }
    if (a.mi !== b.mi) {
        return a.mi - b.mi;
    }
    return a.s - b.s;
}

/**
 * UTC millisecond instant for a **wall-clock** local Y-M-D H:M:S in `timeZone`, if it exists.
 * Uses monotonic binary search on the UTC line (DST gaps yield `null`; DST fold takes the earlier UTC instant).
 */
export function zonedWallTimeToUtcMs(
    year: number,
    month: number,
    day: number,
    hour: number,
    minute: number,
    second: number,
    timeZone: string,
): number | null {
    const target = { y: year, m: month, d: day, h: hour, mi: minute, s: second };
    let lo = Date.UTC(year, month - 1, day) - 48 * 3600 * 1000;
    let hi = Date.UTC(year, month - 1, day) + 48 * 3600 * 1000;

    while (lo < hi) {
        const mid = Math.floor((lo + hi) / 2);
        const cur = ymdHmsInZone(mid, timeZone);
        if (cmpWallClock(cur, target) < 0) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }

    const at = ymdHmsInZone(lo, timeZone);
    if (at.y !== target.y || at.m !== target.m || at.d !== target.d || at.h !== target.h || at.mi !== target.mi || at.s !== target.s) {
        return null;
    }
    return lo;
}

export function zonedWallTimeToRfc3339Utc(
    year: number,
    month: number,
    day: number,
    hour: number,
    minute: number,
    second: number,
    timeZone: string,
): string | null {
    try {
        const ms = zonedWallTimeToUtcMs(year, month, day, hour, minute, second, timeZone);
        if (ms === null) {
            return null;
        }
        return new Date(ms).toISOString();
    } catch {
        return null;
    }
}

export function startOfZonedDayToRfc3339Utc(dateStr: string, timeZone: string): string | null {
    const parts = parseHtmlDateString(dateStr);
    if (!parts) {
        return null;
    }
    try {
        const ms = startOfZonedDayUtcMs(parts.y, parts.m, parts.d, timeZone);
        return new Date(ms).toISOString();
    } catch {
        return null;
    }
}

const FALLBACK_TIMEZONES = [
    'UTC',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Anchorage',
    'Pacific/Honolulu',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Asia/Tokyo',
    'Asia/Shanghai',
    'Australia/Sydney',
    'Pacific/Auckland',
];

type IntlWithTimeZones = typeof Intl & { supportedValuesOf?: (key: 'timeZone') => string[] };

/** Sorted IANA zones for a `<select>`; uses `Intl.supportedValuesOf` when available. */
export function listIanaTimeZones(): string[] {
    try {
        const intl = Intl as IntlWithTimeZones;
        if (typeof intl.supportedValuesOf === 'function') {
            const tzs = intl.supportedValuesOf('timeZone');
            return [...tzs].sort((a, b) => a.localeCompare(b));
        }
    } catch {
        /* ignore */
    }
    return [...FALLBACK_TIMEZONES];
}

export function getSystemTimeZone(): string {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
        return 'UTC';
    }
}

/**
 * IANA zone for workflow date/time pickers and Calendar Skill Explorer formatting.
 * Profile key `workflow_time_zone`: `"system"` (default) or an explicit IANA string.
 */
export function resolveWorkflowTimeZone(settings: Record<string, unknown> | undefined): string {
    const raw = settings?.workflow_time_zone;
    if (typeof raw !== 'string') {
        return getSystemTimeZone();
    }
    const s = raw.trim();
    if (!s || s.toLowerCase() === 'system') {
        return getSystemTimeZone();
    }
    return s;
}

/**
 * Format a Google Calendar event boundary for UI: `date` (all-day) or `dateTime` (RFC3339).
 * Interprets instants in `timeZone` so explorer output matches the user's workflow time zone.
 */
export function formatCalendarBoundaryForDisplay(value: string, timeZone: string): string {
    const v = value.trim();
    if (!v) {
        return '';
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
        const ms = Date.UTC(Number(v.slice(0, 4)), Number(v.slice(5, 7)) - 1, Number(v.slice(8, 10)), 12, 0, 0);
        return new Intl.DateTimeFormat(undefined, { timeZone, dateStyle: 'medium' }).format(new Date(ms));
    }
    const ms = parseRfc3339ToUtcMs(v);
    if (ms === null) {
        return v;
    }
    return new Intl.DateTimeFormat(undefined, {
        timeZone,
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(ms));
}

/** Join formatted start/end for list rows and modals. */
export function formatCalendarEventRangeForZone(start: string, end: string, timeZone: string): string {
    const a = formatCalendarBoundaryForDisplay(start, timeZone);
    const b = formatCalendarBoundaryForDisplay(end, timeZone);
    if (!a && !b) {
        return '';
    }
    if (!a) {
        return b;
    }
    if (!b) {
        return a;
    }
    return `${a} → ${b}`;
}
