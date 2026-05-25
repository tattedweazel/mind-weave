import type {
    FixtureDefinitionRead,
    ItemDefinitionRead,
    TerrainDefinitionRead,
    WorkflowDefinitionListItem,
} from '../api/types';
import type { SandboxItemJson } from '../domain/sandbox/types';
import {
    getSandboxItemRenderLayer,
    type SandboxItemRenderCatalog,
} from './sandboxItemRender';
import {
    isFixtureItem,
    isPickableItem,
    isRegionItemResolved,
    isSolidItem,
    resolvedItemType,
} from './sandboxItemResolve';

export type InspectorOccupantKind =
    | 'fixture'
    | 'terrain'
    | 'pickable'
    | 'builtin_food'
    | 'builtin_ball'
    | 'builtin_wall';

export interface SandboxInspectorDefinitionContext {
    itemDefinitions?: ReadonlyArray<ItemDefinitionRead>;
    terrainDefinitions?: ReadonlyArray<TerrainDefinitionRead>;
    fixtureDefinitions?: ReadonlyArray<FixtureDefinitionRead>;
    workflows?: ReadonlyArray<WorkflowDefinitionListItem>;
}

export interface InspectorDefinitionSummary {
    name: string;
    label: string;
    shape?: string;
    defaultEnergy?: number | null;
    defaultColor?: string | null;
    workflowId?: string;
}

const INSPECTOR_LAYER_ORDER: Record<string, number> = {
    region: 0,
    solid: 1,
    pickable: 2,
};

function hasDefinitionId(item: SandboxItemJson): boolean {
    return typeof item.definition_id === 'string' && item.definition_id.trim().length > 0;
}

export function inspectorOccupantKind(item: SandboxItemJson): InspectorOccupantKind {
    if (isFixtureItem(item)) return 'fixture';
    if (hasDefinitionId(item)) {
        if (item.definition_kind === 'terrain' || (isSolidItem(item) && !isFixtureItem(item))) {
            return 'terrain';
        }
        if (isPickableItem(item)) return 'pickable';
    }
    const type = resolvedItemType(item);
    if (type === 'food') return 'builtin_food';
    if (type === 'ball') return 'builtin_ball';
    if (type === 'wall') return 'builtin_wall';
    if (isPickableItem(item)) return 'pickable';
    if (isSolidItem(item)) return 'terrain';
    return 'pickable';
}

export function inspectorDefinitionSummary(
    item: SandboxItemJson,
    ctx: SandboxInspectorDefinitionContext = {},
): InspectorDefinitionSummary | null {
    const defId = item.definition_id;
    if (!defId) return null;

    if (item.definition_kind === 'fixture' || isFixtureItem(item)) {
        const def = ctx.fixtureDefinitions?.find(d => d.id === defId);
        if (!def) return null;
        return {
            name: def.name,
            label: def.label,
            defaultColor: def.color,
            workflowId: def.workflow_id,
        };
    }

    if (item.definition_kind === 'terrain' || (isSolidItem(item) && !isFixtureItem(item))) {
        const def = ctx.terrainDefinitions?.find(d => d.id === defId);
        if (!def) return null;
        return {
            name: def.name,
            label: def.label,
            shape: def.shape,
            defaultColor: def.default_color,
        };
    }

    const def = ctx.itemDefinitions?.find(d => d.id === defId);
    if (!def) return null;
    return {
        name: def.name,
        label: def.label,
        shape: def.shape,
        defaultEnergy: def.default_energy,
        defaultColor: def.default_color,
    };
}

export function inspectorWorkflowLabel(
    workflowId: string | null | undefined,
    workflows: ReadonlyArray<WorkflowDefinitionListItem> = [],
): string {
    if (!workflowId?.trim()) return '—';
    const wf = workflows.find(w => w.id === workflowId);
    if (wf?.name?.trim()) return wf.name.trim();
    return `${workflowId.slice(0, 8)}…`;
}

export function inspectorSectionTitle(
    item: SandboxItemJson,
    ctx: SandboxInspectorDefinitionContext = {},
): string {
    const def = inspectorDefinitionSummary(item, ctx);
    const kind = inspectorOccupantKind(item);

    if (kind === 'fixture') {
        return def?.label ? `Fixture · ${def.label}` : 'Fixture';
    }
    if (kind === 'terrain') {
        return def?.label ? `Terrain · ${def.label}` : 'Terrain';
    }
    if (kind === 'pickable' && def?.label) {
        return `Item · ${def.label}`;
    }
    if (kind === 'builtin_food') return 'Food';
    if (kind === 'builtin_ball') return 'Ball';
    if (kind === 'builtin_wall') return 'Terrain';
    return 'Item';
}

export function inspectorBuiltinTypeLabel(item: SandboxItemJson): string | null {
    if (hasDefinitionId(item)) return null;
    const type = resolvedItemType(item);
    if (type === 'food') return 'Food';
    if (type === 'ball') return 'Ball';
    if (type === 'wall') return 'Terrain';
    return null;
}

export function sortItemsForCellInspector(items: SandboxItemJson[]): SandboxItemJson[] {
    return [...items].sort((a, b) => {
        const layerA = getSandboxItemRenderLayer(a) ?? 'pickable';
        const layerB = getSandboxItemRenderLayer(b) ?? 'pickable';
        const orderA = INSPECTOR_LAYER_ORDER[layerA] ?? 99;
        const orderB = INSPECTOR_LAYER_ORDER[layerB] ?? 99;
        if (orderA !== orderB) return orderA - orderB;
        if (isFixtureItem(a) && !isFixtureItem(b)) return -1;
        if (!isFixtureItem(a) && isFixtureItem(b)) return 1;
        if (isSolidItem(a) && !isSolidItem(b) && !isFixtureItem(b)) return -1;
        if (!isSolidItem(a) && isSolidItem(b) && !isFixtureItem(a)) return 1;
        return a.id.localeCompare(b.id);
    });
}

export function itemHasEnergySemantics(
    item: SandboxItemJson,
    ctx: SandboxInspectorDefinitionContext = {},
): boolean {
    if (!isPickableItem(item)) return false;
    if (typeof item.energy === 'number') return true;
    const kind = inspectorOccupantKind(item);
    if (kind === 'builtin_food') return true;
    if (kind === 'pickable' && hasDefinitionId(item) && resolvedItemType(item) === 'food') {
        return true;
    }
    const def = inspectorDefinitionSummary(item, ctx);
    return def?.defaultEnergy != null;
}

export function toItemRenderCatalog(ctx: SandboxInspectorDefinitionContext): SandboxItemRenderCatalog {
    return {
        itemDefinitions: (ctx.itemDefinitions ?? []).map(def => ({
            id: def.id,
            shape: def.shape === 'rect' ? 'square' : def.shape,
            default_color: def.default_color,
        })),
    };
}

export function isRegionItemForInspector(item: SandboxItemJson): boolean {
    return isRegionItemResolved(item);
}
