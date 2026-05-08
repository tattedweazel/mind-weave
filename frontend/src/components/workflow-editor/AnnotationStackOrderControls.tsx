export type AnnotationStackKind = 'note' | 'region';

export interface AnnotationStackOrderControlsProps {
    kind: AnnotationStackKind;
    onMoveBack: () => void;
    onMoveForward: () => void;
}

const COPY: Record<AnnotationStackKind, { body: string }> = {
    note: {
        body: 'When notes overlap, higher order draws on top. Notes stay above regions; edges stay on top.',
    },
    region: {
        body: 'When regions overlap, higher order draws on top. Regions stay behind workflow notes on the canvas.',
    },
};

/** Explorer stack controls for annotation notes and regions (shared copy + layout). */
export function AnnotationStackOrderControls({
    kind,
    onMoveBack,
    onMoveForward,
}: AnnotationStackOrderControlsProps) {
    const { body } = COPY[kind];
    return (
        <div>
            <label className="text-xs font-medium text-mw-text-secondary block mb-1">Stack order</label>
            <p className="text-[11px] text-mw-text-secondary mb-2">{body}</p>
            <div className="flex flex-wrap gap-2">
                <button
                    type="button"
                    className="px-3 py-1.5 text-sm rounded-lg border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-page focus:outline-none focus:ring-2 focus:ring-mw-primary"
                    onClick={onMoveBack}
                >
                    Move back
                </button>
                <button
                    type="button"
                    className="px-3 py-1.5 text-sm rounded-lg border border-mw-border bg-mw-card text-mw-text-primary hover:bg-mw-page focus:outline-none focus:ring-2 focus:ring-mw-primary"
                    onClick={onMoveForward}
                >
                    Move forward
                </button>
            </div>
        </div>
    );
}
