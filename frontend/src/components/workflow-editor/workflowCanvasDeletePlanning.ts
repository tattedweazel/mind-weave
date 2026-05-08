import type { Node as FlowNode } from '@xyflow/react';

const NON_TEXT_INPUT_TYPES = new Set([
    'button',
    'checkbox',
    'color',
    'file',
    'hidden',
    'image',
    'radio',
    'range',
    'reset',
    'submit',
]);

/** Delete / Backspace when not combined with modifier shortcuts. */
export function isKeyboardDeleteIntentKey(e: Pick<KeyboardEvent, 'key' | 'metaKey' | 'ctrlKey' | 'altKey'>): boolean {
    if (e.metaKey || e.ctrlKey || e.altKey) return false;
    return e.key === 'Delete' || e.key === 'Backspace';
}

export function eventTargetIsTextEntry(target: EventTarget | null): boolean {
    let cur: EventTarget | null = target;
    while (cur) {
               if (cur instanceof HTMLElement) {
            if (cur.isContentEditable) return true;
            const ceAttr = cur.getAttribute('contenteditable');
            if (ceAttr === 'true' || ceAttr === '') return true;
            if (cur instanceof HTMLTextAreaElement) return true;
            if (cur instanceof HTMLSelectElement) return true;
            if (cur instanceof HTMLInputElement) {
                const t = (cur.type || 'text').toLowerCase();
                if (!NON_TEXT_INPUT_TYPES.has(t)) return true;
            }
        }
        cur = cur instanceof Node ? cur.parentNode : null;
    }
    return false;
}

export type CanvasNodeDeletionPlan =
    | { ok: true; ids: string[]; skippedStart: boolean }
    | { ok: false; reason: string };

/**
 * From canvas-selected nodes, compute ids safe to remove (Start omitted; last Stop invariant).
 * Order follows `selected` array order.
 */
export function planCanvasNodeDeletion(selected: FlowNode[], allNodes: FlowNode[]): CanvasNodeDeletionPlan {
    if (selected.length === 0) {
        return { ok: false, reason: 'Select a node to delete.' };
    }
    const skippedStart = selected.some(n => n.type === 'start');
    const candidates = selected.filter(n => n.type !== 'start');
    if (candidates.length === 0) {
        return { ok: false, reason: 'Start cannot be removed from the graph.' };
    }
    const stopCount = allNodes.filter(n => n.type === 'stop').length;
    const stopsToRemove = candidates.filter(n => n.type === 'stop').length;
    if (stopCount - stopsToRemove < 1) {
        return {
            ok: false,
            reason: 'Cannot delete the selection: at least one Stop node must remain.',
        };
    }
    return {
        ok: true,
        ids: candidates.map(n => n.id),
        skippedStart,
    };
}
