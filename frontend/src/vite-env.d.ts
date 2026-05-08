/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** When `'false'`, Sandbox nav and routes are hidden (default: enabled). */
    readonly VITE_SANDBOX_ENABLED?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
