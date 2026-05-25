import type { SandboxItemJson, SandboxItemType } from '../domain/sandbox/types';

const REGION_ITEM_TYPE: SandboxItemType = 'region';
const BALL_ITEM_TYPE: SandboxItemType = 'ball';
const FIXTURE_ITEM_TYPE: SandboxItemType = 'fixture';

const SOLID_TYPES = new Set<SandboxItemType>(['wall', 'fixture']);
const PICKABLE_TYPES = new Set<SandboxItemType>(['food', 'ball']);

/** Resolve sensory/behavior type from legacy `type` or definition fields. */
export function resolvedItemType(item: SandboxItemJson): SandboxItemType {
    if (item.type != null) {
        return item.type;
    }
    const kind = item.definition_kind;
    if (kind === 'terrain') return 'wall';
    if (kind === 'fixture') return FIXTURE_ITEM_TYPE;
    if (kind === 'region') return REGION_ITEM_TYPE;
    if (kind === 'item') {
        if (item.energy != null) return 'food';
        const slug = (item.builtin_slug ?? '').toLowerCase();
        if (slug.includes('ball') || item.color != null) return BALL_ITEM_TYPE;
        return 'food';
    }
    return 'food';
}

export function isSolidItem(item: SandboxItemJson): boolean {
    if (item.role === 'solid') return true;
    return SOLID_TYPES.has(resolvedItemType(item));
}

export function isPickableItem(item: SandboxItemJson): boolean {
    if (item.role === 'pickable') return true;
    return PICKABLE_TYPES.has(resolvedItemType(item));
}

export function isRegionItemResolved(item: SandboxItemJson): boolean {
    return resolvedItemType(item) === REGION_ITEM_TYPE;
}

export function isFixtureItem(item: SandboxItemJson): boolean {
    return resolvedItemType(item) === FIXTURE_ITEM_TYPE;
}
