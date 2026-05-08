import { describe, expect, it } from 'vitest';
import { nodeTypes } from './nodeTypes';
import { ANNOTATION_FLOW_NODE_TYPES, isAnnotationFlowNodeType, showInspectorLastRunExplorerSection } from './graphConverters';

describe('workflow annotation nodes', () => {
    it('registers annotation React Flow types on nodeTypes', () => {
        for (const t of ANNOTATION_FLOW_NODE_TYPES) {
            expect(nodeTypes).toHaveProperty(t);
            expect(typeof (nodeTypes as Record<string, unknown>)[t]).toBe('function');
        }
    });

    it('isAnnotationFlowNodeType recognizes annotation types only', () => {
        expect(isAnnotationFlowNodeType('annotationNote')).toBe(true);
        expect(isAnnotationFlowNodeType('annotationRegion')).toBe(true);
        expect(isAnnotationFlowNodeType('start')).toBe(false);
        expect(isAnnotationFlowNodeType(null)).toBe(false);
    });

    it('showInspectorLastRunExplorerSection is false for annotations only', () => {
        expect(showInspectorLastRunExplorerSection('annotationNote')).toBe(false);
        expect(showInspectorLastRunExplorerSection('annotationRegion')).toBe(false);
        expect(showInspectorLastRunExplorerSection('start')).toBe(true);
        expect(showInspectorLastRunExplorerSection('simpleLLMCall')).toBe(true);
        expect(showInspectorLastRunExplorerSection(null)).toBe(true);
    });
});
