import { describe, it, expect } from 'vitest';
import {
    DEFAULT_SYSTEM_COLORS_LIGHT,
    DEFAULT_SYSTEM_COLORS_DARK,
    SYSTEM_COLOR_TOKENS,
    type SystemColorToken,
} from './defaults';

describe('theme/defaults', () => {
    it('DEFAULT_SYSTEM_COLORS_LIGHT has all tokens with hex values', () => {
        const tokens: SystemColorToken[] = [
            'page_bg', 'sidebar_bg', 'card_bg', 'card_bg_alt',
            'text_primary', 'text_secondary', 'border',
            'primary', 'primary_hover', 'primary_muted',
            'success', 'success_muted', 'error', 'error_muted',
        ];
        for (const token of tokens) {
            expect(DEFAULT_SYSTEM_COLORS_LIGHT[token]).toBeDefined();
            expect(DEFAULT_SYSTEM_COLORS_LIGHT[token]).toMatch(/^#[0-9a-fA-F]{6}$/);
        }
    });

    it('DEFAULT_SYSTEM_COLORS_DARK has all tokens', () => {
        const tokens = Object.keys(DEFAULT_SYSTEM_COLORS_LIGHT) as SystemColorToken[];
        for (const token of tokens) {
            expect(DEFAULT_SYSTEM_COLORS_DARK[token]).toBeDefined();
        }
    });

    it('SYSTEM_COLOR_TOKENS includes all expected keys', () => {
        const keys = SYSTEM_COLOR_TOKENS.map(t => t.key);
        expect(keys).toContain('page_bg');
        expect(keys).toContain('primary');
        expect(keys).toContain('error');
        expect(keys).toContain('primary_muted');
    });
});
