import { DEFAULT_REGION_COLOR, normalizeHexColor } from './sandboxColorUtils';

export const MAX_SANDBOX_FAVORITE_COLORS = 16;

export function parseSandboxFavoriteColors(settings: Record<string, unknown> | undefined): string[] {
    const raw = settings?.sandbox_favorite_colors;
    if (!Array.isArray(raw)) {
        return [];
    }
    const out: string[] = [];
    const seen = new Set<string>();
    for (const item of raw) {
        if (typeof item !== 'string') {
            continue;
        }
        const normalized = normalizeHexColor(item);
        if (normalized && !seen.has(normalized)) {
            seen.add(normalized);
            out.push(normalized);
            if (out.length >= MAX_SANDBOX_FAVORITE_COLORS) {
                break;
            }
        }
    }
    return out;
}

export function defaultRegionPlacementColor(favorites: string[]): string {
    return favorites[0] ?? DEFAULT_REGION_COLOR;
}
