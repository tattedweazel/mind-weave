/**
 * ThemeContext
 * ============
 * Resolves app-wide colors: defaults → active system palette (User.settings.system_palette_id)
 * → optional User.settings.system_colors partials. Injects CSS variables for the design system.
 */

import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useLayoutEffect,
    useState,
    ReactNode,
} from 'react';
import { useAuth } from './AuthContext';
import { ApiClient } from '../api/client';
import {
    DEFAULT_SYSTEM_COLORS_LIGHT,
    DEFAULT_SYSTEM_COLORS_DARK,
    type SystemColorToken,
    type SystemColorsMode,
} from '../theme/defaults';
import { mergeResolvedSystemColors } from '../theme/mergeSystemColors';

export interface SystemColorsStored {
    light?: Partial<SystemColorsMode>;
    dark?: Partial<SystemColorsMode>;
}

const CSS_VAR_PREFIX = '--mw-';

/** When not logged in, `localStorage.theme` wins; otherwise follow OS preference. */
function readUnauthenticatedDark(): boolean {
    const ls = localStorage.getItem('theme');
    if (ls === 'dark') return true;
    if (ls === 'light') return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function toCssVarName(token: SystemColorToken): string {
    return `${CSS_VAR_PREFIX}${token.replace(/_/g, '-')}`;
}

function normalizePresetFromApi(raw: unknown): { light: Partial<SystemColorsMode>; dark: Partial<SystemColorsMode> } {
    if (!raw || typeof raw !== 'object') return { light: {}, dark: {} };
    const o = raw as Record<string, unknown>;
    const light =
        o.light && typeof o.light === 'object' && !Array.isArray(o.light)
            ? (o.light as Record<string, string>)
            : {};
    const dark =
        o.dark && typeof o.dark === 'object' && !Array.isArray(o.dark)
            ? (o.dark as Record<string, string>)
            : {};
    return { light, dark };
}

interface ThemeContextType {
    systemColors: SystemColorsMode;
    isDarkMode: boolean;
    setDarkMode: (dark: boolean) => void;
    getColor: (token: SystemColorToken) => string;
    /** Re-fetch active system palette (same `system_palette_id`) after server-side edits. */
    refreshActiveSystemPalette: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const { user } = useAuth();
    const [activePresetPartials, setActivePresetPartials] = useState<{
        light: Partial<SystemColorsMode>;
        dark: Partial<SystemColorsMode>;
    } | null>(null);
    const [presetLoadVersion, setPresetLoadVersion] = useState(0);

    const [isDarkMode, setIsDarkMode] = useState(() =>
        typeof window !== 'undefined' ? readUnauthenticatedDark() : false,
    );

    /** Logged-in: `user.settings.theme_mode` is authoritative (`light` / `dark` / `system`); missing = `system`. */
    useEffect(() => {
        if (user == null) {
            setIsDarkMode(readUnauthenticatedDark());
            return;
        }
        const raw = user.settings?.theme_mode;
        const mode = raw === 'light' || raw === 'dark' ? raw : 'system';

        const apply = () => {
            let dark: boolean;
            if (mode === 'light') dark = false;
            else if (mode === 'dark') dark = true;
            else dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            setIsDarkMode(dark);
            localStorage.setItem('theme', dark ? 'dark' : 'light');
        };

        apply();
        if (mode !== 'system') {
            return;
        }
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = () => apply();
        mq.addEventListener('change', onChange);
        return () => mq.removeEventListener('change', onChange);
    }, [user, user?.settings?.theme_mode]);

    const paletteId = user?.settings?.system_palette_id;
    useEffect(() => {
        if (typeof paletteId !== 'string' || paletteId.trim() === '') {
            setActivePresetPartials(null);
            return;
        }
        let cancelled = false;
        void (async () => {
            try {
                const p = await ApiClient.getSystemPalette(paletteId);
                if (cancelled) return;
                setActivePresetPartials(normalizePresetFromApi(p.colors));
            } catch {
                if (!cancelled) setActivePresetPartials(null);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [paletteId, presetLoadVersion]);

    const refreshActiveSystemPalette = useCallback(() => {
        setPresetLoadVersion((v) => v + 1);
    }, []);

    const stored = (user?.settings?.system_colors as SystemColorsStored | undefined) ?? {};
    const defaults = isDarkMode ? DEFAULT_SYSTEM_COLORS_DARK : DEFAULT_SYSTEM_COLORS_LIGHT;
    const presetPartial = activePresetPartials
        ? isDarkMode
            ? activePresetPartials.dark
            : activePresetPartials.light
        : undefined;
    const userPartial = isDarkMode ? stored.dark : stored.light;
    const systemColors = mergeResolvedSystemColors(defaults, presetPartial, userPartial);

    /** Immediate UI only; signed-in users should persist via My Settings (`theme_mode`). */
    const setDarkMode = (dark: boolean) => {
        setIsDarkMode(dark);
        document.documentElement.classList.toggle('dark', dark);
        localStorage.setItem('theme', dark ? 'dark' : 'light');
    };

    // Apply dark class before paint to avoid flash of wrong theme
    useLayoutEffect(() => {
        document.documentElement.classList.toggle('dark', isDarkMode);
    }, [isDarkMode]);

    useEffect(() => {
        const root = document.documentElement;
        (Object.keys(systemColors) as SystemColorToken[]).forEach((token) => {
            root.style.setProperty(toCssVarName(token), systemColors[token]);
        });
    }, [systemColors]);

    const getColor = (token: SystemColorToken): string => systemColors[token] ?? '';

    return (
        <ThemeContext.Provider
            value={{ systemColors, isDarkMode, setDarkMode, getColor, refreshActiveSystemPalette }}
        >
            {children}
        </ThemeContext.Provider>
    );
};

export const useTheme = () => {
    const context = useContext(ThemeContext);
    if (context === undefined) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
};
