/**
 * Default System Color Tokens
 * ===========================
 * Semantic color tokens for the app-wide design system.
 * Used when no custom system_colors are stored in User.settings.
 *
 * Structure: { light: Record<token, hex>, dark: Record<token, hex> }
 */

export type SystemColorToken =
    | 'page_bg'
    | 'sidebar_bg'
    | 'card_bg'
    | 'card_bg_alt'
    | 'text_primary'
    | 'text_secondary'
    | 'border'
    | 'primary'
    | 'primary_hover'
    | 'primary_muted'
    | 'success'
    | 'success_muted'
    | 'error'
    | 'error_muted';

export type SystemColorsMode = Record<SystemColorToken, string>;

export const DEFAULT_SYSTEM_COLORS_LIGHT: SystemColorsMode = {
    page_bg: '#f9fafb',
    sidebar_bg: '#ffffff',
    card_bg: '#ffffff',
    card_bg_alt: '#f3f4f6',
    text_primary: '#111827',
    text_secondary: '#4b5563',
    border: '#e5e7eb',
    primary: '#2563eb',
    primary_hover: '#1d4ed8',
    primary_muted: '#eff6ff',
    success: '#16a34a',
    success_muted: '#dcfce7',
    error: '#dc2626',
    error_muted: '#fee2e2',
};

export const DEFAULT_SYSTEM_COLORS_DARK: SystemColorsMode = {
    page_bg: '#030712',
    sidebar_bg: '#111827',
    card_bg: '#111827',
    card_bg_alt: '#1f2937',
    text_primary: '#f9fafb',
    text_secondary: '#9ca3af',
    border: '#1f2937',
    primary: '#60a5fa',
    primary_hover: '#93c5fd',
    primary_muted: '#1e293b',
    success: '#4ade80',
    success_muted: '#14532d',
    error: '#f87171',
    error_muted: '#7f1d1d',
};

export const SYSTEM_COLOR_TOKENS: { key: SystemColorToken; label: string }[] = [
    { key: 'page_bg', label: 'Page Background' },
    { key: 'sidebar_bg', label: 'Sidebar Background' },
    { key: 'card_bg', label: 'Card / Modal Background' },
    { key: 'card_bg_alt', label: 'Secondary Panel Background' },
    { key: 'text_primary', label: 'Primary Text' },
    { key: 'text_secondary', label: 'Secondary Text' },
    { key: 'border', label: 'Border' },
    { key: 'primary', label: 'Primary Accent' },
    { key: 'primary_hover', label: 'Primary Hover' },
    { key: 'primary_muted', label: 'Primary Muted (Selected)' },
    { key: 'success', label: 'Success' },
    { key: 'success_muted', label: 'Success Background' },
    { key: 'error', label: 'Error' },
    { key: 'error_muted', label: 'Error Background' },
];
