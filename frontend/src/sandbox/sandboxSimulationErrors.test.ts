import { describe, expect, it } from 'vitest';

import type { SandboxEnvelopeJson } from '../domain/sandbox/types';
import { collectSandboxVisibleErrors } from './sandboxSimulationErrors';

function envelope(partial: Partial<SandboxEnvelopeJson>): SandboxEnvelopeJson {
    return {
        schema_version: '2.5.0',
        sandbox: {
            tick: 1,
            creatures: [],
            world: { grid: { width: 8, height: 8 }, items: [] },
            recent_actions: [],
        },
        playback: {},
        state_version: 1,
        ...partial,
    };
}

describe('collectSandboxVisibleErrors', () => {
    it('includes brain, fixture, and region trigger errors', () => {
        const errors = collectSandboxVisibleErrors(
            envelope({
                last_errors: { c1: 'brain failed' },
                last_fixture_errors: { c1: 'fixture failed' },
                last_region_trigger_errors: [
                    'region trigger enter (region_id=goal, creature_id=c1): pause failed',
                ],
            }),
            null,
        );
        expect(errors.map(e => e.source)).toEqual(['brain', 'fixture', 'region_trigger']);
    });

    it('filters to the selected creature when possible', () => {
        const errors = collectSandboxVisibleErrors(
            envelope({
                last_errors: { c1: 'brain failed', c2: 'other brain' },
                last_region_trigger_errors: [
                    'region trigger enter (region_id=goal, creature_id=c2): pause failed',
                ],
            }),
            'c1',
        );
        expect(errors).toHaveLength(1);
        expect(errors[0].source).toBe('brain');
    });
});
