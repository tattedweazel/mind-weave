import React from 'react';

import type { WorkflowDefinitionListItem } from '../../api/types';
import type { RegionTriggerConfigJson, SandboxItemJson } from '../../domain/sandbox/types';
import { regionTriggerFromItem } from '../../sandbox/sandboxItemInspectorFields';
import { SandboxColorPicker } from './SandboxColorPicker';
import { InspectorSection } from '../workflow-editor/InspectorSection';

export interface SandboxRegionInspectorSectionProps {
    item: SandboxItemJson;
    readOnly: boolean;
    favoriteColors?: string[];
    workflows?: WorkflowDefinitionListItem[];
    onItemChange?: (
        itemId: string,
        patch: Partial<Pick<SandboxItemJson, 'color' | 'trigger'>>,
    ) => void;
}

export const SandboxRegionInspectorSection: React.FC<SandboxRegionInspectorSectionProps> = ({
    item,
    readOnly,
    favoriteColors = [],
    workflows = [],
    onItemChange,
}) => {
    const trigger = regionTriggerFromItem(item);
    const color = item.color ?? '#3B82F6';
    const [inputsDraft, setInputsDraft] = React.useState(() => JSON.stringify(trigger.inputs ?? {}, null, 2));
    const [inputsError, setInputsError] = React.useState<string | null>(null);

    React.useEffect(() => {
        setInputsDraft(JSON.stringify(trigger.inputs ?? {}, null, 2));
        setInputsError(null);
    }, [item.id, trigger.inputs]);

    const patchTrigger = (partial: Partial<RegionTriggerConfigJson>) => {
        onItemChange?.(item.id, {
            trigger: { ...trigger, ...partial },
        });
    };

    const commitInputs = () => {
        try {
            const parsed: unknown = JSON.parse(inputsDraft.trim() || '{}');
            if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
                setInputsError('Must be a JSON object');
                return;
            }
            setInputsError(null);
            patchTrigger({ inputs: parsed as Record<string, unknown> });
        } catch {
            setInputsError('Invalid JSON');
        }
    };

    return (
        <InspectorSection title="Region">
            <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                <div className="text-mw-text-secondary">Id</div>
                <div className="text-mw-text-primary text-right font-mono text-[10px] break-all">{item.id}</div>
                <div className="text-mw-text-secondary">Position</div>
                <div className="text-mw-text-primary tabular-nums text-right font-mono">
                    ({item.position.x}, {item.position.y})
                </div>
            </div>
            {readOnly ? (
                <>
                    <div className="text-xs text-mw-text-secondary mb-1">Color</div>
                    <div className="flex items-center gap-2 mb-3">
                        <div className="h-6 w-6 rounded border border-mw-border" style={{ backgroundColor: color }} />
                        <span className="font-mono text-xs">{color}</span>
                    </div>
                </>
            ) : (
                <div className="mb-4">
                    <SandboxColorPicker
                        value={color}
                        favoriteColors={favoriteColors}
                        onChange={next => onItemChange?.(item.id, { color: next })}
                        onConfirm={next => onItemChange?.(item.id, { color: next })}
                        showConfirmButton={false}
                    />
                </div>
            )}
            <p className="text-[11px] text-mw-text-secondary mb-3 leading-relaxed">
                Trigger behavior is not executed yet; configuration is saved for future use.
            </p>
            <div className="space-y-3 border-t border-mw-border pt-3">
                <div className="flex items-center gap-2">
                    <input
                        id={`${item.id}-trigger-enabled`}
                        type="checkbox"
                        checked={trigger.enabled}
                        disabled={readOnly}
                        onChange={e =>
                            patchTrigger({
                                enabled: e.target.checked,
                                mode: e.target.checked ? trigger.mode ?? 'enter' : null,
                            })
                        }
                        className="h-4 w-4 rounded border-mw-border"
                    />
                    <label htmlFor={`${item.id}-trigger-enabled`} className="text-xs font-medium text-mw-text-primary">
                        Trigger enabled
                    </label>
                </div>
                {trigger.enabled ? (
                    <>
                        <div>
                            <label htmlFor={`${item.id}-trigger-mode`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                                Trigger mode
                            </label>
                            <select
                                id={`${item.id}-trigger-mode`}
                                value={trigger.mode ?? 'enter'}
                                disabled={readOnly}
                                onChange={e =>
                                    patchTrigger({
                                        mode: e.target.value as RegionTriggerConfigJson['mode'],
                                    })
                                }
                                className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card rounded-lg"
                            >
                                {REGION_TRIGGER_MODES.map(m => (
                                    <option key={m.value} value={m.value}>
                                        {m.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label htmlFor={`${item.id}-trigger-workflow`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                                Workflow
                            </label>
                            <select
                                id={`${item.id}-trigger-workflow`}
                                value={trigger.workflow_id ?? ''}
                                disabled={readOnly}
                                onChange={e =>
                                    patchTrigger({
                                        workflow_id: e.target.value.trim() === '' ? null : e.target.value,
                                    })
                                }
                                className="w-full px-2 py-1.5 text-sm border border-mw-border bg-mw-card rounded-lg"
                            >
                                <option value="">None</option>
                                {workflows.map(wf => (
                                    <option key={wf.id} value={wf.id}>
                                        {wf.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label htmlFor={`${item.id}-trigger-inputs`} className="text-xs font-medium text-mw-text-secondary block mb-1">
                                Workflow inputs (JSON)
                            </label>
                            <textarea
                                id={`${item.id}-trigger-inputs`}
                                value={inputsDraft}
                                readOnly={readOnly}
                                onChange={e => setInputsDraft(e.target.value)}
                                onBlur={() => !readOnly && commitInputs()}
                                rows={4}
                                className="w-full px-2 py-1.5 text-xs font-mono border border-mw-border bg-mw-card rounded-lg"
                            />
                            {inputsError ? (
                                <p className="text-[11px] text-mw-error mt-1">{inputsError}</p>
                            ) : null}
                        </div>
                    </>
                ) : null}
            </div>
        </InspectorSection>
    );
};
