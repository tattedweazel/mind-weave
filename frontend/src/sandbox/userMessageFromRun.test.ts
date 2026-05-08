import { describe, expect, it } from 'vitest';

import type { NodeRunResult } from '../api/types';

import { collectUserMessagesFromNodeResults, SANDBOX_USER_MESSAGE_UI_MAX_LEN } from './userMessageFromRun';

describe('collectUserMessagesFromNodeResults', () => {
    it('returns empty for undefined or empty', () => {
        expect(collectUserMessagesFromNodeResults(undefined)).toBe('');
        expect(collectUserMessagesFromNodeResults([])).toBe('');
    });

    it('joins messages in step_number order', () => {
        const rows: NodeRunResult[] = [
            { node_id: 'b', status: 'ok', details: { user_message: 'second' }, step_number: 2 },
            { node_id: 'a', status: 'ok', details: { user_message: 'first' }, step_number: 1 },
        ];
        expect(collectUserMessagesFromNodeResults(rows)).toBe('first\n\nsecond');
    });

    it('skips non-ok and missing user_message', () => {
        const rows: NodeRunResult[] = [
            { node_id: 'a', status: 'error', details: { user_message: 'x' }, step_number: 1 },
            { node_id: 'b', status: 'ok', details: {}, step_number: 2 },
            { node_id: 'c', status: 'ok', details: { user_message: 'keep' }, step_number: 3 },
        ];
        expect(collectUserMessagesFromNodeResults(rows)).toBe('keep');
    });

    it('truncates very long joined text', () => {
        const long = 'a'.repeat(SANDBOX_USER_MESSAGE_UI_MAX_LEN + 50);
        const rows: NodeRunResult[] = [
            { node_id: 'a', status: 'ok', details: { user_message: long }, step_number: 1 },
        ];
        const out = collectUserMessagesFromNodeResults(rows);
        expect(out.endsWith('…')).toBe(true);
        expect(out.length).toBe(SANDBOX_USER_MESSAGE_UI_MAX_LEN + 1);
    });
});
