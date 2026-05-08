/**
 * System theme palette JSON import/export (Manage Palettes → System tab).
 */

import type { SystemColorsMode } from '../theme/defaults';
import { DEFAULT_SYSTEM_COLORS_DARK, DEFAULT_SYSTEM_COLORS_LIGHT } from '../theme/defaults';

export const SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION = 1 as const;

export class SystemPaletteImportError extends Error {
    override readonly name = 'SystemPaletteImportError';
    constructor(message: string) {
        super(message);
    }
}

export type SystemPaletteExportDocument = {
    schema_version: typeof SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION;
    name: string;
    colors: { light: SystemColorsMode; dark: SystemColorsMode };
    /** Present for built-in themes; ignored on import for creates. */
    slug?: string;
};

function normalizeModeMap(raw: unknown, mode: 'light' | 'dark'): Record<string, string> {
    if (raw === undefined) return {};
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
        throw new SystemPaletteImportError(`Invalid colors.${mode}: expected an object.`);
    }
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
        if (v === undefined || v === null || v === '') continue;
        if (typeof v !== 'string') {
            throw new SystemPaletteImportError(`Invalid colors.${mode}: value for "${k}" must be a string.`);
        }
        out[k] = v;
    }
    return out;
}

export function expandSystemThemeColorsForExport(light: SystemColorsMode, dark: SystemColorsMode): {
    light: SystemColorsMode;
    dark: SystemColorsMode;
} {
    return {
        light: { ...DEFAULT_SYSTEM_COLORS_LIGHT, ...light },
        dark: { ...DEFAULT_SYSTEM_COLORS_DARK, ...dark },
    };
}

export function buildSystemPaletteExportObject(
    name: string,
    light: SystemColorsMode,
    dark: SystemColorsMode,
    slug?: string | null,
): SystemPaletteExportDocument {
    const trimmed = name.trim();
    const expanded = expandSystemThemeColorsForExport(light, dark);
    const doc: SystemPaletteExportDocument = {
        schema_version: SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION,
        name: trimmed,
        colors: expanded,
    };
    if (slug != null && slug !== '') {
        doc.slug = slug;
    }
    return doc;
}

export function serializeSystemPaletteExport(
    name: string,
    light: SystemColorsMode,
    dark: SystemColorsMode,
    slug?: string | null,
): string {
    return JSON.stringify(buildSystemPaletteExportObject(name, light, dark, slug), null, 2);
}

export function slugifySystemPaletteExportBasename(name: string): string {
    const s = name
        .trim()
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    return s || 'system-theme';
}

export type SystemPaletteImportResult = { name: string; light: Record<string, string>; dark: Record<string, string> };

export function parseSystemPaletteImport(raw: unknown): SystemPaletteImportResult {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
        throw new SystemPaletteImportError('Invalid JSON: expected an object.');
    }
    const obj = raw as Record<string, unknown>;

    const ver = obj.schema_version;
    if (ver !== undefined && ver !== SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION) {
        throw new SystemPaletteImportError(
            `Unsupported system theme export schema_version: ${String(ver)} (expected ${SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION}).`,
        );
    }

    const nameRaw = obj.name;
    if (typeof nameRaw !== 'string' || !nameRaw.trim()) {
        throw new SystemPaletteImportError('Invalid theme: name is required.');
    }

    const colorsRaw = obj.colors;
    if (colorsRaw !== undefined && (typeof colorsRaw !== 'object' || colorsRaw === null || Array.isArray(colorsRaw))) {
        throw new SystemPaletteImportError('Invalid theme: colors must be an object.');
    }
    const cr = (colorsRaw ?? {}) as Record<string, unknown>;
    const light = normalizeModeMap(cr.light, 'light');
    const dark = normalizeModeMap(cr.dark, 'dark');

    return { name: nameRaw.trim(), light, dark };
}

export function readSystemPaletteImportFile(file: File): Promise<SystemPaletteImportResult> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const text = typeof reader.result === 'string' ? reader.result : '';
                let raw: unknown;
                try {
                    raw = JSON.parse(text) as unknown;
                } catch {
                    throw new SystemPaletteImportError('Invalid JSON file.');
                }
                resolve(parseSystemPaletteImport(raw));
            } catch (e) {
                reject(e instanceof Error ? e : new Error(String(e)));
            }
        };
        reader.onerror = () => reject(new Error('Failed to read file.'));
        reader.readAsText(file);
    });
}
