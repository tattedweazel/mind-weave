import { describe, expect, it } from 'vitest';
import {
    ANNOTATION_TEXT_ALIGN_DEFAULT,
    normalizeAnnotationTextAlign,
    type AnnotationTextAlign,
} from './annotationTextAlign';

describe('normalizeAnnotationTextAlign', () => {
    it('returns left for undefined, null, and non-strings', () => {
        expect(normalizeAnnotationTextAlign(undefined)).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
        expect(normalizeAnnotationTextAlign(null)).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
        expect(normalizeAnnotationTextAlign(1)).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
        expect(normalizeAnnotationTextAlign({})).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
    });

    it('returns left for invalid strings', () => {
        expect(normalizeAnnotationTextAlign('')).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
        expect(normalizeAnnotationTextAlign('justify')).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
        expect(normalizeAnnotationTextAlign('LEFT')).toBe(ANNOTATION_TEXT_ALIGN_DEFAULT);
    });

    it('returns the value for left, center, right', () => {
        const vals: AnnotationTextAlign[] = ['left', 'center', 'right'];
        for (const v of vals) {
            expect(normalizeAnnotationTextAlign(v)).toBe(v);
        }
    });
});
