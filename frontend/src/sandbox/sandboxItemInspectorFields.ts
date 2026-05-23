import type { RegionTriggerMode, SandboxItemJson } from '../domain/sandbox/types';
import { DEFAULT_REGION_TRIGGER } from '../domain/sandbox/types';

/** Matches backend `DEFAULT_FOOD_ENERGY` in sandbox/constants.py */
export const SANDBOX_DEFAULT_FOOD_ENERGY = 48;

export type SandboxItemEditableFieldKey = 'energy';

export interface SandboxItemEditableField {
    key: SandboxItemEditableFieldKey;
    label: string;
    kind: 'integer';
    min?: number;
    max?: number;
    description?: string;
}

export const REGION_TRIGGER_MODES: { value: RegionTriggerMode; label: string }[] = [
    { value: 'enter', label: 'Enter — when a creature moves onto this cell' },
    { value: 'exit', label: 'Exit — when a creature leaves this cell' },
    { value: 'while_inside', label: 'While inside — every tick while overlapping' },
    { value: 'on_enter_once', label: 'On enter once — first entry per creature per session' },
];

export const SANDBOX_ITEM_INSPECTOR_FIELDS: Record<string, SandboxItemEditableField[]> = {
    ball: [],
    food: [
        {
            key: 'energy',
            label: 'Energy',
            kind: 'integer',
            min: 0,
            description: 'Energy restored when a creature eats this food.',
        },
    ],
    wall: [],
    region: [],
};

export function getEditableItemFields(itemType: string): SandboxItemEditableField[] {
    return SANDBOX_ITEM_INSPECTOR_FIELDS[itemType] ?? [];
}

export function getItemFieldValue(item: SandboxItemJson, key: SandboxItemEditableFieldKey): number | undefined {
    if (key === 'energy') {
        return typeof item.energy === 'number' ? item.energy : undefined;
    }
    return undefined;
}

export function validateItemFieldValue(field: SandboxItemEditableField, rawValue: string): number | null {
    const trimmed = rawValue.trim();
    if (trimmed === '') {
        return null;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || !Number.isInteger(parsed)) {
        return null;
    }
    let value = parsed;
    if (field.min != null) {
        value = Math.max(field.min, value);
    }
    if (field.max != null) {
        value = Math.min(field.max, value);
    }
    return value;
}

export function isEditableItemFieldKey(
    itemType: string,
    key: string,
): key is SandboxItemEditableFieldKey {
    return getEditableItemFields(itemType).some(field => field.key === key);
}

export function regionTriggerFromItem(item: SandboxItemJson) {
    return item.trigger ?? { ...DEFAULT_REGION_TRIGGER };
}

export function parseRegionTriggerInputs(raw: string): Record<string, unknown> | null {
    const trimmed = raw.trim();
    if (trimmed === '') {
        return {};
    }
    try {
        const parsed: unknown = JSON.parse(trimmed);
        if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return null;
        }
        return parsed as Record<string, unknown>;
    } catch {
        return null;
    }
}
