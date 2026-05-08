import { describe, expect, it } from 'vitest';
import { lastRunInputsPayload } from './lastRunInputsPayload';

describe('lastRunInputsPayload', () => {
    it('returns null for empty or missing details', () => {
        expect(lastRunInputsPayload(undefined)).toBeNull();
        expect(lastRunInputsPayload(null)).toBeNull();
        expect(lastRunInputsPayload({})).toBeNull();
    });

    it('uses resolved_inputs when present', () => {
        expect(
            lastRunInputsPayload({
                resolved_inputs: { a: 1, b: 'two' },
            }),
        ).toEqual({ a: 1, b: 'two' });
    });

    it('merges top-level LLM keys when not already in resolved_inputs', () => {
        expect(
            lastRunInputsPayload({
                resolved_inputs: { model: 'x' },
                user_prompt: 'hello',
                system_prompt: 'sys',
                additional_context: 'ctx',
            }),
        ).toEqual({
            model: 'x',
            user_prompt: 'hello',
            system_prompt: 'sys',
            additional_context: 'ctx',
        });
    });

    it('does not override resolved_inputs with top-level LLM keys', () => {
        expect(
            lastRunInputsPayload({
                resolved_inputs: { user_prompt: 'from resolved' },
                user_prompt: 'from top',
            }),
        ).toEqual({ user_prompt: 'from resolved' });
    });

    it('ignores non-object resolved_inputs', () => {
        expect(
            lastRunInputsPayload({
                resolved_inputs: 'bad' as unknown as Record<string, unknown>,
                user_prompt: 'only this',
            }),
        ).toEqual({ user_prompt: 'only this' });
    });
});
