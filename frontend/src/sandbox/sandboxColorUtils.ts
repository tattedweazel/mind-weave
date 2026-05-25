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

function hexRelativeLuminance(hex: string): number {
    const h = hex.replace('#', '');
    const r = parseInt(h.slice(0, 2), 16) / 255;
    const g = parseInt(h.slice(2, 4), 16) / 255;
    const b = parseInt(h.slice(4, 6), 16) / 255;
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Inline styles for a small hex-colored badge chip with readable text. */
export function hexChipStyle(hex: string): { backgroundColor: string; color: string; borderColor: string } {
    const normalized = normalizeHexColor(hex) ?? hex;
    const lum = hexRelativeLuminance(normalized);
    return {
        backgroundColor: normalized,
        color: lum > 0.55 ? '#1e293b' : '#ffffff',
        borderColor: normalized,
    };
}
