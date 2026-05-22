import { describe, expect, it } from 'vitest';

import { parseRegionTriggerInputs } from './sandboxItemInspectorFields';

describe('sandboxItemInspectorFields', () => {
    it('parses empty trigger inputs as object', () => {
        expect(parseRegionTriggerInputs('')).toEqual({});
    });

    it('parses valid json object', () => {
        expect(parseRegionTriggerInputs('{"goal":"finish"}')).toEqual({ goal: 'finish' });
    });

    it('rejects non-object json', () => {
        expect(parseRegionTriggerInputs('[]')).toBeNull();
        expect(parseRegionTriggerInputs('not-json')).toBeNull();
    });
});
