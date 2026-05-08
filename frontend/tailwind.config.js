import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        mw: {
          page: 'var(--mw-page-bg, #f9fafb)',
          sidebar: 'var(--mw-sidebar-bg, #ffffff)',
          card: 'var(--mw-card-bg, #ffffff)',
          'card-alt': 'var(--mw-card-bg-alt, #f3f4f6)',
          'text-primary': 'var(--mw-text-primary, #111827)',
          'text-secondary': 'var(--mw-text-secondary, #4b5563)',
          border: 'var(--mw-border, #e5e7eb)',
          primary: 'var(--mw-primary, #2563eb)',
          'primary-hover': 'var(--mw-primary-hover, #1d4ed8)',
          'primary-muted': 'var(--mw-primary-muted, #eff6ff)',
          success: 'var(--mw-success, #16a34a)',
          'success-muted': 'var(--mw-success-muted, #dcfce7)',
          error: 'var(--mw-error, #dc2626)',
          'error-muted': 'var(--mw-error-muted, #fee2e2)',
        },
      },
    },
  },
  plugins: [typography],
}
