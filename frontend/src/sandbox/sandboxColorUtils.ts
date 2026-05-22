/** Hex color normalization for Sandbox regions (mirrors backend normalize_hex_color). */

const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

export const DEFAULT_REGION_COLOR = '#3B82F6';

export function normalizeHexColor(raw: string): string | null {
    const s = raw.trim();
    if (!s.startsWith('#')) {
        return null;
    }
    let hex = s;
    if (hex.length === 4) {
        const r = hex[1];
        const g = hex[2];
        const b = hex[3];
        hex = `#${r}${r}${g}${g}${b}${b}`;
    }
    if (!HEX_COLOR_RE.test(hex)) {
        return null;
    }
    return hex.toUpperCase();
}

export function isValidHexColor(raw: string): boolean {
    return normalizeHexColor(raw) != null;
}
