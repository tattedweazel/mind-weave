/**
 * Shared fetch + FastAPI error parsing for ApiClient and AuthClient.
 */

export function fetchWithCredentials(url: string, init?: RequestInit): Promise<Response> {
    return fetch(url, { ...init, credentials: 'include' });
}

/** Normalize FastAPI `detail` (string, object with message, or validation issue list) to a single message. */
export function parseFastApiDetail(data: unknown): string | undefined {
    if (!data || typeof data !== 'object' || !('detail' in data)) return undefined;
    const raw = (data as { detail: unknown }).detail;
    if (typeof raw === 'string') return raw;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'message' in raw) {
        const m = (raw as { message: unknown }).message;
        if (typeof m === 'string') return m;
    }
    if (Array.isArray(raw)) {
        const parts = raw.map(item => {
            if (item && typeof item === 'object' && 'msg' in item) {
                return String((item as { msg: unknown }).msg);
            }
            try {
                return JSON.stringify(item);
            } catch {
                return String(item);
            }
        });
        return parts.join('; ');
    }
    if (raw && typeof raw === 'object') {
        try {
            return JSON.stringify(raw);
        } catch {
            return String(raw);
        }
    }
    return undefined;
}

/** When FastAPI returns a JSON object as `detail`, return it (e.g. preflight payloads). */
export function getApiErrorDetailObject(body: unknown): Record<string, unknown> | undefined {
    if (!body || typeof body !== 'object' || !('detail' in body)) return undefined;
    const d = (body as { detail: unknown }).detail;
    if (d && typeof d === 'object' && !Array.isArray(d)) return d as Record<string, unknown>;
    return undefined;
}

export async function readJsonBody(response: Response): Promise<unknown> {
    return response.json().catch(() => null);
}

export function formatApiErrorMessage(status: number, statusText: string, detail?: string): string {
    if (detail) return detail;
    return `API Error ${status}: ${statusText}`;
}

/** Build Error for a non-OK JSON API response (after optional body read). */
export function apiErrorFromResponse(response: Response, body: unknown): Error {
    const detail = parseFastApiDetail(body);
    const err = new Error(formatApiErrorMessage(response.status, response.statusText, detail));
    (err as Error & { apiBody?: unknown }).apiBody = body;
    return err;
}
