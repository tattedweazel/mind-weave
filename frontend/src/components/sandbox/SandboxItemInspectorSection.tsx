import React from 'react';

import type { SandboxItemJson } from '../../domain/sandbox/types';
import {
    getEditableItemFields,
    getItemFieldValue,
    validateItemFieldValue,
} from '../../sandbox/sandboxItemInspectorFields';
import { InspectorSection } from '../workflow-editor/InspectorSection';

export interface SandboxItemInspectorSectionProps {
    item: SandboxItemJson;
    readOnly: boolean;
    onItemChange?: (itemId: string, patch: Partial<Pick<SandboxItemJson, 'energy'>>) => void;
}

function EditableIntegerField({
    item,
    field,
    onItemChange,
}: {
    item: SandboxItemJson;
    field: ReturnType<typeof getEditableItemFields>[number];
    onItemChange?: SandboxItemInspectorSectionProps['onItemChange'];
}) {
    const committed = getItemFieldValue(item, field.key);
    const [draft, setDraft] = React.useState(() => (committed != null ? String(committed) : ''));

    React.useEffect(() => {
        setDraft(committed != null ? String(committed) : '');
    }, [item.id, field.key, committed]);

    const commit = (rawValue: string) => {
        const validated = validateItemFieldValue(field, rawValue);
        if (validated == null) {
            setDraft(committed != null ? String(committed) : '');
            return;
        }
        setDraft(String(validated));
        if (validated !== committed) {
            onItemChange?.(item.id, { [field.key]: validated });
        }
    };

    return (
        <div>
            <label htmlFor={`${item.id}-${field.key}`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                {field.label}
            </label>
            {field.description ? (
                <p className="text-[11px] text-mw-text-secondary mb-1">{field.description}</p>
            ) : null}
            <input
                id={`${item.id}-${field.key}`}
                type="number"
                min={field.min}
                max={field.max}
                step={1}
                value={draft}
                onChange={e => {
                    setDraft(e.target.value);
                    const validated = validateItemFieldValue(field, e.target.value);
                    if (validated != null && validated !== committed) {
                        onItemChange?.(item.id, { [field.key]: validated });
                    }
                }}
                onBlur={() => commit(draft)}
                className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card text-mw-text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-mw-primary tabular-nums"
            />
        </div>
    );
}

export const SandboxItemInspectorSection: React.FC<SandboxItemInspectorSectionProps> = ({
    item,
    readOnly,
    onItemChange,
}) => {
    const editableFields = getEditableItemFields(item.type);

    return (
        <InspectorSection title={`Item (${item.type})`}>
            <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-mw-text-secondary">Id</div>
                <div className="text-mw-text-primary text-right font-mono text-[10px] break-all">{item.id}</div>
                <div className="text-mw-text-secondary">Type</div>
                <div className="text-mw-text-primary text-right font-mono">{item.type}</div>
                <div className="text-mw-text-secondary">Position</div>
                <div className="text-mw-text-primary tabular-nums text-right font-mono">
                    ({item.position.x}, {item.position.y})
                </div>
                {item.type === 'ball' && item.color ? (
                    <>
                        <div className="text-mw-text-secondary">Color</div>
                        <div className="flex items-center justify-end gap-2">
                            <span
                                className="inline-block h-4 w-4 rounded border border-mw-border shrink-0"
                                style={{ backgroundColor: item.color }}
                                aria-hidden
                            />
                            <span className="text-mw-text-primary font-mono text-[10px]">{item.color}</span>
                        </div>
                    </>
                ) : null}
                {readOnly
                    ? editableFields.map(field => {
                          const value = getItemFieldValue(item, field.key);
                          return value != null ? (
                              <React.Fragment key={field.key}>
                                  <div className="text-mw-text-secondary">{field.label}</div>
                                  <div className="text-mw-text-primary tabular-nums text-right">{value}</div>
                              </React.Fragment>
                          ) : null;
                      })
                    : null}
            </div>
            {!readOnly
                ? editableFields.map(field => (
                      <EditableIntegerField key={field.key} item={item} field={field} onItemChange={onItemChange} />
                  ))
                : null}
        </InspectorSection>
    );
};
