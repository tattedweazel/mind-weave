import { describe, expect, it } from 'vitest';
import type { NodeRunResult } from '../api/types';
import {
    isPlayableTtsAudioOutput,
    isRedactedTtsAudioOutput,
    mergeLastRunNodeResult,
    TTS_AUDIO_BASE64_REDACTED,
} from './ttsPlayableOutput';

describe('isPlayableTtsAudioOutput', () => {
    it('returns true for audio kind with non-empty base64', () => {
        expect(
            isPlayableTtsAudioOutput({ kind: 'audio', audio_base64: 'YWI=', mime_type: 'audio/wav' }),
        ).toBe(true);
    });

    it('returns false for redacted placeholder', () => {
        expect(isPlayableTtsAudioOutput({ kind: 'audio', audio_base64: TTS_AUDIO_BASE64_REDACTED })).toBe(false);
    });

    it('returns false for empty base64', () => {
        expect(isPlayableTtsAudioOutput({ kind: 'audio', audio_base64: '' })).toBe(false);
        expect(isPlayableTtsAudioOutput({ kind: 'audio', audio_base64: '  ' })).toBe(false);
    });

    it('returns false for non-audio', () => {
        expect(isPlayableTtsAudioOutput({ kind: 'string', text: 'hi' })).toBe(false);
        expect(isPlayableTtsAudioOutput(null)).toBe(false);
    });

    it('returns false when audio_base64 is not a string', () => {
        expect(isPlayableTtsAudioOutput({ kind: 'audio', audio_base64: null })).toBe(false);
        expect(isPlayableTtsAudioOutput({ kind: 'audio' })).toBe(false);
    });
});

describe('isRedactedTtsAudioOutput', () => {
    it('returns true only for audio with redacted token', () => {
        expect(isRedactedTtsAudioOutput({ kind: 'audio', audio_base64: TTS_AUDIO_BASE64_REDACTED })).toBe(true);
        expect(isRedactedTtsAudioOutput({ kind: 'audio', audio_base64: 'YWI=' })).toBe(false);
        expect(isRedactedTtsAudioOutput({ kind: 'string', text: 'x' })).toBe(false);
    });

    it('returns false for non-objects', () => {
        expect(isRedactedTtsAudioOutput(null)).toBe(false);
        expect(isRedactedTtsAudioOutput(undefined)).toBe(false);
        expect(isRedactedTtsAudioOutput('x')).toBe(false);
    });
});

describe('mergeLastRunNodeResult', () => {
    const full: NodeRunResult = {
        node_id: 'n1',
        status: 'ok',
        step_number: 3,
        output: { kind: 'audio', audio_base64: 'YWI=', mime_type: 'audio/wav' },
    };
    const redactedReplay: NodeRunResult = {
        node_id: 'n1',
        status: 'ok',
        step_number: 3,
        output: {
            kind: 'audio',
            audio_base64: TTS_AUDIO_BASE64_REDACTED,
            mime_type: 'audio/wav',
        },
    };

    it('returns incoming when prev is undefined', () => {
        expect(mergeLastRunNodeResult(undefined, full)).toBe(full);
    });

    it('does not let redacted replay clobber playable audio at same step', () => {
        expect(mergeLastRunNodeResult(full, redactedReplay)).toEqual(full);
    });

    it('still advances when incoming has higher step_number', () => {
        const next: NodeRunResult = {
            ...full,
            step_number: 4,
            output: { kind: 'audio', audio_base64: 'eHg=', mime_type: 'audio/wav' },
        };
        expect(mergeLastRunNodeResult(full, next)).toEqual(next);
    });

    it('keeps prev when incoming repeats lower step_number', () => {
        const older: NodeRunResult = { ...full, step_number: 2 };
        expect(mergeLastRunNodeResult(full, older)).toEqual(full);
    });

    it('accepts newer full payload at same step over prior full', () => {
        const newer: NodeRunResult = {
            ...full,
            output: { kind: 'audio', audio_base64: 'eHg=', mime_type: 'audio/wav' },
        };
        expect(mergeLastRunNodeResult(full, newer)).toEqual(newer);
    });

    it('does not special-case when prev is not playable', () => {
        const errPrev: NodeRunResult = {
            node_id: 'n1',
            status: 'error',
            step_number: 3,
            error: 'boom',
        };
        expect(mergeLastRunNodeResult(errPrev, redactedReplay)).toEqual(redactedReplay);
    });

    it('treats omitted step_number as 0 when merging redacted replay', () => {
        const fullNoStep: NodeRunResult = {
            node_id: 'n1',
            status: 'ok',
            output: { kind: 'audio', audio_base64: 'YWI=', mime_type: 'audio/wav' },
        };
        const redactedNoStep: NodeRunResult = {
            node_id: 'n1',
            status: 'ok',
            output: {
                kind: 'audio',
                audio_base64: TTS_AUDIO_BASE64_REDACTED,
                mime_type: 'audio/wav',
            },
        };
        expect(mergeLastRunNodeResult(fullNoStep, redactedNoStep)).toEqual(fullNoStep);
    });

    it('keeps prev when replay step_number defaults below stored step', () => {
        const ahead: NodeRunResult = { ...full, step_number: 5 };
        const replayImplicitZero: NodeRunResult = { ...redactedReplay, step_number: undefined };
        expect(mergeLastRunNodeResult(ahead, replayImplicitZero)).toEqual(ahead);
    });
});
