import type { SandboxSandboxStateJson } from '../../domain/sandbox/types';

/** Renderer + input only; never owns simulation truth (see docs/SANDBOX.md). */
export interface SandboxRuntimeAdapter {
    mount(container: HTMLElement): void;
    destroy(): void;
    setState(state: SandboxSandboxStateJson): void;
    setOnCellClick(handler: (cell: { x: number; y: number }) => void): void;
}
