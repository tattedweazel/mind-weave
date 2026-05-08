/** JSON shapes returned by `/api/v1/sandbox/*` (mirror backend `SandboxDocumentEnvelope`). */

export interface SandboxGridCellJson {
    x: number;
    y: number;
}

export interface SandboxItemJson {
    id: string;
    type: string;
    position: SandboxGridCellJson;
    energy?: number;
}

export interface SandboxPetJson {
    hunger: number;
    energy: number;
    mood: number;
    position: SandboxGridCellJson;
    intent: Record<string, unknown> | null;
}

export interface SandboxWorldJson {
    grid: { width: number; height: number };
    items: SandboxItemJson[];
}

export interface SandboxSandboxStateJson {
    tick: number;
    pet: SandboxPetJson;
    world: SandboxWorldJson;
    recent_actions: { tick: number; action: string; reason: string | null }[];
}

export interface SandboxEnvelopeJson {
    schema_version: string;
    workflow_id: string;
    sandbox: SandboxSandboxStateJson;
    playback: { paused?: boolean; tick_rate_ms?: number };
    state_version: number;
    last_error?: string | null;
}
