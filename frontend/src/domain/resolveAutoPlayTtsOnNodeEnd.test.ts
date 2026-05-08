import { describe, it, expect } from 'vitest';
import {
    resolveAutoPlayTtsForNode,
    resolveAutoPlayTtsOnNodeEnd,
    resolveTtsPlaybackWhen,
} from './resolveAutoPlayTtsOnNodeEnd';

describe('resolveAutoPlayTtsOnNodeEnd', () => {
    it('defaults inline when missing or invalid boolean', () => {
        expect(resolveAutoPlayTtsOnNodeEnd(undefined)).toBe(true);
        expect(resolveAutoPlayTtsOnNodeEnd({})).toBe(true);
        expect(resolveAutoPlayTtsOnNodeEnd({ auto_play_tts_on_node_end: undefined })).toBe(true);
        expect(resolveAutoPlayTtsOnNodeEnd({ auto_play_tts_on_node_end: 'yes' as unknown as boolean })).toBe(true);
    });

    it('respects legacy boolean', () => {
        expect(resolveAutoPlayTtsOnNodeEnd({ auto_play_tts_on_node_end: false })).toBe(false);
        expect(resolveAutoPlayTtsOnNodeEnd({ auto_play_tts_on_node_end: true })).toBe(true);
    });

    it('respects tts_playback_when over legacy boolean', () => {
        expect(
            resolveAutoPlayTtsOnNodeEnd({
                auto_play_tts_on_node_end: true,
                tts_playback_when: 'manual',
            }),
        ).toBe(false);
        expect(
            resolveAutoPlayTtsOnNodeEnd({
                auto_play_tts_on_node_end: false,
                tts_playback_when: 'inline',
            }),
        ).toBe(true);
        expect(
            resolveAutoPlayTtsOnNodeEnd({
                auto_play_tts_on_node_end: true,
                tts_playback_when: 'after_workflow',
            }),
        ).toBe(false);
    });
});

describe('resolveTtsPlaybackWhen', () => {
    it('inherits user setting when node omits override', () => {
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: false }, {})).toBe('manual');
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: false }, undefined)).toBe('manual');
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: true }, { auto_play_tts_on_node_end: null })).toBe(
            'inline',
        );
        expect(resolveTtsPlaybackWhen({ tts_playback_when: 'after_workflow' }, {})).toBe('after_workflow');
    });

    it('node legacy true/false overrides user', () => {
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: false }, { auto_play_tts_on_node_end: true })).toBe(
            'inline',
        );
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: true }, { auto_play_tts_on_node_end: false })).toBe(
            'manual',
        );
    });

    it('node tts_playback_when overrides user and legacy bool', () => {
        expect(
            resolveTtsPlaybackWhen(
                { auto_play_tts_on_node_end: false },
                { tts_playback_when: 'inline', auto_play_tts_on_node_end: false },
            ),
        ).toBe('inline');
        expect(
            resolveTtsPlaybackWhen(
                { tts_playback_when: 'inline' },
                { tts_playback_when: 'after_workflow' },
            ),
        ).toBe('after_workflow');
    });

    it('ignores invalid tts_playback_when string', () => {
        expect(resolveTtsPlaybackWhen({ auto_play_tts_on_node_end: false }, { tts_playback_when: 'nope' })).toBe('manual');
    });
});

describe('resolveAutoPlayTtsForNode', () => {
    it('is true only for inline mode', () => {
        expect(resolveAutoPlayTtsForNode({ tts_playback_when: 'after_workflow' }, {})).toBe(false);
        expect(resolveAutoPlayTtsForNode({ tts_playback_when: 'manual' }, {})).toBe(false);
        expect(resolveAutoPlayTtsForNode({}, { tts_playback_when: 'inline' })).toBe(true);
    });
});
