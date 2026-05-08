/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

/**
 * When nginx proxies `https://app…` to Vite, the `Host` header is your public hostname.
 * Vite blocks that unless it appears in `server.allowedHosts`.
 *
 * Set `DEV_ALLOWED_HOSTS=app.example.com` and/or `DEV_HMR_HOST=app.example.com` in `frontend/.env`
 * (see docs/DEPLOYMENT_AND_NETWORK.md). `DEV_ALLOW_ANY_HOST=true` allows any host (dev only).
 *
 * Note: `frontend/.env` is not on `process.env` during config evaluation — we use `loadEnv`.
 */
function devServerForHttpsProxy(env: Record<string, string>) {
    if (env.DEV_ALLOW_ANY_HOST === 'true' || env.DEV_ALLOW_ANY_HOST === '1') {
        return { allowedHosts: true as const };
    }
    const fromList = (env.DEV_ALLOWED_HOSTS ?? '')
        .split(',')
        .map((h) => h.trim())
        .filter(Boolean);
    const hmrHost = env.DEV_HMR_HOST?.trim();
    const merged = [...fromList, ...(hmrHost ? [hmrHost] : [])];
    const hosts: string[] = [];
    for (const h of merged) {
        if (h && !hosts.includes(h)) hosts.push(h);
    }
    if (hosts.length === 0) {
        return {};
    }
    return {
        allowedHosts: hosts,
        ...(hmrHost
            ? {
                  hmr: {
                      protocol: 'wss' as const,
                      host: hmrHost,
                      clientPort: 443,
                  },
              }
            : {}),
    };
}

function manualChunks(id: string): string | undefined {
    if (!id.includes('/node_modules/')) {
        return undefined;
    }
    if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/')) {
        return 'react-vendor';
    }
    if (id.includes('/node_modules/@xyflow/react/')) {
        return 'xyflow';
    }
    if (
        id.includes('/node_modules/react-markdown/') ||
        id.includes('/node_modules/remark-gfm/') ||
        id.includes('/node_modules/remark-math/') ||
        id.includes('/node_modules/rehype-katex/')
    ) {
        return 'markdown';
    }
    if (id.includes('/node_modules/phaser/')) {
        return 'phaser';
    }
    return undefined;
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // Empty prefix loads all keys from `.env`, `.env.local`, `.env.[mode]`, etc.
    const env = loadEnv(mode, process.cwd(), '');
    return {
        plugins: [react()],
        server: {
            host: '127.0.0.1',
            ...devServerForHttpsProxy(env),
        },
        optimizeDeps: {
            include: [
                'react',
                'react-dom',
                'lucide-react',
                'react-markdown',
                'remark-gfm',
                'remark-math',
                'rehype-katex',
                '@xyflow/react',
                'phaser',
                'mermaid',
                'katex',
            ],
        },
        build: {
            rollupOptions: {
                output: {
                    manualChunks,
                },
            },
        },
        test: {
            environment: 'jsdom',
            setupFiles: ['./src/test/setup.ts'],
            globals: true,
            coverage: {
                provider: 'v8',
                reporter: ['text', 'lcov'],
                include: ['src/**/*.{ts,tsx}'],
                exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/**/*.d.ts'],
                // No global % threshold: see docs/Audits/TEST_AUDIT.md (behavior ↔ tests, not line %).
                // Use `npm run test:cov` for reports during release review.
            },
        },
    };
});
