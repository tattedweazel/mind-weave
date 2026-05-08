import { describe, it, expect } from 'vitest';
import {
    PALETTE_EXPORT_SCHEMA_VERSION,
    PaletteImportError,
    buildPaletteExportObject,
    parsePaletteImport,
    readPaletteImportFile,
    serializePaletteExport,
    slugifyPaletteExportBasename,
} from './paletteImportExport';
import { normalizeWorkflowPaletteColors, WORKFLOW_PALETTE_COLORS } from './paletteDefaults';

describe('paletteImportExport', () => {
    it('buildPaletteExportObject includes schema_version and explicit per-step colors plus families', () => {
        const doc = buildPaletteExportObject('My Palette', {
            string: '#ff0000',
            primitive: '#abcdef',
        });
        expect(doc.schema_version).toBe(PALETTE_EXPORT_SCHEMA_VERSION);
        expect(doc.name).toBe('My Palette');
        expect(doc.slug).toBeUndefined();
        expect(doc.colors.string).toBe('#ff0000');
        expect(doc.colors.primitive).toBe('#abcdef');
        expect(doc.colors.list).toBe(WORKFLOW_PALETTE_COLORS.list);
    });

    it('buildPaletteExportObject includes slug when provided', () => {
        const doc = buildPaletteExportObject('Default', { string: '#111111' }, 'default');
        expect(doc.slug).toBe('default');
    });

    it('serializePaletteExport is readable JSON', () => {
        const s = serializePaletteExport('N', { boolean: '#00ff00' });
        const parsed = JSON.parse(s) as { schema_version: number; name: string; colors: Record<string, string> };
        expect(parsed.name).toBe('N');
        expect(parsed.colors.boolean).toBe('#00ff00');
    });

    it('parse then normalize after export matches normalized source', () => {
        const source = { string: '#aabbcc', primitive: '#111111' };
        const doc = buildPaletteExportObject('Round', source);
        const imp = parsePaletteImport(doc);
        expect(imp.name).toBe('Round');
        expect(normalizeWorkflowPaletteColors(imp.colors)).toEqual(normalizeWorkflowPaletteColors(source));
    });

    it('parsePaletteImport accepts API-shaped payload', () => {
        const imp = parsePaletteImport({
            id: 'p1',
            user_id: null,
            name: 'API Palette',
            colors: { any: '#010203' },
            created_at: '',
            updated_at: '',
        });
        expect(imp.name).toBe('API Palette');
        expect(imp.colors.any).toBe('#010203');
    });

    it('parsePaletteImport allows omitting schema_version', () => {
        const imp = parsePaletteImport({ name: 'Legacy', colors: {} });
        expect(imp.name).toBe('Legacy');
        expect(imp.colors).toEqual({});
    });

    it('parsePaletteImport treats missing colors as empty', () => {
        const imp = parsePaletteImport({ name: 'NoColors' });
        expect(imp.colors).toEqual({});
    });

    it('parsePaletteImport skips empty string color values', () => {
        const imp = parsePaletteImport({
            name: 'X',
            colors: { a: '#fff', b: '', c: '  #123  ' },
        });
        expect(imp.colors.a).toBe('#fff');
        expect(imp.colors.b).toBeUndefined();
        expect(imp.colors.c).toBe('  #123  ');
    });

    it('parsePaletteImport rejects wrong schema_version', () => {
        expect(() =>
            parsePaletteImport({ schema_version: 99, name: 'x', colors: {} })
        ).toThrowError(PaletteImportError);
    });

    it('parsePaletteImport rejects non-object root', () => {
        expect(() => parsePaletteImport(null)).toThrowError(PaletteImportError);
        expect(() => parsePaletteImport([])).toThrowError(PaletteImportError);
        expect(() => parsePaletteImport('x')).toThrowError(PaletteImportError);
    });

    it('parsePaletteImport rejects empty name', () => {
        expect(() => parsePaletteImport({ name: '', colors: {} })).toThrowError(PaletteImportError);
        expect(() => parsePaletteImport({ name: '   ', colors: {} })).toThrowError(PaletteImportError);
    });

    it('parsePaletteImport rejects invalid name type', () => {
        expect(() => parsePaletteImport({ name: 1, colors: {} })).toThrowError(PaletteImportError);
    });

    it('parsePaletteImport rejects non-object colors', () => {
        expect(() => parsePaletteImport({ name: 'a', colors: [] })).toThrowError(PaletteImportError);
        expect(() => parsePaletteImport({ name: 'a', colors: null })).toThrowError(PaletteImportError);
    });

    it('parsePaletteImport rejects non-string color values', () => {
        expect(() => parsePaletteImport({ name: 'a', colors: { k: 1 } })).toThrowError(PaletteImportError);
    });

    it('slugifyPaletteExportBasename sanitizes name', () => {
        expect(slugifyPaletteExportBasename('Hello World!')).toBe('hello-world');
        expect(slugifyPaletteExportBasename('!!!')).toBe('palette');
        expect(slugifyPaletteExportBasename('  Teal  ')).toBe('teal');
    });

    it('readPaletteImportFile parses valid file', async () => {
        const file = new File(
            [JSON.stringify({ schema_version: 1, name: 'File', colors: { string: '#111111' } })],
            'x.json',
            { type: 'application/json' }
        );
        const r = await readPaletteImportFile(file);
        expect(r.name).toBe('File');
        expect(r.colors.string).toBe('#111111');
    });

    it('readPaletteImportFile rejects invalid JSON', async () => {
        const file = new File(['not json'], 'x.json', { type: 'application/json' });
        await expect(readPaletteImportFile(file)).rejects.toThrowError(PaletteImportError);
    });
});
