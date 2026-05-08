import { describe, expect, it } from 'vitest';
import { filterNamesByPrefix } from './workflowListFilter';

describe('filterNamesByPrefix', () => {
    it('returns all when query is empty', () => {
        const items = [{ name: 'Foo' }, { name: 'Bar' }];
        expect(filterNamesByPrefix(items, '')).toEqual(items);
        expect(filterNamesByPrefix(items, '   ')).toEqual(items);
    });

    it('filters by case-insensitive prefix', () => {
        const items = [{ name: 'Alpha' }, { name: 'beta' }, { name: 'Alpine' }];
        expect(filterNamesByPrefix(items, 'al')).toEqual([{ name: 'Alpha' }, { name: 'Alpine' }]);
        expect(filterNamesByPrefix(items, 'Be')).toEqual([{ name: 'beta' }]);
    });
});
