import React, { useMemo } from 'react';

import type { SandboxFacing, SandboxInventoryItemJson } from '../../domain/sandbox/types';
import {
    inventoryEntryColor,
    inventoryEntryEnergy,
    inventoryEntryTitle,
    type InventoryLabelContext,
} from '../../sandbox/sandboxCreatureInventory';
import {
    forwardRingSlot,
    INVENTORY_SELECTION_HINT,
    nearbyCellKindBadgeClass,
    nearbyCellKindBadgeStyle,
    nearbyCellKindLabel,
    nearbyCellsToRingMap,
    nearbyRegionChipBadgeClass,
    nearbyRegionChipLabel,
    NEARBY_RING_LAYOUT,
    PROBE_HINTS,
    PROBE_LABELS,
    type NearbyRingSlot,
} from '../../sandbox/sandboxSensoryProbeDisplay';
import type { CellProbeJson, NearbyCellJson, SandboxSensoryProbeKind } from '../../sandbox/sandboxSensoryProbes';

export interface SandboxSensoryProbePanelProps {
    kind: SandboxSensoryProbeKind;
    value: unknown;
    /** Creature facing — used to highlight the forward adjacent cell in the nearby ring. */
    facing?: SandboxFacing;
    /** Creature position — used to map nearby cells onto the ring grid. */
    origin?: { x: number; y: number };
    /** When true, inventory rows are selectable (Place item flow). */
    inventorySelectable?: boolean;
    selectedInventoryIndex?: number | null;
    onInventorySelect?: (index: number) => void;
    /** Item definition catalog for definition-aware inventory labels. */
    itemDefinitions?: InventoryLabelContext['itemDefinitions'];
}

function facingCompassHighlight(facing: SandboxFacing, direction: 'N' | 'E' | 'S' | 'W'): boolean {
    return facing === direction;
}

function CellKindBadges({ cell }: { cell: CellProbeJson }) {
    const regionChip = nearbyRegionChipLabel(cell.region_label);
    const kindBadgeStyle = nearbyCellKindBadgeStyle(cell);
    return (
        <>
            <span
                className={
                    kindBadgeStyle
                        ? 'text-[9px] font-semibold leading-none px-1.5 py-0.5 rounded border'
                        : `text-[9px] font-semibold leading-none px-1.5 py-0.5 rounded border ${nearbyCellKindBadgeClass(cell.kind)}`
                }
                style={kindBadgeStyle ?? undefined}
            >
                {nearbyCellKindLabel(cell.kind)}
            </span>
            {regionChip ? (
                <span
                    className={`text-[9px] font-semibold leading-none px-1.5 py-0.5 rounded border ${nearbyRegionChipBadgeClass()}`}
                >
                    {regionChip}
                </span>
            ) : null}
        </>
    );
}

function PositionReadout({ value }: { value: CellProbeJson | { x: number; y: number } }) {
    const hasKind = 'kind' in value && typeof value.kind === 'string';
    if (hasKind) {
        const cell = value as CellProbeJson;
        return (
            <div className="flex justify-center">
                <div className="flex flex-col items-center justify-center gap-0.5 rounded-lg border border-indigo-300/60 dark:border-indigo-500/50 bg-indigo-50/80 dark:bg-indigo-950/30 px-3 py-2 min-w-[5rem]">
                    <CellKindBadges cell={cell} />
                    <span className="text-[9px] font-mono tabular-nums text-slate-500 dark:text-slate-400 leading-none">
                        ({cell.x}, {cell.y})
                    </span>
                </div>
            </div>
        );
    }
    return (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div className="text-slate-500 dark:text-slate-400">X</div>
            <div className="text-right font-mono tabular-nums text-slate-800 dark:text-slate-100">{value.x}</div>
            <div className="text-slate-500 dark:text-slate-400">Y</div>
            <div className="text-right font-mono tabular-nums text-slate-800 dark:text-slate-100">{value.y}</div>
        </div>
    );
}

