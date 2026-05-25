import { describe, expect, it } from 'vitest';

import type { SandboxCreatureJson, SandboxSandboxStateJson } from '../domain/sandbox/types';
import {
    creatureFacingFromState,
    creaturePositionFromState,
    forwardCellAllowsPlaceItem,
    forwardCellKind,
    forwardCellPickable,
    forwardCellPickables,
    forwardCellPlaceBlockedReason,
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
            items: [
                {
                    id: 'f1',
                    kind: 'food',
                    definition_id: null,
                    energy: 10,
                    color: null,
                    custom_metadata: {},
                    label: 'Food (10)',
                },
            ],
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
            items: [
                {
                    id: 'f1',
                    kind: 'food',
                    definition_id: null,
                    energy: 10,
                    color: null,
                    custom_metadata: {},
                    label: 'Food (10)',
                },
            ],
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
            itemDefinitions: [
                {
                    id: 'def-1',
                    name: 'golden_key',
                    label: 'Golden Key',
                    custom_metadata: { energy: 48 },
                },
            ],
        });
        expect(probe.items[0]?.label).toBe('Golden Key');
        expect(probe.items[0]?.kind).toBe('item');
        expect(probe.items[0]?.energy).toBe(48);
        expect(probe.items[0]?.custom_metadata).toEqual({ energy: 48 });
    });

    it('excludes pickable:false definitions from stack_count and pickables', () => {
        const c = creature({ position: { x: 2, y: 2 } });
        const st = state(c, [
            {
                id: 'recipe1',
                definition_id: 'def-recipe',
                definition_kind: 'item',
                role: 'pickable',
                position: { x: 2, y: 2 },
            },
        ]);
        const ctx = {
            itemDefinitions: [
                {
                    id: 'def-recipe',
                    name: 'chai_recipe',
                    label: 'Chai Recipe',
                    pickable: false,
                    custom_metadata: { ingredients: ['milk', 'powder'] },
                },
            ],
        };
        const probe = creaturePositionFromState(c, st, ctx);
        expect(probe.stack_count).toBe(0);
        expect(probe.items).toEqual([]);
        expect(forwardCellPickables(c, st, ctx)).toEqual([]);
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

    it('forwardCellPickable is true when forward cell has pickables', () => {
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

    it('forwardCellPickable is true on fixture cells with stacked pickables', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const stackedState = state(c, [
            { id: 'fix1', type: 'fixture', position: { x: 3, y: 1 } },
            { id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 },
        ]);
        expect(forwardCellPickable(c, stackedState)).toBe(true);
        expect(forwardCellPickables(c, stackedState)).toHaveLength(1);
        expect(forwardCellPickables(c, stackedState)[0]?.id).toBe('f1');
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

    it('includes fixture color from definition in nearby probes', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const fixtureState = state(c, [
            {
                id: 'fix1',
                type: 'fixture',
                definition_id: 'fx-def-red',
                position: { x: 3, y: 1 },
            },
        ]);
        const nearby = nearbyCellsFromState(c, fixtureState, {
            fixtureDefinitions: [{ id: 'fx-def-red', color: '#EF4444' }],
        });
        expect(nearby[0]?.kind).toBe('fixture');
        expect(nearby[0]?.color).toBe('#EF4444');
    });

    it('uses instance fixture color over definition in probes', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        const fixtureState = state(c, [
            {
                id: 'fix1',
                type: 'fixture',
                definition_id: 'fx-def-red',
                position: { x: 3, y: 1 },
                color: '#22C55E',
            },
        ]);
        const nearby = nearbyCellsFromState(c, fixtureState, {
            fixtureDefinitions: [{ id: 'fx-def-red', color: '#EF4444' }],
        });
        expect(nearby[0]?.color).toBe('#22C55E');
    });

    it('forwardCellAllowsPlaceItem matches board builder placement rules', () => {
        const c = creature({ position: { x: 3, y: 2 }, facing: 'N' });
        expect(forwardCellAllowsPlaceItem(c, state(c))).toBe(true);

        const fixtureState = state(c, [{ id: 'fix1', type: 'fixture', position: { x: 3, y: 1 } }]);
        expect(forwardCellAllowsPlaceItem(c, fixtureState)).toBe(true);

        const stackedFixtureState = state(c, [
            { id: 'fix1', type: 'fixture', position: { x: 3, y: 1 } },
            { id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 },
        ]);
        expect(forwardCellAllowsPlaceItem(c, stackedFixtureState)).toBe(true);

        const pickableStackState = state(c, [
            { id: 'f1', type: 'food', position: { x: 3, y: 1 }, energy: 10 },
        ]);
        expect(forwardCellAllowsPlaceItem(c, pickableStackState)).toBe(true);

        const wallState = state(c, [{ id: 'w1', type: 'wall', position: { x: 3, y: 1 } }]);
        expect(forwardCellAllowsPlaceItem(c, wallState)).toBe(false);
        expect(forwardCellPlaceBlockedReason(c, wallState)).toBe('Forward cell is blocked by terrain');

        const edgeCreature = creature({ position: { x: 0, y: 0 }, facing: 'W' });
        expect(forwardCellAllowsPlaceItem(edgeCreature, state(edgeCreature))).toBe(false);
        expect(forwardCellPlaceBlockedReason(edgeCreature, state(edgeCreature))).toBe(
            'Forward cell is out of bounds',
        );

        const blocked = creature({ position: { x: 2, y: 2 }, facing: 'N' });
        const withCreature = state(blocked, []);
        withCreature.creatures.push({
            id: 'c2',
            workflow_id: 'wf2',
            position: { x: 2, y: 1 },
            facing: 'S',
        });
        expect(forwardCellAllowsPlaceItem(blocked, withCreature)).toBe(false);
        expect(forwardCellPlaceBlockedReason(blocked, withCreature)).toBe(
            'Forward cell is occupied by a creature',
        );
    });
});
