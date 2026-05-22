import { describe, expect, it } from 'vitest';
import type { WorkflowDefinitionListItem } from '../../api/types';
import { filterNamesByPrefix, sortWorkflowListItems } from './workflowListFilter';

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

function wf(overrides: Partial<WorkflowDefinitionListItem> & Pick<WorkflowDefinitionListItem, 'id'>): WorkflowDefinitionListItem {
    return {
        user_id: null,
        name: 'W',
        description: null,
        updated_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        ...overrides,
    };
}

describe('sortWorkflowListItems', () => {
    it('sorts by name A–Z then id', () => {
        const items = [
            wf({ id: 'b', name: 'Beta' }),
            wf({ id: 'a', name: 'Alpha' }),
            wf({ id: 'c', name: 'Alpha' }),
        ];
        expect(sortWorkflowListItems(items, 'name').map(w => w.id)).toEqual(['a', 'c', 'b']);
    });

    it('sorts by updated desc then id', () => {
        const items = [
            wf({ id: 'old', name: 'Old', updated_at: '2026-01-01T00:00:00Z' }),
            wf({ id: 'new', name: 'New', updated_at: '2026-06-01T00:00:00Z' }),
            wf({ id: 'tie', name: 'Tie', updated_at: '2026-06-01T00:00:00Z' }),
        ];
        expect(sortWorkflowListItems(items, 'updated').map(w => w.id)).toEqual(['new', 'tie', 'old']);
    });
});
