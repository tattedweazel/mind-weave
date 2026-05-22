import type { SandboxItemJson } from '../domain/sandbox/types';

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

export const SANDBOX_ITEM_INSPECTOR_FIELDS: Record<string, SandboxItemEditableField[]> = {
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
