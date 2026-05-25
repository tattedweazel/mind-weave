import React from 'react';

import type { ItemDefinitionRead } from '../../api/types';
import type {
    BoardDefinitionJson,
    SandboxCreatureJson,
    SandboxInventoryItemType,
} from '../../domain/sandbox/types';
import {
    formatInventoryEntryLabel,
    patchBoardCreatureInventoryEntry,
    removeBoardCreatureInventoryEntry,
} from '../../sandbox/sandboxCreatureInventory';
import { InspectorSection } from '../workflow-editor/InspectorSection';

export interface SandboxCreatureInventorySectionProps {
    creature: SandboxCreatureJson;
    readOnly: boolean;
    onBoardChange?: (updater: (def: BoardDefinitionJson) => BoardDefinitionJson) => void;
    onAddEntry?: (type: SandboxInventoryItemType) => void;
    itemDefinitions?: ReadonlyArray<Pick<ItemDefinitionRead, 'id' | 'name' | 'label' | 'default_color'>>;
}

export const SandboxCreatureInventorySection: React.FC<SandboxCreatureInventorySectionProps> = ({
    creature,
    readOnly,
    onBoardChange,
    onAddEntry,
    itemDefinitions,
}) => {
    const inventory = creature.inventory ?? [];
    const labelContext = { itemDefinitions };

    return (
        <InspectorSection title="Inventory">
            {inventory.length === 0 ? (
                <p className="text-xs text-mw-text-secondary">Empty</p>
            ) : (
                <ul className="space-y-2">
                    {inventory.map((entry, idx) => (
                        <li
                            key={`${creature.id}-inv-${idx}`}
                            className="rounded-lg border border-mw-border px-2 py-2 text-xs"
                        >
                            <div className="flex items-center justify-between gap-2">
                                <span className="font-medium text-mw-text-primary">
                                    {formatInventoryEntryLabel(entry, labelContext)}
                                </span>
                                {!readOnly && onBoardChange ? (
                                    <button
                                        type="button"
                                        className="text-[10px] text-red-600 hover:underline shrink-0"
                                        onClick={() =>
                                            onBoardChange(def =>
                                                removeBoardCreatureInventoryEntry(def, creature.id, idx),
                                            )
                                        }
                                    >
                                        Remove
                                    </button>
                                ) : null}
                            </div>
                            {!readOnly && onBoardChange && entry.type === 'food' ? (
                                <label className="mt-2 block">
                                    <span className="text-mw-text-secondary">Energy</span>
                                    <input
                                        type="number"
                                        min={0}
                                        step={1}
                                        defaultValue={entry.energy ?? 0}
                                        className="mt-1 w-full px-2 py-1 border border-mw-border rounded text-mw-text-primary tabular-nums"
                                        onBlur={e => {
                                            const parsed = Number(e.target.value);
                                            if (!Number.isInteger(parsed) || parsed < 0) return;
                                            onBoardChange(def =>
                                                patchBoardCreatureInventoryEntry(def, creature.id, idx, {
                                                    energy: parsed,
                                                }),
                                            );
                                        }}
                                    />
                                </label>
                            ) : null}
                            {!readOnly && onBoardChange && entry.type === 'ball' ? (
                                <label className="mt-2 block">
                                    <span className="text-mw-text-secondary">Color (#RRGGBB)</span>
                                    <input
                                        type="text"
                                        defaultValue={entry.color ?? ''}
                                        className="mt-1 w-full px-2 py-1 border border-mw-border rounded font-mono text-[10px] text-mw-text-primary"
                                        onBlur={e => {
                                            onBoardChange(def =>
                                                patchBoardCreatureInventoryEntry(def, creature.id, idx, {
                                                    color: e.target.value,
                                                }),
                                            );
                                        }}
                                    />
                                </label>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
            {!readOnly && onAddEntry ? (
                <div className="flex gap-2 mt-2">
                    <button
                        type="button"
                        className="text-xs px-2 py-1 rounded border border-mw-border hover:border-mw-primary"
                        onClick={() => onAddEntry('ball')}
                    >
                        Add ball
                    </button>
                    <button
                        type="button"
                        className="text-xs px-2 py-1 rounded border border-mw-border hover:border-mw-primary"
                        onClick={() => onAddEntry('food')}
                    >
                        Add food
                    </button>
                </div>
            ) : null}
        </InspectorSection>
    );
};
