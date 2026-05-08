import { describe, expect, it } from 'vitest';
import { paletteDisplayNameForReactFlowType } from './workflowPaletteStepItems';

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
