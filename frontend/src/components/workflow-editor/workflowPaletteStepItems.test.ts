import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
    WORKFLOW_PALETTE_PRIMITIVE_ITEMS,
    WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS,
    WORKFLOW_PALETTE_SKILL_ITEMS,
    WORKFLOW_PALETTE_UTILITY_ITEMS,
    paletteDisplayNameForReactFlowType,
} from './workflowPaletteStepItems';

const __dirname = dirname(fileURLToPath(import.meta.url));
const workflowEditorSource = readFileSync(join(__dirname, 'WorkflowEditor.tsx'), 'utf-8');

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
        expect(paletteDisplayNameForReactFlowType('sandboxGetPosition')).toBe('Get position');
        expect(paletteDisplayNameForReactFlowType('sandboxTickPrimitive')).toBe('Tick input');
        expect(paletteDisplayNameForReactFlowType('sandboxGetCellItems')).toBe('Get cell items');
        expect(paletteDisplayNameForReactFlowType('sandboxRemoveItemAtCell')).toBe('Remove item');
        expect(paletteDisplayNameForReactFlowType('sandboxSpawnItemAtCell')).toBe('Spawn item');
    });

    it('returns fixed labels for non-palette canvas types', () => {
        expect(paletteDisplayNameForReactFlowType('start')).toBe('Start');
        expect(paletteDisplayNameForReactFlowType('invalidStep')).toBe('Invalid step');
    });

    it('falls back to the raw type string when unknown', () => {
        expect(paletteDisplayNameForReactFlowType('futureNodeType')).toBe('futureNodeType');
    });
});

describe('sandbox navigation palette drop parity', () => {
    it('lists fixture cell utilities in Sandbox Utilities', () => {
        const types = paletteTypes(WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS);
        expect(types).toContain('sandboxGetCellItems');
        expect(types).toContain('sandboxRemoveItemAtCell');
        expect(types).toContain('sandboxSpawnItemAtCell');
    });

    it('WorkflowEditor onDrop handles every sandbox utility palette type', () => {
        for (const item of WORKFLOW_PALETTE_SANDBOX_UTILITY_ITEMS) {
            expect(workflowEditorSource).toContain(`type === '${item.type}'`);
        }
    });
});

describe('primitive palette drop parity', () => {
    it('WorkflowEditor handlePaletteDrop handles every primitive palette type', () => {
        for (const item of WORKFLOW_PALETTE_PRIMITIVE_ITEMS) {
            expect(workflowEditorSource).toContain(`type === '${item.type}'`);
        }
    });
});
