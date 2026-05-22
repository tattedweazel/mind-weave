import { describe, expect, it } from 'vitest';

import { normalizeBoardName, shouldCommitBoardRename } from './sandboxBoardRename';

describe('sandboxBoardRename', () => {
    describe('normalizeBoardName', () => {
        it('returns trimmed draft when non-empty', () => {
            expect(normalizeBoardName('  My Board  ', 'Fallback')).toBe('My Board');
        });

        it('returns fallback when draft is empty or whitespace', () => {
            expect(normalizeBoardName('', 'Fallback')).toBe('Fallback');
            expect(normalizeBoardName('   ', 'Fallback')).toBe('Fallback');
        });
    });

    describe('shouldCommitBoardRename', () => {
        it('returns false for system boards', () => {
            expect(
                shouldCommitBoardRename({
                    currentName: 'Old',
                    draftName: 'New',
                    isSystem: true,
                }),
            ).toBe(false);
        });

        it('returns false when draft is empty or whitespace', () => {
            expect(
                shouldCommitBoardRename({
                    currentName: 'Old',
                    draftName: '',
                    isSystem: false,
                }),
            ).toBe(false);
            expect(
                shouldCommitBoardRename({
                    currentName: 'Old',
                    draftName: '   ',
                    isSystem: false,
                }),
            ).toBe(false);
        });

        it('returns false when normalized draft matches current name', () => {
            expect(
                shouldCommitBoardRename({
                    currentName: 'Same',
                    draftName: 'Same',
                    isSystem: false,
                }),
            ).toBe(false);
            expect(
                shouldCommitBoardRename({
                    currentName: 'Same',
                    draftName: '  Same  ',
                    isSystem: false,
                }),
            ).toBe(false);
        });

        it('returns true when user-owned board name changed', () => {
            expect(
                shouldCommitBoardRename({
                    currentName: 'Old',
                    draftName: 'New',
                    isSystem: false,
                }),
            ).toBe(true);
        });
    });
});
