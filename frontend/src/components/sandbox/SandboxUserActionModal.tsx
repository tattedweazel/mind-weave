/**
 * Remote-control modal for sandbox_prompt_user_action brains (simulation ticks only).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ArrowLeft,
    ArrowRight,
    ArrowUp,
    Hand,
    Package,
    Pause,
    Sparkles,
    X,
} from 'lucide-react';

import type { ItemDefinitionRead } from '../../api/types';
import type { SandboxCreatureJson, SandboxFacing, SandboxSandboxStateJson } from '../../domain/sandbox/types';
import {
    forwardCellAllowsPlaceItem,
    forwardCellHasFixture,
    forwardCellKind,
    forwardCellPickable,
    forwardCellPickables,
    forwardCellPlaceBlockedReason,
    runSensoryProbe,
    type NearbyCellItemSummaryJson,
    type SandboxSensoryProbeKind,
} from '../../sandbox/sandboxSensoryProbes';
import { PICK_UP_SELECTION_HINT } from '../../sandbox/sandboxSensoryProbeDisplay';
import type {
    SandboxCreatureUserAction,
    SandboxUserDecisionAction,
} from '../../sandbox/sandboxPromptUserAction';
import { SandboxSensoryProbePanel } from './SandboxSensoryProbePanel';

export interface SandboxUserActionModalProps {
    creature: SandboxCreatureJson;
    sandboxState: SandboxSandboxStateJson;
    creatureIndex: number;
    creatureTotal: number;
    onConfirm: (action: SandboxCreatureUserAction) => void;
    onDismiss: () => void;
    itemDefinitions?: ReadonlyArray<Pick<ItemDefinitionRead, 'id' | 'name' | 'label' | 'default_color'>>;
}

const PROBE_BUTTONS: { kind: SandboxSensoryProbeKind; label: string }[] = [
    { kind: 'nearby', label: 'Nearby' },
    { kind: 'position', label: 'Position' },
    { kind: 'facing', label: 'Facing' },
    { kind: 'inventory', label: 'Inventory' },
];

function facingCompassHighlight(facing: SandboxFacing, direction: 'N' | 'E' | 'S' | 'W'): boolean {
    return facing === direction;
}

function pickableRowLabel(item: NearbyCellItemSummaryJson): string {
    return item.label?.trim() || item.kind;
}

export const SandboxUserActionModal: React.FC<SandboxUserActionModalProps> = ({
    creature,
    sandboxState,
    creatureIndex,
    creatureTotal,
    onConfirm,
    onDismiss,
    itemDefinitions,
}) => {
    const [selectedAction, setSelectedAction] = useState<SandboxUserDecisionAction | null>(null);
    const [selectedInventoryIndex, setSelectedInventoryIndex] = useState<number | null>(null);
    const [selectedPickableItemId, setSelectedPickableItemId] = useState<string | null>(null);
    const [pickUpAll, setPickUpAll] = useState(false);
    const [activeProbe, setActiveProbe] = useState<SandboxSensoryProbeKind | null>(null);
    const [probeCache, setProbeCache] = useState<Partial<Record<SandboxSensoryProbeKind, unknown>>>({});

    const creatureLabel = creature.name?.trim() || creature.id;
    const tick = sandboxState.tick;
    const inventory = creature.inventory ?? [];
    const hasInventory = inventory.length > 0;
    const canPickUp = useMemo(
        () => forwardCellPickable(creature, sandboxState),
        [creature, sandboxState],
    );
    const forwardPickables = useMemo(
        () => forwardCellPickables(creature, sandboxState),
        [creature, sandboxState],
    );
    const canUseFixture = useMemo(
        () => forwardCellHasFixture(creature, sandboxState),
        [creature, sandboxState],
    );
    const forwardKind = useMemo(
        () => forwardCellKind(creature, sandboxState),
        [creature, sandboxState],
    );
    const forwardPlaceAllowed = useMemo(
        () => forwardCellAllowsPlaceItem(creature, sandboxState),
        [creature, sandboxState],
    );
    const forwardPlaceBlockedReason = useMemo(
        () => forwardCellPlaceBlockedReason(creature, sandboxState),
        [creature, sandboxState],
    );

    const openInventoryProbe = useCallback(() => {
        const kind: SandboxSensoryProbeKind = 'inventory';
        if (probeCache[kind] === undefined) {
            const value = runSensoryProbe(kind, creature, sandboxState);
            setProbeCache(prev => ({ ...prev, [kind]: value }));
        }
        setActiveProbe(kind);
    }, [creature, probeCache, sandboxState]);

    const selectAction = useCallback(
        (action: SandboxUserDecisionAction) => {
            setSelectedAction(action);
            if (action !== 'place_item') {
                setSelectedInventoryIndex(null);
            }
            if (action !== 'pick_up_item') {
                setSelectedPickableItemId(null);
                setPickUpAll(false);
            } else {
                setPickUpAll(false);
                const pickables = forwardCellPickables(creature, sandboxState);
                setSelectedPickableItemId(pickables.length === 1 ? (pickables[0]?.id ?? null) : null);
            }
            if (action === 'place_item') {
                setSelectedInventoryIndex(null);
                openInventoryProbe();
            }
        },
        [creature, openInventoryProbe, sandboxState],
    );

    const pickUpNeedsSelection = selectedAction === 'pick_up_item' && forwardPickables.length > 1;
    const pickUpSelectionReady =
        selectedAction === 'pick_up_item' &&
        (forwardPickables.length <= 1 || pickUpAll || selectedPickableItemId != null);

    const confirmDisabled =
        selectedAction == null ||
        (selectedAction === 'place_item' &&
            (selectedInventoryIndex == null || !forwardPlaceAllowed)) ||
        (selectedAction === 'pick_up_item' && !pickUpSelectionReady);

    const handleConfirm = useCallback(() => {
        if (!selectedAction) return;
        const payload: SandboxCreatureUserAction = { action: selectedAction };
        if (selectedAction === 'place_item' && selectedInventoryIndex != null) {
            const entry = inventory[selectedInventoryIndex];
            if (entry) {
                payload.inventory_index = selectedInventoryIndex;
                payload.item_type = entry.type;
            }
        }
        if (selectedAction === 'pick_up_item') {
            if (pickUpAll) {
                payload.pick_all = true;
            } else if (selectedPickableItemId) {
                payload.item_id = selectedPickableItemId;
            }
        }
        onConfirm(payload);
    }, [
        inventory,
        onConfirm,
        pickUpAll,
        selectedAction,
        selectedInventoryIndex,
        selectedPickableItemId,
    ]);

    const toggleProbe = useCallback(
        (kind: SandboxSensoryProbeKind) => {
            if (activeProbe === kind) {
                setActiveProbe(null);
                return;
            }
            if (probeCache[kind] !== undefined) {
                setActiveProbe(kind);
                return;
            }
            const value = runSensoryProbe(kind, creature, sandboxState);
            setProbeCache(prev => ({ ...prev, [kind]: value }));
            setActiveProbe(kind);
        },
        [activeProbe, probeCache, creature, sandboxState],
    );

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement | null;
            if (
                target &&
                (target.tagName === 'INPUT' ||
                    target.tagName === 'TEXTAREA' ||
                    target.tagName === 'SELECT' ||
                    target.isContentEditable)
            ) {
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                onDismiss();
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectAction('move_forward');
                return;
            }
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                selectAction('turn_left');
                return;
            }
            if (e.key === 'ArrowRight') {
                e.preventDefault();
                selectAction('turn_right');
                return;
            }
            if (e.key === ' ' || e.key === 'Spacebar') {
                e.preventDefault();
                selectAction('idle');
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onDismiss, selectAction]);

    const probeButtonClass = (kind: SandboxSensoryProbeKind) => {
        const active = activeProbe === kind;
        return [
            'px-3 py-1.5 text-xs font-medium rounded-lg border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900',
            active
                ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/40 text-teal-800 dark:text-teal-200 shadow-sm shadow-teal-500/20'
                : 'border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:border-teal-500 hover:text-teal-700 dark:hover:text-teal-300',
        ].join(' ');
    };

    const selectClass = (action: SandboxUserDecisionAction, extra?: string) => {
        const active = selectedAction === action;
        return [
            'rounded-xl border transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900',
            active
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 shadow-md shadow-indigo-500/20 scale-[1.02]'
                : 'border-slate-200 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 hover:border-indigo-400 hover:bg-indigo-50/30 dark:hover:bg-indigo-950/20',
            extra ?? '',
        ].join(' ');
    };

    const inventorySelectionMode = selectedAction === 'place_item';

    return (
        <div
            className="fixed inset-0 z-[75] flex items-center justify-center bg-black/50 dark:bg-black/65 backdrop-blur-sm p-4"
            onClick={onDismiss}
            role="presentation"
        >
            <div
                className="mw-card relative w-full max-w-md rounded-2xl border border-slate-200/80 dark:border-slate-600/80 bg-white dark:bg-slate-900 shadow-2xl shadow-black/20 overflow-hidden"
                onClick={e => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-labelledby="sandbox-user-action-title"
            >
                <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 px-5 py-4 text-white">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-indigo-300/90">
                                Remote control · Tick {tick}
                            </p>
                            <h2 id="sandbox-user-action-title" className="text-lg font-semibold truncate">
                                {creatureLabel}
                            </h2>
                            <p className="text-xs text-slate-300 mt-0.5">
                                Creature {creatureIndex + 1} of {creatureTotal} · Facing {creature.facing}
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={onDismiss}
                            className="shrink-0 p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-white/10"
                            aria-label="Close dialog"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                    <div className="mt-3 flex justify-center">
                        <div
                            className="grid grid-cols-3 gap-1 w-[7.5rem] text-[10px] font-mono"
                            aria-hidden
                        >
                            <span />
                            <span
                                className={`text-center py-1 rounded ${
                                    facingCompassHighlight(creature.facing, 'N')
                                        ? 'bg-indigo-500/40 text-white'
                                        : 'text-slate-500'
                                }`}
                            >
                                N
                            </span>
                            <span />
                            <span
                                className={`text-center py-1 rounded ${
                                    facingCompassHighlight(creature.facing, 'W')
                                        ? 'bg-indigo-500/40 text-white'
                                        : 'text-slate-500'
                                }`}
                            >
                                W
                            </span>
                            <span
                                className="flex items-center justify-center w-8 h-8 mx-auto rounded-full bg-indigo-500/30 border border-indigo-400/50"
                                style={
                                    creature.color
                                        ? { boxShadow: `0 0 0 2px ${creature.color}` }
                                        : undefined
                                }
                            />
                            <span
                                className={`text-center py-1 rounded ${
                                    facingCompassHighlight(creature.facing, 'E')
                                        ? 'bg-indigo-500/40 text-white'
                                        : 'text-slate-500'
                                }`}
                            >
                                E
                            </span>
                            <span />
                            <span
                                className={`text-center py-1 rounded ${
                                    facingCompassHighlight(creature.facing, 'S')
                                        ? 'bg-indigo-500/40 text-white'
                                        : 'text-slate-500'
                                }`}
                            >
                                S
                            </span>
                            <span />
                        </div>
                    </div>
                </div>

                <div className="px-5 py-5 space-y-5">
                    <div className="grid grid-cols-3 gap-2 max-w-[14rem] mx-auto" role="group" aria-label="Movement">
                        <span />
                        <button
                            type="button"
                            className={selectClass('move_forward', 'col-start-2 flex flex-col items-center gap-1 py-3')}
                            onClick={() => selectAction('move_forward')}
                            aria-pressed={selectedAction === 'move_forward'}
                        >
                            <ArrowUp className="w-6 h-6" strokeWidth={2.5} />
                            <span className="text-xs font-medium">Forward</span>
                        </button>
                        <span />
                        <button
                            type="button"
                            className={selectClass('turn_left', 'flex flex-col items-center gap-1 py-3')}
                            onClick={() => selectAction('turn_left')}
                            aria-pressed={selectedAction === 'turn_left'}
                        >
                            <ArrowLeft className="w-6 h-6" strokeWidth={2.5} />
                            <span className="text-xs font-medium">Left</span>
                        </button>
                        <button
                            type="button"
                            className={selectClass('idle', 'flex flex-col items-center gap-1 py-3')}
                            onClick={() => selectAction('idle')}
                            aria-pressed={selectedAction === 'idle'}
                        >
                            <Pause className="w-5 h-5" strokeWidth={2.5} />
                            <span className="text-xs font-medium">Idle</span>
                        </button>
                        <button
                            type="button"
                            className={selectClass('turn_right', 'flex flex-col items-center gap-1 py-3')}
                            onClick={() => selectAction('turn_right')}
                            aria-pressed={selectedAction === 'turn_right'}
                        >
                            <ArrowRight className="w-6 h-6" strokeWidth={2.5} />
                            <span className="text-xs font-medium">Right</span>
                        </button>
                    </div>

                    {canPickUp || hasInventory || canUseFixture ? (
                        <div className="flex gap-2 justify-center flex-wrap" role="group" aria-label="Inventory actions">
                            {canUseFixture ? (
                                <button
                                    type="button"
                                    className={selectClass('use_fixture', 'flex items-center gap-2 px-4 py-2.5 text-sm')}
                                    onClick={() => selectAction('use_fixture')}
                                    aria-pressed={selectedAction === 'use_fixture'}
                                >
                                    <Sparkles className="w-4 h-4" />
                                    Use
                                </button>
                            ) : null}
                            {canPickUp ? (
                                <button
                                    type="button"
                                    className={selectClass('pick_up_item', 'flex items-center gap-2 px-4 py-2.5 text-sm')}
                                    onClick={() => selectAction('pick_up_item')}
                                    aria-pressed={selectedAction === 'pick_up_item'}
                                >
                                    <Hand className="w-4 h-4" />
                                    Pick up
                                </button>
                            ) : null}
                            {hasInventory ? (
                                <button
                                    type="button"
                                    className={selectClass('place_item', 'flex items-center gap-2 px-4 py-2.5 text-sm')}
                                    onClick={() => selectAction('place_item')}
                                    aria-pressed={selectedAction === 'place_item'}
                                >
                                    <Package className="w-4 h-4" />
                                    Place
                                </button>
                            ) : null}
                        </div>
                    ) : null}

                    {pickUpNeedsSelection ? (
                        <div>
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                                {PICK_UP_SELECTION_HINT}
                            </p>
                            <ul className="space-y-2" role="listbox" aria-label="Pickable items">
                                {forwardPickables.map(item => (
                                    <li key={item.id} role="option" aria-selected={selectedPickableItemId === item.id}>
                                        <button
                                            type="button"
                                            className={`w-full text-left rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                                                selectedPickableItemId === item.id
                                                    ? 'border-amber-500 bg-amber-50 dark:bg-amber-950/30 ring-1 ring-amber-400/50'
                                                    : 'border-slate-200 dark:border-slate-600 hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/20'
                                            }`}
                                            onClick={() => {
                                                setSelectedPickableItemId(item.id);
                                                setPickUpAll(false);
                                            }}
                                            aria-pressed={selectedPickableItemId === item.id}
                                        >
                                            {pickableRowLabel(item)}
                                        </button>
                                    </li>
                                ))}
                                <li role="option" aria-selected={pickUpAll}>
                                    <button
                                        type="button"
                                        className={`w-full text-left rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                                            pickUpAll
                                                ? 'border-amber-500 bg-amber-50 dark:bg-amber-950/30 ring-1 ring-amber-400/50'
                                                : 'border-slate-200 dark:border-slate-600 hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/20'
                                        }`}
                                        onClick={() => {
                                            setPickUpAll(true);
                                            setSelectedPickableItemId(null);
                                        }}
                                        aria-pressed={pickUpAll}
                                    >
                                        Pick up all
                                    </button>
                                </li>
                            </ul>
                        </div>
                    ) : null}

                    {selectedAction === 'place_item' &&
                    selectedInventoryIndex != null &&
                    forwardPlaceBlockedReason ? (
                        <p className="text-xs text-center text-amber-700 dark:text-amber-300">
                            {forwardPlaceBlockedReason}
                        </p>
                    ) : null}

                    <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
                            Sensory probes
                        </p>
                        <div className="flex flex-wrap gap-2">
                            {PROBE_BUTTONS.map(({ kind, label }) => (
                                <button
                                    key={kind}
                                    type="button"
                                    className={probeButtonClass(kind)}
                                    onClick={() => toggleProbe(kind)}
                                    aria-pressed={activeProbe === kind}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                        {activeProbe != null && probeCache[activeProbe] != null ? (
                            <SandboxSensoryProbePanel
                                kind={activeProbe}
                                value={probeCache[activeProbe]}
                                facing={creature.facing}
                                origin={creature.position}
                                inventorySelectable={inventorySelectionMode && activeProbe === 'inventory'}
                                selectedInventoryIndex={selectedInventoryIndex}
                                onInventorySelect={setSelectedInventoryIndex}
                                itemDefinitions={itemDefinitions}
                            />
                        ) : null}
                    </div>
                </div>

                <div className="flex gap-2 px-5 py-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/50">
                    <button
                        type="button"
                        className="flex-1 px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
                        onClick={onDismiss}
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="flex-1 px-4 py-2.5 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-indigo-600/25"
                        disabled={confirmDisabled}
                        onClick={handleConfirm}
                    >
                        Confirm
                    </button>
                </div>
                <p className="px-5 pb-3 text-[10px] text-center text-slate-400 dark:text-slate-500">
                    ↑ forward · ← → turn · Space idle · Esc cancel
                </p>
            </div>
        </div>
    );
};
