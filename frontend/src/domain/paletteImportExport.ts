/**
 * Workflow palette JSON import/export (Editor tab).
 * Shape aligns with PaletteCreate / API list payloads; see frontend README.
 */

import { expandWorkflowPaletteColorsForExport } from './paletteDefaults';

export const PALETTE_EXPORT_SCHEMA_VERSION = 1 as const;

export class PaletteImportError extends Error {
    override readonly name = 'PaletteImportError';
    constructor(message: string) {
        super(message);
    }
}

export type PaletteExportDocument = {
    schema_version: typeof PALETTE_EXPORT_SCHEMA_VERSION;
    name: string;
    colors: Record<string, string>;
    /** Present for built-in system presets; omitted for user palettes. */
    slug?: string;
};

export function buildPaletteExportObject(
    name: string,
    colors: Record<string, string>,
    slug?: string | null,
): PaletteExportDocument {
    const trimmed = name.trim();
    const doc: PaletteExportDocument = {
        schema_version: PALETTE_EXPORT_SCHEMA_VERSION,
        name: trimmed,
        colors: expandWorkflowPaletteColorsForExport(colors),
    };
    if (slug != null && slug !== '') {
        doc.slug = slug;
    }
    return doc;
}

export function serializePaletteExport(
    name: string,
    colors: Record<string, string>,
    slug?: string | null,
): string {
    return JSON.stringify(buildPaletteExportObject(name, colors, slug), null, 2);
}

/** Safe filename segment for downloads (no path separators). */
export function slugifyPaletteExportBasename(name: string): string {
    const s = name
        .trim()
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    return s || 'palette';
}

export type PaletteImportResult = { name: string; colors: Record<string, string> };

function normalizeImportColors(raw: unknown): Record<string, string> {
    if (raw === undefined) return {};
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
        throw new PaletteImportError('Invalid colors: expected an object.');
    }
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
        if (v === undefined || v === null || v === '') continue;
        if (typeof v !== 'string') {
            throw new PaletteImportError(`Invalid colors: value for "${k}" must be a string.`);
        }
        out[k] = v;
    }
    return out;
}

/**
 * Validate a parsed JSON value. Accepts API-shaped rows (extra keys ignored).
 * Does not normalize colors; callers should run normalizeWorkflowPaletteColors before save.
 */
export function parsePaletteImport(raw: unknown): PaletteImportResult {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
        throw new PaletteImportError('Invalid JSON: expected an object.');
    }
    const obj = raw as Record<string, unknown>;

    const ver = obj.schema_version;
    if (ver !== undefined && ver !== PALETTE_EXPORT_SCHEMA_VERSION) {
        throw new PaletteImportError(
            `Unsupported palette export schema_version: ${String(ver)} (expected ${PALETTE_EXPORT_SCHEMA_VERSION}).`
        );
    }

    const nameRaw = obj.name;
    if (typeof nameRaw !== 'string' || !nameRaw.trim()) {
        throw new PaletteImportError('Invalid palette: name is required.');
    }

    const colors = normalizeImportColors(obj.colors);

    return { name: nameRaw.trim(), colors };
}

export function readPaletteImportFile(file: File): Promise<PaletteImportResult> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const text = typeof reader.result === 'string' ? reader.result : '';
                let raw: unknown;
                try {
                    raw = JSON.parse(text) as unknown;
                } catch {
                    throw new PaletteImportError('Invalid JSON file.');
                }
                resolve(parsePaletteImport(raw));
            } catch (e) {
                reject(e instanceof Error ? e : new Error(String(e)));
            }
        };
        reader.onerror = () => reject(new Error('Failed to read file.'));
        reader.readAsText(file);
    });
}
