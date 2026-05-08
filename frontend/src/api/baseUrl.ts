/**
 * API origin from Vite env (SE-022). Default matches local FastAPI port.
 *
 * Use the server origin only (e.g. http://localhost:8000), not .../api/v1.
 * If someone sets VITE_API_BASE to .../api/v1 by mistake, strip it so paths
 * are not doubled (which breaks OAuth and every route with a 404 JSON body).
 *
 * **Development, no VITE_API_BASE:**
 * - Same host + port 8000 when the SPA hostname is **not** `app.*` (e.g. `localhost`,
 *   `127.0.0.1`, LAN IP → API on that host:8000).
 * - When the SPA is `app.<domain>` (Path C behind nginx), assume the API is
 *   `https://api.<domain>` (no `:8000` — TLS on 443). Override with `VITE_API_BASE`
 *   if your API host does not follow that convention.
 *
 * **Production / `vite preview`:** set `VITE_API_BASE` at build time; when unset,
 * falls back to http://localhost:8000 (unchanged).
 */
function normalizeApiOrigin(raw: string | undefined): string {
    let o = (raw?.trim() || 'http://localhost:8000').replace(/\/+$/, '');
    if (o.endsWith('/api/v1')) {
        o = o.slice(0, -'/api/v1'.length).replace(/\/+$/, '');
    }
    return o;
}

/** Dev-only: infer API origin from the page URL when `VITE_API_BASE` is unset. */
export function resolveDevApiOriginFromLocation(loc: { protocol: string; hostname: string }): string {
    const { protocol, hostname } = loc;
    if (hostname.startsWith('app.')) {
        const rest = hostname.slice('app.'.length);
        const apiHost = `api.${rest}`;
        if (protocol === 'https:') {
            return `https://${apiHost}`;
        }
        return `http://${apiHost}:8000`;
    }
    return `${protocol}//${hostname}:8000`;
}

function resolveApiOrigin(): string {
    const raw = import.meta.env.VITE_API_BASE as string | undefined;
    if (raw != null && raw.trim() !== '') {
        return normalizeApiOrigin(raw);
    }
    if (import.meta.env.DEV && typeof window !== 'undefined') {
        return resolveDevApiOriginFromLocation(window.location);
    }
    return normalizeApiOrigin(undefined);
}

const origin = resolveApiOrigin();

export const API_ORIGIN = origin;
export const API_BASE = `${origin}/api/v1`;
