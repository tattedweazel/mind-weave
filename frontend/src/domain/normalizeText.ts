/**
 * Best-effort normalization of pasted / noisy text into list or dictionary JSON values.
 * v1: list + dictionary only; other primitive kinds can add normalizeTextAs* later.
 *
 * Timing: list/dictionary use {@link NormalizationTiming.explicit} (button) to avoid
 * fighting partial JSON on every keystroke. Future kinds (e.g. int) may use on_input.
 */

export type NormalizeTextKind = 'list' | 'dictionary';

export type NormalizationTiming = 'explicit' | 'on_input';

export type NormalizeTextSuccess = {
    ok: true;
    value: unknown[] | Record<string, unknown>;
    formatted: string;
};

export type NormalizeTextFailure = { ok: false; error: string };

export type NormalizeTextResult = NormalizeTextSuccess | NormalizeTextFailure;

const BOM = '\uFEFF';

/** Which UX timing applies per kind (for docs and future wiring). */
export function normalizationTimingForKind(kind: NormalizeTextKind): NormalizationTiming {
    if (kind === 'list' || kind === 'dictionary') return 'explicit';
    return 'explicit';
}

function trimBom(s: string): string {
    let t = s.trim();
    if (t.startsWith(BOM)) t = t.slice(1).trim();
    return t;
}

/** Remove markdown code fences and standalone `---` lines. */
export function stripCommonJsonWrappers(raw: string): string {
    let s = trimBom(raw);
    const lines = s.split(/\r?\n/);
    const out: string[] = [];
    let inFence = false;
    for (const line of lines) {
        const t = line.trim();
        if (/^```(?:json)?$/i.test(t)) {
            inFence = !inFence;
            continue;
        }
        if (!inFence && /^---+$/.test(t)) continue;
        out.push(line);
    }
    s = out.join('\n').trim();
    return trimBom(s);
}

/**
 * Extract first top-level JSON array or object slice using bracket depth, respecting strings.
 */
export function extractBalancedJsonSlice(s: string, open: '[' | '{'): string | null {
    const close = open === '[' ? ']' : '}';
    const start = s.indexOf(open);
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escape = false;
    for (let i = start; i < s.length; i++) {
        const c = s[i];
        if (escape) {
            escape = false;
            continue;
        }
        if (inString) {
            if (c === '\\') {
                escape = true;
                continue;
            }
            if (c === '"') inString = false;
            continue;
        }
        if (c === '"') {
            inString = true;
            continue;
        }
        if (c === open) depth++;
        else if (c === close) {
            depth--;
            if (depth === 0) return s.slice(start, i + 1);
        }
    }
    return null;
}

function parseWholeOrExtract(pre: string, kind: 'list' | 'dictionary'): unknown {
    try {
        return JSON.parse(pre) as unknown;
    } catch {
        if (kind === 'list') {
            const slice = extractBalancedJsonSlice(pre, '[');
            if (slice) return JSON.parse(slice) as unknown;
        } else {
            const slice = extractBalancedJsonSlice(pre, '{');
            if (slice) return JSON.parse(slice) as unknown;
        }
        throw new Error('Could not parse JSON');
    }
}

export function normalizeTextAsList(raw: string): NormalizeTextResult {
    try {
        const pre = stripCommonJsonWrappers(raw);
        const parsed = parseWholeOrExtract(pre, 'list');
        if (!Array.isArray(parsed)) {
            return { ok: false, error: 'Expected a JSON array' };
        }
        return {
            ok: true,
            value: parsed,
            formatted: JSON.stringify(parsed, null, 2),
        };
    } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid JSON';
        return { ok: false, error: msg };
    }
}

export function normalizeTextAsDictionary(raw: string): NormalizeTextResult {
    try {
        const pre = stripCommonJsonWrappers(raw);
        const parsed = parseWholeOrExtract(pre, 'dictionary');
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return { ok: false, error: 'Expected a JSON object' };
        }
        return {
            ok: true,
            value: parsed as Record<string, unknown>,
            formatted: JSON.stringify(parsed, null, 2),
        };
    } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid JSON';
        return { ok: false, error: msg };
    }
}

export function normalizeText(raw: string, kind: 'list'): NormalizeTextResult;
export function normalizeText(raw: string, kind: 'dictionary'): NormalizeTextResult;
export function normalizeText(raw: string, kind: NormalizeTextKind): NormalizeTextResult {
    if (kind === 'list') return normalizeTextAsList(raw);
    return normalizeTextAsDictionary(raw);
}
