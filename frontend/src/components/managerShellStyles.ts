/**
 * Shared list+detail manager styling. Uses Tailwind `mw.*` → CSS variables from ThemeContext
 * so modals match the active system theme (same pattern as PaletteManager).
 */

export const MANAGER_INPUT_CLS =
    'w-full px-3 py-2 border border-mw-border bg-mw-card text-mw-text-primary rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-mw-primary transition-shadow';

export const MANAGER_LABEL_CLS = 'block text-xs font-medium text-mw-text-secondary mb-1';
