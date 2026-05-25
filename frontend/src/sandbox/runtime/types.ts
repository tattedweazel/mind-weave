import type { SandboxSandboxStateJson } from '../../domain/sandbox/types';
import type { SandboxItemRenderCatalog } from '../sandboxItemRender';

export interface SandboxSetStateOptions {
    selectedCreatureId?: string | null;
    renderCatalog?: SandboxItemRenderCatalog;
}

/** Renderer + input only; never owns simulation truth (see docs/SANDBOX.md). */
export interface SandboxRuntimeAdapter {
    mount(container: HTMLElement): void;
    destroy(): void;
    setState(state: SandboxSandboxStateJson, options?: SandboxSetStateOptions): void;
    setOnCellClick(handler: (cell: { x: number; y: number }) => void): void;
    fitToView(): void;
    zoomIn(): void;
    zoomOut(): void;
}
