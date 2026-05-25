import { describe, expect, it } from 'vitest';

import type { SandboxItemJson } from '../domain/sandbox/types';
import {
    inspectorDefinitionSummary,
    inspectorOccupantKind,
    inspectorSectionTitle,
    inspectorWorkflowLabel,
    itemHasEnergySemantics,
    sortItemsForCellInspector,
} from './sandboxItemInspectorDisplay';

const ctx = {
    itemDefinitions: [
        {
            id: 'item-def-1',
            name: 'golden_key',
            label: 'Golden Key',
            custom_metadata: { energy: 10 },
            default_color: '#FFD700',
            shape: 'square' as const,
            pickable: true,
            is_system: false,
        },
    ],
    fixtureDefinitions: [
        {
            id: 'fx-def-1',
            name: 'steamer',
            label: 'Steamer',
            workflow_id: 'wf-abc-12345678',
            color: '#8B5CF6',
            is_system: false,
        },
    ],
    terrainDefinitions: [
        {
            id: 'terrain-def-1',
            name: 'stone',
            label: 'Stone Wall',
            shape: 'rect' as const,
            is_system: false,
        },
    ],
    workflows: [{ id: 'wf-abc-12345678', name: 'Open Door', updated_at: '2026-01-01' }],
};

describe('sandboxItemInspectorDisplay', () => {
    it('inspectorSectionTitle uses definition labels for fixture and item', () => {
        const fixture: SandboxItemJson = {
            id: 'fx1',
            type: 'fixture',
            definition_id: 'fx-def-1',
            definition_kind: 'fixture',
            role: 'solid',
            position: { x: 1, y: 1 },
        };
        const item: SandboxItemJson = {
            id: 'k1',
            definition_id: 'item-def-1',
            definition_kind: 'item',
            role: 'pickable',
            position: { x: 1, y: 1 },
        };
        expect(inspectorSectionTitle(fixture, ctx)).toBe('Fixture · Steamer');
        expect(inspectorSectionTitle(item, ctx)).toBe('Item · Golden Key');
    });

    it('does not label definition-backed pickables as food', () => {
        const item: SandboxItemJson = {
            id: 'k1',
            definition_id: 'item-def-1',
            definition_kind: 'item',
            role: 'pickable',
            position: { x: 0, y: 0 },
        };
        expect(inspectorOccupantKind(item)).toBe('pickable');
        expect(inspectorSectionTitle(item, ctx)).not.toContain('food');
    });

    it('sortItemsForCellInspector orders fixture before pickables', () => {
        const fixture: SandboxItemJson = {
            id: 'fx1',
            type: 'fixture',
            position: { x: 1, y: 1 },
        };
        const food: SandboxItemJson = {
            id: 'f1',
            type: 'food',
            position: { x: 1, y: 1 },
            energy: 10,
        };
        const region: SandboxItemJson = {
            id: 'r1',
            type: 'region',
            position: { x: 1, y: 1 },
            color: '#3B82F6',
            label: 'Goal',
        };
        const sorted = sortItemsForCellInspector([food, region, fixture]);
        expect(sorted.map(it => it.id)).toEqual(['r1', 'fx1', 'f1']);
    });

    it('inspectorWorkflowLabel resolves workflow name', () => {
        expect(inspectorWorkflowLabel('wf-abc-12345678', ctx.workflows)).toBe('Open Door');
    });

    it('itemHasEnergySemantics for definition-backed pickables with instance energy', () => {
        const item: SandboxItemJson = {
            id: 'k1',
            definition_id: 'item-def-1',
            definition_kind: 'item',
            role: 'pickable',
            position: { x: 0, y: 0 },
            energy: 5,
        };
        expect(itemHasEnergySemantics(item, ctx)).toBe(true);
    });

    it('itemHasEnergySemantics false for generic definition pickables without instance energy', () => {
        const item: SandboxItemJson = {
            id: 'k1',
            definition_id: 'item-def-1',
            definition_kind: 'item',
            role: 'pickable',
            position: { x: 0, y: 0 },
        };
        expect(itemHasEnergySemantics(item, ctx)).toBe(false);
    });

    it('inspectorDefinitionSummary returns fixture workflow id', () => {
        const fixture: SandboxItemJson = {
            id: 'fx1',
            type: 'fixture',
            definition_id: 'fx-def-1',
            definition_kind: 'fixture',
            role: 'solid',
            position: { x: 0, y: 0 },
        };
        expect(inspectorDefinitionSummary(fixture, ctx)?.workflowId).toBe('wf-abc-12345678');
    });
});
