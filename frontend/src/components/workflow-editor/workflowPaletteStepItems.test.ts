import { describe, expect, it } from 'vitest';
import {
    WORKFLOW_PALETTE_SKILL_ITEMS,
    WORKFLOW_PALETTE_UTILITY_ITEMS,
    paletteDisplayNameForReactFlowType,
} from './workflowPaletteStepItems';

function paletteTypes(items: ReadonlyArray<{ type: string }>): string[] {
    return items.map((item) => item.type);
}

describe('workflow palette taxonomy', () => {
    it('lists Google Docs Get in Skills and Parse in Utilities only', () => {
        const skillTypes = paletteTypes(WORKFLOW_PALETTE_SKILL_ITEMS);
        const utilityTypes = paletteTypes(WORKFLOW_PALETTE_UTILITY_ITEMS);

        expect(skillTypes).toContain('googleDocsGetDocument');
        expect(skillTypes).not.toContain('googleDocsParseDocument');
        expect(utilityTypes).toContain('googleDocsParseDocument');
        expect(utilityTypes).not.toContain('googleDocsGetDocument');
    });
});

describe('paletteDisplayNameForReactFlowType', () => {
    it('returns palette tile labels for known types', () => {
        expect(paletteDisplayNameForReactFlowType('lenFromList')).toBe('Len from List');
        expect(paletteDisplayNameForReactFlowType('intToString')).toBe('Int to String');
        expect(paletteDisplayNameForReactFlowType('stop')).toBe('Stop');
    });

    it('returns fixed labels for non-palette canvas types', () => {
        expect(paletteDisplayNameForReactFlowType('start')).toBe('Start');
        expect(paletteDisplayNameForReactFlowType('sandboxBehaviorPrimitive')).toBe('Sandbox behavior');
        expect(paletteDisplayNameForReactFlowType('invalidStep')).toBe('Invalid step');
    });

    it('falls back to the raw type string when unknown', () => {
        expect(paletteDisplayNameForReactFlowType('futureNodeType')).toBe('futureNodeType');
    });
});
