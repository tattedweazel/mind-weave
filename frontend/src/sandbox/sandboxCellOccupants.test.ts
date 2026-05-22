import { describe, expect, it } from 'vitest';

import type { SandboxEnvelopeJson } from '../domain/sandbox/types';
import { cellHasInspectableContent, deriveCellRootActions, getCellOccupants } from './sandboxCellOccupants';

function baseEnvelope(overrides: Partial<SandboxEnvelopeJson> = {}): SandboxEnvelopeJson {
    const base: SandboxEnvelopeJson = {
        schema_version: '1',
        board_id: 'board-1',
        sandbox: {
            tick: 0,
            creatures: [],
            world: {
                grid: { width: 5, height: 5 },
                items: [],
            },
            recent_actions: [],
        },
        playback: {},
        state_version: 1,
    };
    return { ...base, ...overrides, sandbox: { ...base.sandbox, ...overrides.sandbox } };
}

describe('getCellOccupants', () => {
    it('returns empty items and creatures for empty cell', () => {
        const env = baseEnvelope();
        expect(getCellOccupants(env, { x: 2, y: 3 })).toEqual({ items: [], creatures: [] });
    });

    it('returns creatures when one matches cell', () => {
        const creature = {
            id: 'c1',
            workflow_id: 'wf-1',
            position: { x: 4, y: 4 },
            facing: 'E' as const,
        };
        const env = baseEnvelope({
            sandbox: {
                tick: 1,
                creatures: [creature],
                world: { grid: { width: 5, height: 5 }, items: [] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 4, y: 4 })).toEqual({ items: [], creatures: [creature] });
        expect(getCellOccupants(env, { x: 0, y: 0 })).toEqual({ items: [], creatures: [] });
    });

    it('returns items at matching position', () => {
        const food = {
            id: 'food-1',
            type: 'food',
            position: { x: 1, y: 2 },
            energy: 25,
        };
        const env = baseEnvelope({
            sandbox: {
                tick: 0,
                creatures: [],
                world: { grid: { width: 5, height: 5 }, items: [food] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 1, y: 2 })).toEqual({ items: [food], creatures: [] });
        expect(getCellOccupants(env, { x: 1, y: 1 })).toEqual({ items: [], creatures: [] });
    });

    it('returns both items and creatures when both occupy cell', () => {
        const food = {
            id: 'f',
            type: 'food',
            position: { x: 2, y: 2 },
            energy: 10,
        };
        const creature = {
            id: 'c1',
            workflow_id: 'wf-1',
            position: { x: 2, y: 2 },
            facing: 'S' as const,
        };
        const env = baseEnvelope({
            sandbox: {
                tick: 0,
                creatures: [creature],
                world: { grid: { width: 5, height: 5 }, items: [food] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 2, y: 2 })).toEqual({ items: [food], creatures: [creature] });
    });
});

describe('cellHasInspectableContent', () => {
    it('is false when no items and no creatures', () => {
        expect(cellHasInspectableContent({ items: [], creatures: [] })).toBe(false);
    });

    it('is true when creatures present', () => {
        expect(
            cellHasInspectableContent({
                items: [],
                creatures: [
                    {
                        id: 'c1',
                        workflow_id: 'wf',
                        position: { x: 0, y: 0 },
                        facing: 'N' as const,
                    },
                ],
            }),
        ).toBe(true);
    });

    it('is true when items present', () => {
        expect(
            cellHasInspectableContent({
                items: [{ id: '1', type: 'food', position: { x: 0, y: 0 } }],
                creatures: [],
            }),
        ).toBe(true);
    });
});

describe('deriveCellRootActions', () => {
    const creature = {
        id: 'c1',
        workflow_id: 'wf-1',
        position: { x: 0, y: 0 },
        facing: 'W' as const,
    };
    const food = { id: 'f1', type: 'food' as const, position: { x: 0, y: 0 }, energy: 25 };

    it('returns place actions for empty cell when creature actions allowed', () => {
        expect(deriveCellRootActions({ items: [], creatures: [] }, { allowCreatureActions: true }).map(a => a.id)).toEqual([
            'place_item',
            'place_creature',
        ]);
    });

    it('returns only place_item for empty cell when creature actions disallowed', () => {
        expect(deriveCellRootActions({ items: [], creatures: [] }).map(a => a.id)).toEqual(['place_item']);
    });

    it('returns remove_item only for item-only cell', () => {
        expect(deriveCellRootActions({ items: [food], creatures: [] }, { allowCreatureActions: true }).map(a => a.id)).toEqual([
            'remove_item',
        ]);
    });

    it('returns remove_creature only for creature-only cell', () => {
        expect(deriveCellRootActions({ items: [], creatures: [creature] }, { allowCreatureActions: true }).map(a => a.id)).toEqual([
            'remove_creature',
        ]);
    });

    it('returns both remove actions when item and creature share cell', () => {
        expect(
            deriveCellRootActions({ items: [food], creatures: [creature] }, { allowCreatureActions: true }).map(a => a.id),
        ).toEqual(['remove_item', 'remove_creature']);
    });

    it('hides remove_creature when creature actions disallowed even if creature present', () => {
        expect(deriveCellRootActions({ items: [], creatures: [creature] }).map(a => a.id)).toEqual([]);
    });
});
