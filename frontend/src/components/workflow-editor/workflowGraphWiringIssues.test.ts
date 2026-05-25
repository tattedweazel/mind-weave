import { describe, expect, it } from 'vitest';
import type { Edge, Node } from '@xyflow/react';
import { findWorkflowGraphWiringIssues, resolveEdgesForWiringValidation } from './workflowGraphWiringIssues';

function node(id: string, type: string, data: Record<string, unknown> = {}): Node {
    return { id, type, position: { x: 0, y: 0 }, data: { label: id, ...data } };
}

function edge(
    id: string,
    source: string,
    target: string,
    sourceHandle?: string | null,
    targetHandle?: string | null,
): Edge {
    return {
        id,
        source,
        target,
        sourceHandle: sourceHandle ?? undefined,
        targetHandle: targetHandle ?? undefined,
    };
}

describe('findWorkflowGraphWiringIssues', () => {
    it('returns no issues for valid starter-sandbox-shaped Start wiring', () => {
        const nodes = [
            node('start', 'start', {
                label: 'Start',
                required_inputs: [{ key: 'sandbox_tick', type: 'dictionary', value: null }],
            }),
            node('nearby', 'sandboxGetNearby', { label: 'Get nearby' }),
        ];
        const edges = [
            edge('e1', 'start', 'nearby', 'signal_out', 'trigger'),
            edge('e2', 'start', 'nearby', 'sandbox_tick', 'input'),
        ];
        expect(findWorkflowGraphWiringIssues(nodes, edges)).toEqual([]);
    });

    it('flags Start sandbox_tick when required_inputs is empty (legacy mismatch)', () => {
        const nodes = [
            node('start', 'start', { label: 'Start', required_inputs: [] }),
            node('pos', 'sandboxGetPosition', { label: 'Get position' }),
        ];
        const edges = [edge('e1', 'start', 'pos', 'sandbox_tick', 'input')];
        const issues = findWorkflowGraphWiringIssues(nodes, edges);
        expect(issues).toHaveLength(1);
        expect(issues[0]?.kind).toBe('invalid_source_handle');
        expect(issues[0]?.sourceHandle).toBe('sandbox_tick');
        expect(issues[0]?.validSourceHandles).toContain('output');
        expect(issues[0]?.validSourceHandles).toContain('signal_out');
    });

    it('flags Stop target handle that does not match required_outputs key', () => {
        const nodes = [
            node('src', 'stringPrimitive', { label: 'String' }),
            node('stop', 'stop', {
                label: 'Stop',
                required_outputs: [{ key: 'final_summary', type: 'string' }],
            }),
        ];
        const edges = [edge('e1', 'src', 'stop', 'output', 'output')];
        const issues = findWorkflowGraphWiringIssues(nodes, edges);
        expect(issues).toHaveLength(1);
        expect(issues[0]?.kind).toBe('invalid_target_handle');
        expect(issues[0]?.targetHandle).toBe('output');
        expect(issues[0]?.validTargetHandles).toContain('final_summary');
    });

    it('flags edges referencing missing nodes', () => {
        const nodes = [node('a', 'stringPrimitive')];
        const edges = [edge('e1', 'a', 'missing', 'output', 'input')];
        const issues = findWorkflowGraphWiringIssues(nodes, edges);
        expect(issues).toHaveLength(1);
        expect(issues[0]?.kind).toBe('missing_target_node');
    });

    it('flags edges touching annotation nodes', () => {
        const nodes = [node('note', 'annotationNote', { label: 'Note' }), node('s', 'stringPrimitive')];
        const edges = [edge('e1', 's', 'note', 'output', 'input')];
        const issues = findWorkflowGraphWiringIssues(nodes, edges);
        expect(issues).toHaveLength(1);
        expect(issues[0]?.kind).toBe('annotation_edge');
    });

    it('accepts For Loop End export handle from exports list', () => {
        const nodes = [
            node('loop', 'forLoopControl', { label: 'Loop' }),
            node('end', 'forLoopEndControl', {
                label: 'Loop End',
                exports: ['summaries', 'available_milk'],
            }),
            node('add', 'addToList', { label: 'Add' }),
        ];
        const edges = [edge('e1', 'add', 'end', 'output', 'summaries')];
        expect(findWorkflowGraphWiringIssues(nodes, edges)).toEqual([]);
    });
});

describe('resolveEdgesForWiringValidation', () => {
    it('uses committed edges when present', () => {
        const committed = [edge('e1', 'a', 'b')];
        const pending = [edge('e2', 'c', 'd')];
        expect(resolveEdgesForWiringValidation(committed, pending)).toEqual(committed);
    });

    it('falls back to pending edges during deferred commit when committed list is empty', () => {
        const pending = [edge('e1', 'a', 'b', 'sandbox_tick', 'input')];
        expect(resolveEdgesForWiringValidation([], pending)).toEqual(pending);
    });

    it('returns empty array when both committed and pending are empty', () => {
        expect(resolveEdgesForWiringValidation([], null)).toEqual([]);
        expect(resolveEdgesForWiringValidation([], [])).toEqual([]);
    });
});
