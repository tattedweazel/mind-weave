import { describe, expect, it } from 'vitest';
import type { NodeRunLog } from '../../api/types';
import { nodeRunLogsToLastRunMap } from './nodeRunLogsToLastRunMap';

describe('nodeRunLogsToLastRunMap', () => {
    it('maps output_data to output and keeps latest step_number per node_id', () => {
        const logs: NodeRunLog[] = [
            {
                id: 'a',
                run_id: 'r',
                node_id: 'n1',
                step_number: 1,
                status: 'ok',
                output_data: { text: 'first' },
                created_at: '',
            },
            {
                id: 'b',
                run_id: 'r',
                node_id: 'n1',
                step_number: 2,
                status: 'ok',
                output_data: { text: 'second' },
                created_at: '',
            },
        ];
        const m = nodeRunLogsToLastRunMap(logs);
        expect(m.n1.output).toEqual({ text: 'second' });
        expect(m.n1.step_number).toBe(2);
    });

    it('handles missing step_number as 0 for comparison', () => {
        const logs: NodeRunLog[] = [
            {
                id: 'a',
                run_id: 'r',
                node_id: 'n1',
                step_number: null,
                status: 'ok',
                output_data: { text: 'old' },
                created_at: '',
            },
            {
                id: 'b',
                run_id: 'r',
                node_id: 'n1',
                step_number: 1,
                status: 'ok',
                output_data: { text: 'new' },
                created_at: '',
            },
        ];
        const m = nodeRunLogsToLastRunMap(logs);
        expect((m.n1.output as { text?: string })?.text).toBe('new');
    });
});
