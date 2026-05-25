import React, { useMemo } from 'react';

import type { ItemDefinitionRead } from '../../api/types';

export interface SandboxItemDefinitionFieldProps {
    id: string;
    value: string;
    onChange: (definitionId: string) => void;
    itemDefinitions: readonly ItemDefinitionRead[];
    disabled?: boolean;
}

/** Item definition picker: dropdown of known definitions plus manual UUID override. */
export const SandboxItemDefinitionField: React.FC<SandboxItemDefinitionFieldProps> = ({
    id,
    value,
    onChange,
    itemDefinitions,
    disabled = false,
}) => {
    const listedIds = useMemo(() => new Set(itemDefinitions.map(d => d.id)), [itemDefinitions]);
    const selectValue = value && listedIds.has(value) ? value : '';

    return (
        <div className="space-y-2">
            <div>
                <label htmlFor={`${id}-select`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                    Item definition
                </label>
                <select
                    id={`${id}-select`}
                    value={selectValue}
                    disabled={disabled || itemDefinitions.length === 0}
                    onChange={e => onChange(e.target.value)}
                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                >
                    <option value="">
                        {itemDefinitions.length === 0 ? 'No item definitions loaded' : 'Select an item definition…'}
                    </option>
                    {itemDefinitions.map(def => (
                        <option key={def.id} value={def.id}>
                            {def.label || def.name || def.id}
                        </option>
                    ))}
                </select>
            </div>
            <div>
                <label htmlFor={`${id}-manual`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                    Definition ID (manual override)
                </label>
                <input
                    id={`${id}-manual`}
                    type="text"
                    value={value}
                    disabled={disabled}
                    onChange={e => onChange(e.target.value)}
                    placeholder="Paste UUID from Definitions tab"
                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg font-mono focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
            </div>
        </div>
    );
};
