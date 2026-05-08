import js from '@eslint/js';
import globals from 'globals';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
    js.configs.recommended,
    ...tseslint.configs.recommended,
    {
        ignores: ['dist/**', 'node_modules/**'],
    },
    {
        files: ['**/*.js'],
        languageOptions: { globals: { ...globals.node } },
    },
    {
        files: ['**/*.{ts,tsx}'],
        ignores: ['vite.config.ts'],
        languageOptions: {
            ecmaVersion: 2022,
            globals: { ...globals.browser },
            parserOptions: {
                ecmaFeatures: { jsx: true },
            },
        },
        plugins: {
            react,
            'react-hooks': reactHooks,
        },
        rules: {
            ...reactHooks.configs.recommended.rules,
            'react/react-in-jsx-scope': 'off',
            /** Existing codebase uses `any` widely; enforce gradually. */
            '@typescript-eslint/no-explicit-any': 'off',
            /** Many effects intentionally depend on a subset of values. */
            'react-hooks/exhaustive-deps': 'off',
            '@typescript-eslint/no-unused-vars': [
                'error',
                { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
            ],
        },
        settings: {
            react: { version: 'detect' },
        },
    },
    {
        files: ['vite.config.ts'],
        languageOptions: {
            ecmaVersion: 2022,
            globals: { ...globals.node },
        },
        rules: {
            '@typescript-eslint/no-unused-vars': [
                'error',
                { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
            ],
        },
    },
);
