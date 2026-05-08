import type { RequiredInput } from '../../api/types';

/** Reserved across the canvas; must not duplicate @xyflow/react Handle ids on the same node. */
const RESERVED_START_SLOT_KEYS = new Set(['signal_out', 'trigger']);

/**
 * Next unique slot key for Start workflow inputs (must match canvas source handle ids).
 */
export function nextUniqueStartSlotKey(inputs: RequiredInput[]): string {
    const used = new Set(inputs.map(i => i.key.trim()).filter(k => k.length > 0));
    if (inputs.length === 0) {
        return 'user_input';
    }
    let n = 2;
    while (true) {
        const candidate = `input_${n}`;
        if (!used.has(candidate)) {
            return candidate;
        }
        n++;
    }
}

/** Returns an error message if invalid, or null if the key is allowed. */
export function validateStartSlotKey(trimmed: string, inputs: RequiredInput[], idx: number): string | null {
    if (trimmed === '') {
        return 'Key is required';
    }
    if (RESERVED_START_SLOT_KEYS.has(trimmed)) {
        return 'This key is reserved for control-flow handles';
    }
    const others = inputs
        .filter((_, i) => i !== idx)
        .map(r => r.key.trim())
        .filter(Boolean);
    if (others.includes(trimmed)) {
        return 'Key must be unique';
    }
    return null;
}
