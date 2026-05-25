/** JSON shapes returned by `/api/v1/sandbox/*` (mirror backend schemas). */

export type SandboxFacing = 'N' | 'E' | 'S' | 'W';

export const SANDBOX_FACING_VALUES: readonly SandboxFacing[] = ['N', 'E', 'S', 'W'];

export const DEFAULT_SANDBOX_FACING: SandboxFacing = 'N';

export type RegionTriggerMode = 'enter' | 'exit' | 'while_inside' | 'on_enter_once';

export interface RegionTriggerConfigJson {
    enabled: boolean;
    mode: RegionTriggerMode | null;
    workflow_id: string | null;
    inputs: Record<string, unknown>;
}

export const DEFAULT_REGION_TRIGGER: RegionTriggerConfigJson = {
    enabled: false,
    mode: null,
    workflow_id: null,
    inputs: {},
};

export interface SandboxGridCellJson {
    x: number;
    y: number;
}

export type SandboxItemType = 'food' | 'wall' | 'region' | 'ball' | 'fixture';

export type SandboxDefinitionKind = 'item' | 'terrain' | 'fixture' | 'region';

export type SandboxItemRole = 'pickable' | 'solid';

export interface SandboxItemJson {
    id: string;
    type?: SandboxItemType;
    definition_id?: string;
    definition_kind?: SandboxDefinitionKind;
    role?: SandboxItemRole;
    position: SandboxGridCellJson;
    energy?: number;
    color?: string;
    label?: string;
    trigger?: RegionTriggerConfigJson;
    builtin_slug?: string;
}

export type SandboxInventoryItemType = 'ball' | 'food';

export interface SandboxInventoryItemJson {
    type: SandboxInventoryItemType;
    color?: string;
    energy?: number;
}

export interface SandboxCreatureJson {
    id: string;
    workflow_id: string;
    name?: string | null;
    position: SandboxGridCellJson;
    facing: SandboxFacing;
    color?: string;
    inventory?: SandboxInventoryItemJson[];
}

export interface SandboxWorldJson {
    grid: { width: number; height: number };
    items: SandboxItemJson[];
}

export interface SandboxRecentActionJson {
    tick: number;
    creature_id?: string | null;
    action: string;
    reason: string | null;
}

export interface SandboxSandboxStateJson {
    tick: number;
    creatures: SandboxCreatureJson[];
    world: SandboxWorldJson;
    recent_actions: SandboxRecentActionJson[];
}

export interface SandboxEnvelopeJson {
    schema_version: string;
    board_id?: string | null;
    sandbox: SandboxSandboxStateJson;
    playback: { paused?: boolean; tick_rate_ms?: number };
    state_version: number;
    last_errors?: Record<string, string | null>;
    last_fixture_errors?: Record<string, string | null>;
    region_trigger_state?: { enter_once_fired?: Record<string, string[]> };
    last_region_trigger_errors?: string[];
}

export type SandboxNestedWorkflowRunKind = 'fixture' | 'region_trigger';

export interface SandboxNestedWorkflowRunMetaJson {
    kind: SandboxNestedWorkflowRunKind;
    label: string;
    creature_id: string;
    tick: number;
    workflow_id: string;
    fixture_id?: string | null;
    region_id?: string | null;
    trigger_mode?: string | null;
    node_labels?: Record<string, string>;
}

export interface SandboxNestedWorkflowRunJson {
    meta: SandboxNestedWorkflowRunMetaJson;
    run: import('../api/types').WorkflowRunResult;
}

export interface SandboxSimulationEffectsJson {
    force_pause?: boolean;
    broadcast_messages?: Array<{
        node_id: string;
        body: string;
        severity?: 'info' | 'notice' | 'success';
        title?: string;
        render_markdown?: boolean;
        source?: string;
        step_number?: number;
    }>;
}

export interface BoardCreaturePlacementJson {
    id: string;
    workflow_id: string;
    creature_definition_id?: string;
    name?: string | null;
    position: SandboxGridCellJson;
    facing?: SandboxFacing;
    color?: string;
    inventory?: SandboxInventoryItemJson[];
}

export interface BoardDefinitionJson {
    schema_version?: string;
    grid: { width: number; height: number };
    items: SandboxItemJson[];
    creatures: BoardCreaturePlacementJson[];
}

export interface SandboxBoardJson {
    id: string;
    name: string;
    description: string;
    is_system: boolean;
    project_id?: string | null;
    definition: BoardDefinitionJson;
    created_at: string;
    updated_at: string;
}

/** Convert board definition to sandbox state shape for Phaser preview (builder tab). */
export function sandboxStateFromBoardDefinition(def: BoardDefinitionJson): SandboxSandboxStateJson {
    return {
        tick: 0,
        creatures: def.creatures.map(c => ({
            id: c.id,
            workflow_id: c.workflow_id,
            name: c.name ?? null,
            position: c.position,
            facing: c.facing ?? DEFAULT_SANDBOX_FACING,
            ...(c.color !== undefined ? { color: c.color } : {}),
            inventory: c.inventory ?? [],
        })),
        world: { grid: def.grid, items: def.items ?? [] },
        recent_actions: [],
    };
}
