/**
 * List ordering for system theme presets (Manage Palettes → System tab).
 * Aligns built-in default slug/name with backend `system_palette_defaults.py`.
 */

export const DEFAULT_BUILTIN_SYSTEM_THEME_NAME = 'Default';
export const DEFAULT_BUILTIN_SYSTEM_THEME_SLUG = 'default';

export type SystemPaletteListEntry = {
    name: string;
    user_id: string | null;
    slug?: string | null;
};

export function isBuiltinDefaultSystemTheme(p: SystemPaletteListEntry): boolean {
    return (
        p.user_id == null &&
        (p.slug === DEFAULT_BUILTIN_SYSTEM_THEME_SLUG ||
            (p.slug == null && p.name === DEFAULT_BUILTIN_SYSTEM_THEME_NAME))
    );
}

/** System presets first (Default, then A–Z), then user themes A–Z. */
export function sortSystemPalettesForDisplay<T extends SystemPaletteListEntry>(palettes: readonly T[]): T[] {
    const system = palettes.filter(p => p.user_id == null);
    const userOwned = palettes.filter(p => p.user_id != null);
    const defaultNamed = system.filter(isBuiltinDefaultSystemTheme);
    const systemRest = system
        .filter(p => !isBuiltinDefaultSystemTheme(p))
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name));
    userOwned.sort((a, b) => a.name.localeCompare(b.name));
    return [...defaultNamed, ...systemRest, ...userOwned];
}
