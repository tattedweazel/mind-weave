import { describe, expect, it } from 'vitest';
import { parseEffectiveOutputExplorer, parseOutputExplorerV1 } from './types';

const minimalExplorer = {
    version: 1,
    kind: 'generic',
    summary: { line: 'x', detail_lines: [] },
    items: [] as const,
};

describe('parseOutputExplorerV1', () => {
    it('accepts valid v1 payloads', () => {
        expect(parseOutputExplorerV1(minimalExplorer)).toEqual(minimalExplorer);
    });

    it('rejects invalid payloads', () => {
        expect(parseOutputExplorerV1(null)).toBeNull();
        expect(parseOutputExplorerV1({})).toBeNull();
        expect(parseOutputExplorerV1({ version: 2, kind: 'generic', summary: { line: 'x' }, items: [] })).toBeNull();
    });
});

describe('parseEffectiveOutputExplorer', () => {
    it('prefers output_explorer over skill_explorer', () => {
        const a = { ...minimalExplorer, summary: { line: 'new' } };
        const b = { ...minimalExplorer, summary: { line: 'old' } };
        expect(
            parseEffectiveOutputExplorer({
                output_explorer: a,
                skill_explorer: b,
            }),
        ).toEqual(a);
    });

    it('falls back to deprecated skill_explorer', () => {
        const b = { ...minimalExplorer, summary: { line: 'legacy' } };
        expect(parseEffectiveOutputExplorer({ skill_explorer: b })).toEqual(b);
    });
});
