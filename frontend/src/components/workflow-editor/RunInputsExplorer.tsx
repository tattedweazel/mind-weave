/**
 * One **OutputExplorer**-style card per top-level merged **Inputs** key (`lastRunInputsPayload`).
 */

import { buildClientExplorerForInputField } from '../../domain/clientOutputExplorerForInputField';
import { OutputExplorer } from './OutputExplorer';

export interface RunInputsExplorerProps {
    payload: Record<string, unknown>;
}

export function RunInputsExplorer({ payload }: RunInputsExplorerProps) {
    const keys = Object.keys(payload);

    return (
        <div className="space-y-2">
            {keys.map(fieldKey => {
                const bundle = buildClientExplorerForInputField(fieldKey, payload[fieldKey]);
                return (
                    <OutputExplorer
                        key={`run-in-field-${fieldKey}`}
                        explorer={bundle.explorer}
                        nodeOutput={bundle.nodeOutput}
                        headerClipboardText={bundle.headerClipboardText}
                        headerClipboardAriaLabel={bundle.headerClipboardAriaLabel}
                        expandNoRowsDetail={bundle.expandNoRowsDetail}
                    />
                );
            })}
        </div>
    );
}
