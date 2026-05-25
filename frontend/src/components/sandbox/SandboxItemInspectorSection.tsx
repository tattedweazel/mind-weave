import React from 'react';

import type { SandboxItemJson } from '../../domain/sandbox/types';
import {
    getEditableItemFields,
    getItemFieldValue,
    validateItemFieldValue,
} from '../../sandbox/sandboxItemInspectorFields';
import {
    inspectorBuiltinTypeLabel,
    inspectorDefinitionSummary,
    inspectorSectionTitle,
    toItemRenderCatalog,
    type SandboxInspectorDefinitionContext,
} from '../../sandbox/sandboxItemInspectorDisplay';
import { isPickableItem } from '../../sandbox/sandboxItemResolve';
import { resolvePickableVisual } from '../../sandbox/sandboxItemRender';
import { InspectorSection } from '../workflow-editor/InspectorSection';

export interface SandboxItemInspectorSectionProps {
    item: SandboxItemJson;
    readOnly: boolean;
    definitionContext?: SandboxInspectorDefinitionContext;
    onItemChange?: (itemId: string, patch: Partial<Pick<SandboxItemJson, 'energy'>>) => void;
}

function EditableIntegerField({
    item,
    field,
    definitionContext,
    onItemChange,
}: {
    item: SandboxItemJson;
    field: ReturnType<typeof getEditableItemFields>[number];
    definitionContext: SandboxInspectorDefinitionContext;
    onItemChange?: SandboxItemInspectorSectionProps['onItemChange'];
}) {
    const committed = getItemFieldValue(item, field.key, definitionContext);
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
    definitionContext = {},
    onItemChange,
}) => {
    const def = inspectorDefinitionSummary(item, definitionContext);
    const builtinType = inspectorBuiltinTypeLabel(item);
    const editableFields = getEditableItemFields(item, definitionContext);
    const renderCatalog = toItemRenderCatalog(definitionContext);
    const visual = isPickableItem(item) ? resolvePickableVisual(item, renderCatalog) : null;
    const showColor = visual != null && (visual.isBall || item.color != null || def?.defaultColor != null);

    return (
        <InspectorSection title={inspectorSectionTitle(item, definitionContext)}>
            <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-mw-text-secondary">Id</div>
                <div className="text-mw-text-primary text-right font-mono text-[10px] break-all">{item.id}</div>
                <div className="text-mw-text-secondary">Position</div>
                <div className="text-mw-text-primary tabular-nums text-right font-mono">
                    ({item.position.x}, {item.position.y})
                </div>
                {def ? (
                    <>
                        <div className="text-mw-text-secondary">Definition</div>
                        <div className="text-mw-text-primary text-right">
                            <span className="block font-medium">{def.label}</span>
                            <span className="block font-mono text-[10px] text-mw-text-secondary">{def.name}</span>
                        </div>
                    </>
                ) : null}
                {builtinType ? (
                    <>
                        <div className="text-mw-text-secondary">Type</div>
                        <div className="text-mw-text-primary text-right">{builtinType}</div>
                    </>
                ) : null}
                {isPickableItem(item) ? (
                    <>
                        <div className="text-mw-text-secondary">Role</div>
                        <div className="text-mw-text-primary text-right capitalize">Pickable</div>
                    </>
                ) : null}
                {def?.shape ? (
                    <>
                        <div className="text-mw-text-secondary">Shape</div>
                        <div className="text-mw-text-primary text-right capitalize">{def.shape}</div>
                    </>
                ) : null}
                {showColor && visual ? (
                    <>
                        <div className="text-mw-text-secondary">Color</div>
                        <div className="flex items-center justify-end gap-2">
                            <span
                                className="inline-block h-4 w-4 rounded border border-mw-border shrink-0"
                                style={{ backgroundColor: visual.color }}
                                aria-hidden
                            />
                            <span className="text-mw-text-primary font-mono text-[10px]">{visual.color}</span>
                        </div>
                    </>
                ) : null}
                {readOnly
                    ? editableFields.map(field => {
                          const value = getItemFieldValue(item, field.key, definitionContext);
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
                      <EditableIntegerField
                          key={field.key}
                          item={item}
                          field={field}
                          definitionContext={definitionContext}
                          onItemChange={onItemChange}
                      />
                  ))
                : null}
        </InspectorSection>
    );
};
