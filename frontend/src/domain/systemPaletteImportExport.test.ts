import { describe, it, expect } from 'vitest';
import {
    SystemPaletteImportError,
    parseSystemPaletteImport,
    expandSystemThemeColorsForExport,
    SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION,
} from './systemPaletteImportExport';
import { DEFAULT_SYSTEM_COLORS_DARK, DEFAULT_SYSTEM_COLORS_LIGHT } from '../theme/defaults';

describe('systemPaletteImportExport', () => {
    it('parseSystemPaletteImport accepts minimal document', () => {
        const r = parseSystemPaletteImport({
            schema_version: SYSTEM_PALETTE_EXPORT_SCHEMA_VERSION,
            name: 'T',
            colors: { light: { page_bg: '#fff' }, dark: {} },
        });
        expect(r.name).toBe('T');
        expect(r.light.page_bg).toBe('#fff');
        expect(r.dark).toEqual({});
    });

    it('parseSystemPaletteImport rejects bad schema version', () => {
        expect(() =>
            parseSystemPaletteImport({
                schema_version: 999,
                name: 'T',
                colors: {},
            }),
        ).toThrow(SystemPaletteImportError);
    });

    it('expandSystemThemeColorsForExport fills missing tokens from defaults', () => {
        const exp = expandSystemThemeColorsForExport(
            { ...DEFAULT_SYSTEM_COLORS_LIGHT, page_bg: '#custom' },
            DEFAULT_SYSTEM_COLORS_DARK,
        );
        expect(exp.light.page_bg).toBe('#custom');
        expect(exp.dark.page_bg).toBe(DEFAULT_SYSTEM_COLORS_DARK.page_bg);
    });
});