function FacingReadout({ value }: { value: SandboxFacing }) {
    const directions: Array<'N' | 'E' | 'S' | 'W'> = ['N', 'E', 'S', 'W'];
    return (
        <div className="flex justify-center">
            <div className="grid grid-cols-3 gap-1 w-[7rem] text-xs font-mono" aria-label={`Facing ${value}`}>
                <span />
                <span
                    className={`text-center py-1.5 rounded-md ${
                        facingCompassHighlight(value, 'N')
                            ? 'bg-indigo-500 text-white font-semibold shadow-sm'
                            : 'text-slate-400 dark:text-slate-500'
                    }`}
                >
                    N
                </span>
                <span />
                <span
                    className={`text-center py-1.5 rounded-md ${
                        facingCompassHighlight(value, 'W')
                            ? 'bg-indigo-500 text-white font-semibold shadow-sm'
                            : 'text-slate-400 dark:text-slate-500'
                    }`}
                >
                    W
                </span>
                <span className="flex items-center justify-center w-7 h-7 mx-auto rounded-full bg-indigo-500/20 border border-indigo-400/40 text-[10px] text-indigo-600 dark:text-indigo-300">
                    ·
                </span>
                <span
                    className={`text-center py-1.5 rounded-md ${
                        facingCompassHighlight(value, 'E')
                            ? 'bg-indigo-500 text-white font-semibold shadow-sm'
                            : 'text-slate-400 dark:text-slate-500'
                    }`}
                >
                    E
                </span>
                <span />
                <span
                    className={`text-center py-1.5 rounded-md ${
                        facingCompassHighlight(value, 'S')
                            ? 'bg-indigo-500 text-white font-semibold shadow-sm'
                            : 'text-slate-400 dark:text-slate-500'
                    }`}
                >
                    S
                </span>
                <span />
            </div>
        </div>
    );
}

function InventoryEntryRow({
    entry,
    inventoryLabelContext,
}: {
    entry: SandboxInventoryItemJson;
    inventoryLabelContext?: InventoryLabelContext;
}) {
    const ctx = inventoryLabelContext ?? {};
    const title = inventoryEntryTitle(entry, ctx);
    if (entry.type === 'ball') {
        const hex = inventoryEntryColor(entry, ctx) ?? '#3B82F6';
        return (
            <div className="flex items-center gap-2">
                <span className="font-semibold capitalize" style={{ color: hex }}>
                    {title}
                </span>
                <span
                    className="inline-block h-4 w-4 rounded border border-slate-300/60 dark:border-slate-500/60 shrink-0"
                    style={{ backgroundColor: hex }}
                    aria-label={`${title} color ${hex}`}
                />
            </div>
        );
    }
    const energy = inventoryEntryEnergy(entry, ctx);
    return (
        <div className="flex items-center gap-2">
            <span className="font-semibold text-pink-700 dark:text-pink-300">{title}</span>
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-pink-100 text-pink-800 border-pink-200 dark:bg-pink-950/50 dark:text-pink-200 dark:border-pink-800 tabular-nums">
                Energy {energy ?? '?'}
            </span>
        </div>
    );
}

function InventoryReadout({
    value,
    selectable,
    selectedIndex,
    onSelect,
    inventoryLabelContext,
}: {
    value: SandboxInventoryItemJson[];
    selectable?: boolean;
    selectedIndex?: number | null;
    onSelect?: (index: number) => void;
    inventoryLabelContext?: InventoryLabelContext;
}) {
    if (value.length === 0) {
        return <p className="text-xs text-slate-500 dark:text-slate-400">Empty</p>;
    }
    return (
        <ul className="space-y-2" role={selectable ? 'listbox' : undefined} aria-label={selectable ? 'Inventory items' : undefined}>
            {value.map((entry, idx) => {
                const selected = selectable && selectedIndex === idx;
                const content = (
                    <InventoryEntryRow entry={entry} inventoryLabelContext={inventoryLabelContext} />
                );
                if (!selectable) {
                    return (
                        <li
                            key={`inv-${idx}-${entry.type}`}
                            className="rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2 text-xs bg-white/60 dark:bg-slate-900/40"
                        >
                            {content}
                        </li>
                    );
                }
                return (
                    <li key={`inv-${idx}-${entry.type}`} role="option" aria-selected={selected}>
                        <button
                            type="button"
                            className={`w-full rounded-lg border px-3 py-2 text-xs text-left transition-colors ${
                                selected
                                    ? 'border-amber-500 bg-amber-50 dark:bg-amber-950/30 ring-1 ring-amber-400/50'
                                    : 'border-slate-200 dark:border-slate-600 bg-white/60 dark:bg-slate-900/40 hover:border-amber-400'
                            }`}
                            onClick={() => onSelect?.(idx)}
                            aria-pressed={selected}
                        >
                            {content}
                        </button>
                    </li>
                );
            })}
        </ul>
    );
}

function NearbyCellTile({
    cell,
    isForward,
}: {
    cell: NearbyCellJson;
    isForward: boolean;
}) {
    return (
        <div
            className={`flex flex-col items-center justify-center gap-0.5 rounded-lg border px-1 py-1.5 min-h-[3.25rem] ${
                isForward
                    ? 'border-teal-400 dark:border-teal-500 ring-1 ring-teal-400/50 dark:ring-teal-500/40 bg-teal-50/50 dark:bg-teal-950/20'
                    : 'border-slate-200/80 dark:border-slate-600/80 bg-white/50 dark:bg-slate-900/30'
            }`}
        >
            <CellKindBadges cell={cell} />
            <span className="text-[9px] font-mono tabular-nums text-slate-500 dark:text-slate-400 leading-none">
                ({cell.x}, {cell.y})
            </span>
        </div>
    );
}

