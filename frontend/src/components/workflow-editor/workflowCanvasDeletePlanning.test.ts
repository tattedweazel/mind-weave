import type { Node as FlowNode } from '@xyflow/react';
import { describe, expect, it } from 'vitest';
import {
    eventTargetIsTextEntry,
    isKeyboardDeleteIntentKey,
    planCanvasNodeDeletion,
} from './workflowCanvasDeletePlanning';

describe('isKeyboardDeleteIntentKey', () => {
    it('accepts Delete and Backspace without modifiers', () => {
        expect(isKeyboardDeleteIntentKey({ key: 'Delete', metaKey: false, ctrlKey: false, altKey: false })).toBe(true);
        expect(isKeyboardDeleteIntentKey({ key: 'Backspace', metaKey: false, ctrlKey: false, altKey: false })).toBe(
            true,
        );
    });

    it('rejects other keys', () => {
        expect(isKeyboardDeleteIntentKey({ key: 'Enter', metaKey: false, ctrlKey: false, altKey: false })).toBe(false);
        expect(isKeyboardDeleteIntentKey({ key: 'Escape', metaKey: false, ctrlKey: false, altKey: false })).toBe(false);
    });

    it('rejects when meta, ctrl, or alt is held', () => {
        expect(isKeyboardDeleteIntentKey({ key: 'Backspace', metaKey: true, ctrlKey: false, altKey: false })).toBe(
            false,
        );
        expect(isKeyboardDeleteIntentKey({ key: 'Delete', metaKey: false, ctrlKey: true, altKey: false })).toBe(false);
        expect(isKeyboardDeleteIntentKey({ key: 'Delete', metaKey: false, ctrlKey: false, altKey: true })).toBe(false);
    });
});

describe('eventTargetIsTextEntry', () => {
    it('returns false for null', () => {
        expect(eventTargetIsTextEntry(null)).toBe(false);
    });

    it('detects textarea and select', () => {
        expect(eventTargetIsTextEntry(document.createElement('textarea'))).toBe(true);
        expect(eventTargetIsTextEntry(document.createElement('select'))).toBe(true);
    });

    it('treats text-like inputs as text entry', () => {
        const text = document.createElement('input');
        text.type = 'text';
        expect(eventTargetIsTextEntry(text)).toBe(true);
        const search = document.createElement('input');
        search.type = 'search';
        expect(eventTargetIsTextEntry(search)).toBe(true);
    });

    it('treats button-like inputs as not text entry', () => {
        const btn = document.createElement('input');
        btn.type = 'button';
        expect(eventTargetIsTextEntry(btn)).toBe(false);
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        expect(eventTargetIsTextEntry(cb)).toBe(false);
    });

    it('detects contenteditable on self or ancestor', () => {
        const host = document.createElement('div');
        host.setAttribute('contenteditable', 'true');
        const child = document.createElement('span');
        host.appendChild(child);
        expect(eventTargetIsTextEntry(child)).toBe(true);
    });
});

describe('planCanvasNodeDeletion', () => {
    const flow = (partial: Partial<FlowNode> & { id: string; type: string }): FlowNode =>
        ({
            position: { x: 0, y: 0 },
            data: {},
            ...partial,
        }) as FlowNode;

    it('fails on empty selection', () => {
        const r = planCanvasNodeDeletion([], [flow({ id: 'a', type: 'stringPrimitive' })]);
        expect(r.ok).toBe(false);
        if (!r.ok) expect(r.reason).toContain('Select');
    });

    it('fails when only Start is selected', () => {
        const start = flow({ id: 's', type: 'start' });
        const r = planCanvasNodeDeletion([start], [start, flow({ id: 't', type: 'stop' })]);
        expect(r.ok).toBe(false);
        if (!r.ok) expect(r.reason).toContain('Start');
    });

    it('omits Start from ids when other nodes are selected', () => {
        const start = flow({ id: 's', type: 'start' });
        const a = flow({ id: 'a', type: 'stringPrimitive' });
        const stop = flow({ id: 't', type: 'stop' });
        const r = planCanvasNodeDeletion([start, a], [start, a, stop]);
        expect(r.ok).toBe(true);
        if (r.ok) {
            expect(r.ids).toEqual(['a']);
            expect(r.skippedStart).toBe(true);
        }
    });

    it('blocks removing the last Stop', () => {
        const stop = flow({ id: 't', type: 'stop' });
        const a = flow({ id: 'a', type: 'stringPrimitive' });
        const r = planCanvasNodeDeletion([stop, a], [stop, a]);
        expect(r.ok).toBe(false);
        if (!r.ok) expect(r.reason).toContain('Stop');
    });

    it('allows removing one Stop when another remains', () => {
        const t1 = flow({ id: 't1', type: 'stop' });
        const t2 = flow({ id: 't2', type: 'stop' });
        const r = planCanvasNodeDeletion([t1], [t1, t2]);
        expect(r.ok).toBe(true);
        if (r.ok) expect(r.ids).toEqual(['t1']);
    });

    it('allows non-Stop selection when graph has a Stop elsewhere', () => {
        const a = flow({ id: 'a', type: 'stringPrimitive' });
        const stop = flow({ id: 't', type: 'stop' });
        const r = planCanvasNodeDeletion([a], [a, stop]);
        expect(r.ok).toBe(true);
        if (r.ok) {
            expect(r.ids).toEqual(['a']);
            expect(r.skippedStart).toBe(false);
        }
    });
});
