import { describe, expect, it } from 'vitest';

import type { NearbyCellKind } from './sandboxSensoryProbes';
import {
    forwardRingSlot,
    nearbyCellKindBadgeClass,
    nearbyCellKindLabel,
    nearbyCellsToRingMap,
    nearbyRegionChipLabel,
    offsetToRingSlot,
    resolveBallDisplayColor,
} from './sandboxSensoryProbeDisplay';

const ALL_KINDS: NearbyCellKind[] = [
    'empty',
    'wall',
    'food',
    'ball',
    'fixture',
    'creature',
    'out_of_bounds',
];

describe('sandboxSensoryProbeDisplay', () => {
    it('maps relative offsets to ring slots', () => {
        expect(offsetToRingSlot(0, -1)).toBe('n');
        expect(offsetToRingSlot(1, 0)).toBe('e');
        expect(offsetToRingSlot(0, 1)).toBe('s');
        expect(offsetToRingSlot(-1, 0)).toBe('w');
        expect(offsetToRingSlot(1, -1)).toBe('ne');
        expect(offsetToRingSlot(99, 99)).toBeNull();
    });

    it('places forward cell at correct ring slot for each facing', () => {
        const origin = { x: 3, y: 2 };
        const facings = [
            { facing: 'N' as const, forward: { x: 3, y: 1 } },
            { facing: 'E' as const, forward: { x: 4, y: 2 } },
            { facing: 'S' as const, forward: { x: 3, y: 3 } },
            { facing: 'W' as const, forward: { x: 2, y: 2 } },
        ];
        for (const { facing, forward } of facings) {
            const cells = [{ x: forward.x, y: forward.y, kind: 'wall' as const }];
            const map = nearbyCellsToRingMap(cells, origin);
            expect(map[forwardRingSlot(facing)]).toEqual(cells[0]);
        }
    });

    it('labels and badge classes cover all nearby cell kinds', () => {
        for (const kind of ALL_KINDS) {
            expect(nearbyCellKindLabel(kind)).toBeTruthy();
            expect(nearbyCellKindBadgeClass(kind)).toMatch(/bg-/);
        }
    });

    it('resolves ball display color with fallback', () => {
        expect(resolveBallDisplayColor('#eaf73b')).toBe('#EAF73B');
        expect(resolveBallDisplayColor(undefined)).toBe('#3B82F6');
        expect(resolveBallDisplayColor('bad')).toBe('#3B82F6');
    });

    it('nearbyRegionChipLabel returns null without region', () => {
        expect(nearbyRegionChipLabel(null)).toBeNull();
        expect(nearbyRegionChipLabel(undefined)).toBeNull();
    });

    it('nearbyRegionChipLabel returns label text or generic Region', () => {
        expect(nearbyRegionChipLabel('target')).toBe('target');
        expect(nearbyRegionChipLabel('')).toBe('Region');
        expect(nearbyRegionChipLabel('  ')).toBe('Region');
    });
});
