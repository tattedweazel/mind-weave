import React from 'react';

import type { SandboxItemJson } from '../../domain/sandbox/types';
import {
    inspectorDefinitionSummary,
    inspectorSectionTitle,
    inspectorWorkflowLabel,
    type SandboxInspectorDefinitionContext,
} from '../../sandbox/sandboxItemInspectorDisplay';
import { InspectorSection } from '../workflow-editor/InspectorSection';

export interface SandboxFixtureInspectorSectionProps {
    item: SandboxItemJson;
    definitionContext?: SandboxInspectorDefinitionContext;
}

export const SandboxFixtureInspectorSection: React.FC<SandboxFixtureInspectorSectionProps> = ({
    item,
    definitionContext = {},
}) => {
    const def = inspectorDefinitionSummary(item, definitionContext);
    const color = item.color ?? def?.defaultColor ?? null;
    const workflowId = def?.workflowId;
    const instanceLabel = item.label?.trim();

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
                {workflowId ? (
                    <>
                        <div className="text-mw-text-secondary">Workflow</div>
                        <div className="text-mw-text-primary text-right text-[11px] break-words">
                            {inspectorWorkflowLabel(workflowId, definitionContext.workflows)}
                        </div>
                    </>
                ) : null}
                {color ? (
                    <>
                        <div className="text-mw-text-secondary">Color</div>
                        <div className="flex items-center justify-end gap-2">
                            <span
                                className="inline-block h-4 w-4 rounded border border-mw-border shrink-0"
                                style={{ backgroundColor: color }}
                                aria-hidden
                            />
                            <span className="text-mw-text-primary font-mono text-[10px]">{color}</span>
                        </div>
                    </>
                ) : null}
                {instanceLabel ? (
                    <>
                        <div className="text-mw-text-secondary">Instance label</div>
                        <div className="text-mw-text-primary text-right">{instanceLabel}</div>
                    </>
                ) : null}
            </div>
        </InspectorSection>
    );
};
