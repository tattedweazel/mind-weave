export type AnnotationTextAlign = 'left' | 'center' | 'right';

export const ANNOTATION_TEXT_ALIGN_DEFAULT: AnnotationTextAlign = 'left';

const VALID: ReadonlySet<string> = new Set(['left', 'center', 'right']);

export function normalizeAnnotationTextAlign(raw: unknown): AnnotationTextAlign {
    if (typeof raw === 'string' && VALID.has(raw)) {
        return raw as AnnotationTextAlign;
    }
    return ANNOTATION_TEXT_ALIGN_DEFAULT;
}
