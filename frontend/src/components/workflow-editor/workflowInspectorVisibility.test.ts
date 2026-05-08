import { describe, it, expect } from 'vitest';
import { isWorkflowInspectorOpen } from './workflowInspectorVisibility';

describe('isWorkflowInspectorOpen', () => {
    it('is true when a workflow is loaded', () => {
        expect(isWorkflowInspectorOpen({ id: 'wf-1' })).toBe(true);
    });

    it('is false when no workflow is loaded', () => {
        expect(isWorkflowInspectorOpen(null)).toBe(false);
        expect(isWorkflowInspectorOpen(undefined)).toBe(false);
    });
});
