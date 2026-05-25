import { describe, expect, it } from 'vitest';

import { resolvedItemType, isFixtureItem, isSolidItem } from './sandboxItemResolve';

describe('sandboxItemResolve', () => {
    it('resolves definition_kind to runtime type', () => {
        expect(
            resolvedItemType({
                id: '1',
                definition_kind: 'terrain',
                role: 'solid',
                position: { x: 0, y: 0 },
            }),
        ).toBe('wall');
        expect(
            resolvedItemType({
                id: '2',
                definition_kind: 'fixture',
                role: 'solid',
                position: { x: 0, y: 0 },
            }),
        ).toBe('fixture');
    });

    it('detects solid and fixture items', () => {
        const fixture = {
            id: 'f1',
            type: 'fixture' as const,
            position: { x: 0, y: 0 },
        };
        expect(isFixtureItem(fixture)).toBe(true);
        expect(isSolidItem(fixture)).toBe(true);
    });
});
