import { describe, expect, it } from 'vitest';

import {
    collectBroadcastSegmentsFromNodeResults,
    looksLikeMarkdown,
    normalizeBroadcastSeverity,
    parseBroadcastSegmentsFromEffects,
} from './broadcastMessage';
import type { NodeRunResult } from '../api/types';

describe('broadcastMessage helpers', () => {
    it('normalizes severity', () => {
        expect(normalizeBroadcastSeverity('SUCCESS')).toBe('success');
        expect(normalizeBroadcastSeverity('weird')).toBe('info');
    });

    it('detects markdown heuristically', () => {
        expect(looksLikeMarkdown('plain text')).toBe(false);
        expect(looksLikeMarkdown('# Heading')).toBe(true);
        expect(looksLikeMarkdown('```js\nx\n```')).toBe(true);
    });

    it('collects broadcast segments ordered by step_number', () => {
        const rows: NodeRunResult[] = [
            {
                node_id: 'b',
                status: 'ok',
                details: { broadcast_segment: { node_id: 'b', body: 'second', severity: 'info' } },
                step_number: 2,
            },
            {
                node_id: 'a',
                status: 'ok',
                details: { broadcast_segment: { node_id: 'a', body: 'first', severity: 'info' } },
                step_number: 1,
            },
        ];
        expect(collectBroadcastSegmentsFromNodeResults(rows).map(s => s.body)).toEqual(['first', 'second']);
    });

    it('parses simulation_effects broadcast_messages', () => {
        const parsed = parseBroadcastSegmentsFromEffects([
            { node_id: 'n1', body: 'Hi', severity: 'notice', source: 'Creature: A' },
        ]);
        expect(parsed).toHaveLength(1);
        expect(parsed[0].source).toBe('Creature: A');
    });
});
