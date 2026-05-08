import { describe, expect, it } from 'vitest';

import type { SandboxEnvelopeJson } from '../domain/sandbox/types';
import { cellHasInspectableContent, getCellOccupants } from './sandboxCellOccupants';

function baseEnvelope(overrides: Partial<SandboxEnvelopeJson> = {}): SandboxEnvelopeJson {
    const base: SandboxEnvelopeJson = {
        schema_version: '1',
        workflow_id: 'wf-1',
        sandbox: {
            tick: 0,
            pet: {
                hunger: 10,
                energy: 50,
                mood: 80,
                position: { x: 0, y: 0 },
                intent: null,
            },
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
    it('returns empty items and petHere false for empty cell', () => {
        const env = baseEnvelope();
        expect(getCellOccupants(env, { x: 2, y: 3 })).toEqual({ items: [], petHere: false });
    });

    it('returns petHere when pet matches cell', () => {
        const env = baseEnvelope({
            sandbox: {
                tick: 1,
                pet: {
                    hunger: 1,
                    energy: 2,
                    mood: 3,
                    position: { x: 4, y: 4 },
                    intent: null,
                },
                world: { grid: { width: 5, height: 5 }, items: [] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 4, y: 4 })).toEqual({ items: [], petHere: true });
        expect(getCellOccupants(env, { x: 0, y: 0 })).toEqual({ items: [], petHere: false });
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
                pet: {
                    hunger: 0,
                    energy: 0,
                    mood: 0,
                    position: { x: 0, y: 0 },
                    intent: null,
                },
                world: { grid: { width: 5, height: 5 }, items: [food] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 1, y: 2 })).toEqual({ items: [food], petHere: false });
        expect(getCellOccupants(env, { x: 1, y: 1 })).toEqual({ items: [], petHere: false });
    });

    it('returns both items and pet when both occupy cell', () => {
        const food = {
            id: 'f',
            type: 'food',
            position: { x: 2, y: 2 },
            energy: 10,
        };
        const env = baseEnvelope({
            sandbox: {
                tick: 0,
                pet: {
                    hunger: 0,
                    energy: 0,
                    mood: 0,
                    position: { x: 2, y: 2 },
                    intent: null,
                },
                world: { grid: { width: 5, height: 5 }, items: [food] },
                recent_actions: [],
            },
        });
        expect(getCellOccupants(env, { x: 2, y: 2 })).toEqual({ items: [food], petHere: true });
    });
});

describe('cellHasInspectableContent', () => {
    it('is false when no items and pet not here', () => {
        expect(cellHasInspectableContent({ items: [], petHere: false })).toBe(false);
    });

    it('is true when pet here', () => {
        expect(cellHasInspectableContent({ items: [], petHere: true })).toBe(true);
    });

    it('is true when items present', () => {
        expect(
            cellHasInspectableContent({
                items: [{ id: '1', type: 'food', position: { x: 0, y: 0 } }],
                petHere: false,
            }),
        ).toBe(true);
    });
});
