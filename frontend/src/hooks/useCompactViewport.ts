import { useEffect, useState } from 'react';

/** Matches Tailwind `lg` (1024px): compact when viewport is below that width. */
export const COMPACT_VIEWPORT_MEDIA_QUERY = '(max-width: 1023px)';

function getCompactFromMatchMedia(): boolean {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return false;
    }
    return window.matchMedia(COMPACT_VIEWPORT_MEDIA_QUERY).matches;
}

/**
 * True when the layout should use overlay panels instead of fixed side columns
 * (phones and small tablets in portrait/landscape).
 */
export function useCompactViewport(): boolean {
    const [compact, setCompact] = useState(getCompactFromMatchMedia);

    useEffect(() => {
        const mq = window.matchMedia(COMPACT_VIEWPORT_MEDIA_QUERY);
        const onChange = () => setCompact(mq.matches);
        onChange();
        mq.addEventListener('change', onChange);
        return () => mq.removeEventListener('change', onChange);
    }, []);

    return compact;
}