function NearbyReadout({
    value,
    facing,
    origin,
}: {
    value: NearbyCellJson[];
    facing?: SandboxFacing;
    origin?: { x: number; y: number };
}) {
    const ringMap = useMemo(() => {
        if (!origin) return {};
        return nearbyCellsToRingMap(value, origin);
    }, [origin, value]);

    const forwardSlot = facing ? forwardRingSlot(facing) : null;

    const renderSlot = (slot: NearbyRingSlot | 'center') => {
        if (slot === 'center') {
            return (
                <div
                    key="center"
                    className="flex items-center justify-center rounded-lg border border-indigo-300/60 dark:border-indigo-500/50 bg-indigo-50/80 dark:bg-indigo-950/30 min-h-[3.25rem]"
                >
                    <span className="text-[10px] font-semibold text-indigo-700 dark:text-indigo-300">You</span>
                </div>
            );
        }
        const cell = ringMap[slot];
        if (!cell) {
            return <div key={slot} className="min-h-[3.25rem]" aria-hidden />;
        }
        return (
            <NearbyCellTile
                key={slot}
                cell={cell}
                isForward={forwardSlot === slot}
            />
        );
    };

    return (
        <div className="grid grid-cols-3 gap-1.5 max-w-[14rem] mx-auto">
            {NEARBY_RING_LAYOUT.map(slot => renderSlot(slot))}
        </div>
    );
}

function StructuredReadout({
    kind,
    value,
    facing,
    origin,
    inventorySelectable,
    selectedInventoryIndex,
    onInventorySelect,
    itemDefinitions,
}: SandboxSensoryProbePanelProps) {
    const inventoryLabelContext = useMemo(
        (): InventoryLabelContext => ({ itemDefinitions }),
        [itemDefinitions],
    );
    switch (kind) {
        case 'position':
            if (value && typeof value === 'object' && 'x' in value && 'y' in value) {
                return <PositionReadout value={value as CellProbeJson | { x: number; y: number }} />;
            }
            return null;
        case 'facing':
            if (typeof value === 'string' && ['N', 'E', 'S', 'W'].includes(value)) {
                return <FacingReadout value={value as SandboxFacing} />;
            }
            return null;
        case 'inventory':
            if (Array.isArray(value)) {
                return (
                    <InventoryReadout
                        value={value as SandboxInventoryItemJson[]}
                        selectable={inventorySelectable}
                        selectedIndex={selectedInventoryIndex}
                        onSelect={onInventorySelect}
                        inventoryLabelContext={inventoryLabelContext}
                    />
                );
            }
            return null;
        case 'nearby':
            if (Array.isArray(value)) {
                return (
                    <NearbyReadout
                        value={value as NearbyCellJson[]}
                        facing={facing}
                        origin={origin}
                    />
                );
            }
            return null;
        default:
            return null;
    }
}

export const SandboxSensoryProbePanel: React.FC<SandboxSensoryProbePanelProps> = ({
    kind,
    value,
    facing,
    origin,
    inventorySelectable,
    selectedInventoryIndex,
    onInventorySelect,
    itemDefinitions,
}) => {
    const rawJson = useMemo(() => {
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value);
        }
    }, [value]);

    const hint =
        kind === 'inventory' && inventorySelectable ? INVENTORY_SELECTION_HINT : PROBE_HINTS[kind];

    return (
        <div
            className="mt-3 rounded-xl border border-slate-200/80 dark:border-slate-600/80 bg-slate-50/80 dark:bg-slate-800/40 p-3 space-y-3"
            data-testid="sensory-probe-panel"
        >
            <div>
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-100">{PROBE_LABELS[kind]}</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">{hint}</p>
            </div>
            <StructuredReadout
                kind={kind}
                value={value}
                facing={facing}
                origin={origin}
                inventorySelectable={inventorySelectable}
                selectedInventoryIndex={selectedInventoryIndex}
                onInventorySelect={onInventorySelect}
                itemDefinitions={itemDefinitions}
            />
            <details className="group">
                <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 select-none">
                    Raw JSON
                </summary>
                <pre className="mt-2 max-h-32 overflow-auto text-[10px] leading-relaxed font-mono p-2 rounded-lg bg-slate-100 dark:bg-slate-900/60 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                    {rawJson}
                </pre>
            </details>
        </div>
    );
};
