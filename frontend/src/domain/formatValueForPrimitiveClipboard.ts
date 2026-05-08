/**
 * Paste-ready text for Output explorer row Copy (primitives + JSON for structured values).
 */

/** Full list or dictionary value for pasting into List / Dictionary primitive JSON fields. */
export function formatListOrDictionaryForClipboard(data: unknown, kind: 'list' | 'dictionary'): string {
    if (kind === 'list') {
        if (!Array.isArray(data)) {
            return '[]';
        }
    } else if (data === null || typeof data !== 'object' || Array.isArray(data)) {
        return '{}';
    }
    try {
        return JSON.stringify(data, null, 2);
    } catch {
        return kind === 'list' ? '[]' : '{}';
    }
}

export function formatValueForPrimitiveClipboard(value: unknown, inferredPrimitive: string | undefined): string {
    const k = (inferredPrimitive ?? '').toLowerCase();
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value === 'string') {
        return value;
    }
    if (typeof value === 'boolean') {
        return JSON.stringify(value);
    }
    if (typeof value === 'number') {
        return Number.isFinite(value) ? String(value) : JSON.stringify(value);
    }
    if (k === 'string' && typeof value !== 'object') {
        return String(value);
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
}
