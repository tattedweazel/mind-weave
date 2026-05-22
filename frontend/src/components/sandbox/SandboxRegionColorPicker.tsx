import React from 'react';

import { normalizeHexColor } from '../../sandbox/sandboxColorUtils';
import { REGION_PRESET_COLORS } from '../../sandbox/sandboxVisualDefaults';

export interface SandboxRegionColorPickerProps {
    value: string;
    favoriteColors?: string[];
    onChange: (color: string) => void;
    onConfirm: (color: string) => void;
    showConfirmButton?: boolean;
    confirmLabel?: string;
}

function SwatchButton({
    color,
    selected,
    onClick,
    label,
}: {
    color: string;
    selected: boolean;
    onClick: () => void;
    label: string;
}) {
    return (
        <button
            type="button"
            aria-label={label}
            title={label}
            onClick={onClick}
            className={`h-8 w-8 rounded-md border-2 shrink-0 transition-transform hover:scale-105 ${
                selected ? 'border-sky-500 ring-2 ring-sky-400/50' : 'border-slate-300 dark:border-slate-600'
            }`}
            style={{ backgroundColor: color }}
        />
    );
}

export const SandboxRegionColorPicker: React.FC<SandboxRegionColorPickerProps> = ({
    value,
    favoriteColors = [],
    onChange,
    onConfirm,
    showConfirmButton = true,
    confirmLabel,
}) => {
    const [customDraft, setCustomDraft] = React.useState(value.replace(/^#/, ''));

    React.useEffect(() => {
        setCustomDraft(value.replace(/^#/, ''));
    }, [value]);

    const selectColor = (raw: string) => {
        const normalized = normalizeHexColor(raw.startsWith('#') ? raw : `#${raw}`);
        if (normalized) {
            onChange(normalized);
        }
    };

    const commitCustom = () => {
        const normalized = normalizeHexColor(`#${customDraft.trim()}`);
        if (normalized) {
            onChange(normalized);
            onConfirm(normalized);
        }
    };

    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                    Presets
                </p>
                <div className="flex flex-wrap gap-2">
                    {REGION_PRESET_COLORS.map(c => (
                        <SwatchButton
                            key={c}
                            color={c}
                            selected={value === c}
                            label={`Preset ${c}`}
                            onClick={() => selectColor(c)}
                        />
                    ))}
                </div>
            </div>
            {favoriteColors.length > 0 ? (
                <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                        Favorites
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {favoriteColors.map(c => (
                            <SwatchButton
                                key={c}
                                color={c}
                                selected={value === c}
                                label={`Favorite ${c}`}
                                onClick={() => selectColor(c)}
                            />
                        ))}
                    </div>
                </div>
            ) : null}
            <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                    Custom hex
                </p>
                <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-500">#</span>
                    <input
                        type="text"
                        value={customDraft}
                        onChange={e => setCustomDraft(e.target.value.replace(/[^0-9A-Fa-f]/g, '').slice(0, 6))}
                        onKeyDown={e => {
                            if (e.key === 'Enter') {
                                e.preventDefault();
                                commitCustom();
                            }
                        }}
                        className="flex-1 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono uppercase"
                        placeholder="3B82F6"
                        maxLength={6}
                    />
                    <div
                        className="h-9 w-9 rounded-md border border-slate-300 dark:border-slate-600 shrink-0"
                        style={{ backgroundColor: normalizeHexColor(`#${customDraft}`) ?? value }}
                        aria-hidden
                    />
                </div>
            </div>
            {showConfirmButton ? (
                <button
                    type="button"
                    onClick={() => onConfirm(value)}
                    className="w-full rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium py-2.5"
                >
                    {confirmLabel ?? `Place region (${value})`}
                </button>
            ) : null}
        </div>
    );
};
