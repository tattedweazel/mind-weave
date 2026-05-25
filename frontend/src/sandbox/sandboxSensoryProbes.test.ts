import { describe, expect, it } from 'vitest';

import type { SandboxCreatureJson, SandboxSandboxStateJson } from '../domain/sandbox/types';
import {
    creatureFacingFromState,
    creaturePositionFromState,
    forwardCellKind,
    forwardCellPickable,
    inventoryFromCreature,
    nearbyCellsFromState,
} from './sandboxSensoryProbes';

function creature(overrides: Partial<SandboxCreatureJson> = {}): SandboxCreatureJson {
    return {
        id: 'c1',
        workflow_id: 'wf1',
        position: { x: 3, y: 2 },
        facing: 'N',
        ...overrides,
    };
}

function state(
    creature: SandboxCreatureJson,
    items: SandboxSandboxStateJson['world']['items'] = [],
): SandboxSandboxStateJson {
    return {
        tick: 1,
        creatures: [creature],
        world: { grid: { width: 5, height: 5 }, items },
        recent_actions: [],
    };
}

describe('sandboxSensoryProbes', () => {
    it('reads position and facing', () => {
        const c = creature({ position: { x: 4, y: 1 }, facing: 'E' });
        const st = state(c);
        expect(creaturePositionFromState(c, st)).toEqual({
            x: 4,
            y: 1,
            kind: 'empty',
            region_label: null,
            stack_count: 0,
            items: [],
        });
        expect(creatureFacingFromState(c)).toBe('E');
    });

    it('position includes region_label when standing in labeled region', () => {
        const c = creature({ position: { x: 2, y: 2 } });
        const st = state(c, [
            {
                id: 'r1',
                type: 'region',
                position: { x: 2, y: 2 },
                color: '#3B82F6',
                label: 'Goal',
            },
        ]);
        expect(creaturePositionFromState(c, st)).toEqual({
            x: 2,
            y: 2,
            kind: 'empty',
            region_label: 'Goal',
            stack_count: 0,
            items: [],
        });
    });

    it('position reports food under creature', () => {
        const c = creature({ position: { x: 2, y: 2 } });
        const st = state(c, [{ id: 'f1', type: 'food', position: { x: 2, y: 2 }, energy: 10 }]);
        expect(creaturePositionFromState(c, st)).toEqual({
            x: 2,
            y: 2,
            kind: 'food',
            region_label: null,
            stack_count: 1,
            items: [{ id: 'f1', kind: 'food', definition_id: null, energy: 10, color: null, label: 'Food (10)' }],
        });
    });

    it('nearby forward cell is wall when facing N', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const st = state(c, [
            { id: 'w1', type: 'wall', position: { x: 3, y: 1 } },
        ]);
        const cells = nearbyCellsFromState(c, st);
        expect(cells).toHaveLength(8);
        expect(cells[0]).toEqual({
            x: 3,
            y: 1,
            kind: 'wall',
            region_label: null,
            stack_count: 0,
            items: [],
        });
    });

    it('region-only cell reports empty kind with region_label', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const st = state(c, [
            {
                id: 'r1',
                type: 'region',
                position: { x: 3, y: 1 },
                color: '#3B82F6',
                label: 'target',
            },
        ]);
        expect(nearbyCellsFromState(c, st)[0]).toEqual({
            x: 3,
            y: 1,
            kind: 'empty',
            region_label: 'target',
            stack_count: 0,
            items: [],
        });
    });

    it('food on region reports food kind and region_label', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const st = state(c, [
            {
                id: 'r1',
                type: 'region',
                position: { x: 3, y: 1 },
                color: '#3B82F6',
                label: 'target',
            },
            { id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 },
        ]);
        expect(nearbyCellsFromState(c, st)[0]).toEqual({
            x: 3,
            y: 1,
            kind: 'food',
            region_label: 'target',
            stack_count: 1,
            items: [{ id: 'f1', kind: 'food', definition_id: null, energy: 10, color: null, label: 'Food (10)' }],
        });
    });

    it('region with empty label still exposes region_label', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const st = state(c, [
            { id: 'r1', type: 'region', position: { x: 3, y: 1 }, color: '#3B82F6', label: '' },
        ]);
        expect(nearbyCellsFromState(c, st)[0].region_label).toBe('');
    });

    it('ignores region-only cells for kind', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const st = state(c, [
            { id: 'r1', type: 'region', position: { x: 3, y: 1 }, color: '#3B82F6' },
        ]);
        expect(nearbyCellsFromState(c, st)[0].kind).toBe('empty');
    });

    it('resolves pickable label from item definition context', () => {
        const c = creature({ position: { x: 2, y: 2 } });
        const st = state(c, [
            {
                id: 'i1',
                type: 'food',
                definition_id: 'def-1',
                definition_kind: 'item',
                role: 'pickable',
                position: { x: 2, y: 2 },
                energy: 48,
            },
        ]);
        const probe = creaturePositionFromState(c, st, {
            itemDefinitions: [{ id: 'def-1', name: 'golden_key', label: 'Golden Key', default_energy: 48 }],
        });
        expect(probe.items[0]?.label).toBe('Golden Key');
        expect(probe.items[0]?.kind).toBe('item');
        expect(probe.items[0]?.energy).toBe(48);
    });

    it('inventory from creature', () => {
        const c = creature({ inventory: [{ type: 'food', energy: 3 }] });
        expect(inventoryFromCreature(c)).toEqual([{ type: 'food', energy: 3 }]);
    });

    it('forwardCellKind reads index-0 nearby cell', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const emptyState = state(c);
        expect(forwardCellKind(c, emptyState)).toBe('empty');

        const wallState = state(c, [{ id: 'w1', type: 'wall', position: { x: 3, y: 1 } }]);
        expect(forwardCellKind(c, wallState)).toBe('wall');

        const edgeCreature = creature({ position: { x: 0, y: 0 }, facing: 'W' });
        expect(forwardCellKind(edgeCreature, state(edgeCreature))).toBe('out_of_bounds');
    });

    it('forwardCellPickable is true only for ball or food in forward cell', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        expect(forwardCellPickable(c, state(c))).toBe(false);

        expect(
            forwardCellPickable(
                c,
                state(c, [{ id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 }]),
            ),
        ).toBe(true);
        expect(
            forwardCellPickable(
                c,
                state(c, [{ id: 'b1', type: 'ball', position: { x: 3, y: 1 }, color: '#AABBCC' }]),
            ),
        ).toBe(true);
        expect(
            forwardCellPickable(
                c,
                state(c, [{ id: 'w1', type: 'wall', position: { x: 3, y: 1 } }]),
            ),
        ).toBe(false);

        const blocked = creature({
            position: { x: 2, y: 2 },
            facing: 'N',
        });
        const withCreature = state(blocked, []);
        withCreature.creatures.push({
            id: 'c2',
            workflow_id: 'wf2',
            position: { x: 2, y: 1 },
            facing: 'S',
        });
        expect(forwardCellPickable(blocked, withCreature)).toBe(false);

        const edgeCreature = creature({ position: { x: 0, y: 0 }, facing: 'W' });
        expect(forwardCellPickable(edgeCreature, state(edgeCreature))).toBe(false);
    });

    it('forwardCellKind reports fixture and stack_count on stacked pickables', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const fixtureState = state(c, [
            {
                id: 'fix1',
                type: 'fixture',
                position: { x: 3, y: 1 },
                color: '#8B5CF6',
            },
        ]);
        expect(forwardCellKind(c, fixtureState)).toBe('fixture');

        const stackedState = state(c, [
            {
                id: 'fix1',
                type: 'fixture',
                position: { x: 3, y: 1 },
            },
            { id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 },
        ]);
        const nearby = nearbyCellsFromState(c, stackedState);
        expect(nearby[0]?.kind).toBe('fixture');
        expect(nearby[0]?.stack_count).toBe(1);
        expect(nearby[0]?.items).toHaveLength(1);
    });
});
