/**
 * Props for [`OutputExplorer`](../components/workflow-editor/OutputExplorer.tsx) when rendering
 * Last Run / Run logs **Output** from backend `output_explorer` + serialized `nodeOutput`.
 * **`expandNoRowsDetail`**: empty `items` (scalar shells) get per-kind payloads; when `items` has rows,
 * the full serialized `nodeOutput` is supplied so the card header matches **Inputs** (open full output in the modal).
 */

import type { OutputExplorerV1 } from '../api/types';
import type { OutputExplorerExpandNoRowsDetail } from './clientOutputExplorerForInputField';
import { formatValueForPrimitiveClipboard } from './formatValueForPrimitiveClipboard';

export type OutputExplorerRunRowExtras = {
    expandNoRowsDetail?: OutputExplorerExpandNoRowsDetail;
    headerClipboardText?: string;
    headerClipboardAriaLabel?: string;
};

function asRecord(v: unknown): Record<string, unknown> | null {
    return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

const HEADER_COPY_ARIA = 'Copy output value';

const FULL_OUTPUT_SUBTITLE = 'Full output';

/**
 * Derive optional `expandNoRowsDetail` and header **Copy** for Last Run **Output** explorer cards.
 */
export function outputExplorerRunRowExtras(explorer: OutputExplorerV1, nodeOutput: unknown): OutputExplorerRunRowExtras {
    if (explorer.items.length > 0) {
        const title = explorer.summary.line.trim() || 'Output';
        return {
            expandNoRowsDetail: { payload: nodeOutput, title, subtitle: FULL_OUTPUT_SUBTITLE },
        };
    }
    const root = asRecord(nodeOutput);
    if (!root) {
        return {};
    }
    const nk = root.kind;
    const title = explorer.summary.line.trim() || 'Output';

    if (explorer.kind === 'string_primitive' && nk === 'string' && typeof root.text === 'string') {
        const text = root.text;
        return {
            expandNoRowsDetail: { payload: text, title, subtitle: 'string' },
            headerClipboardText: formatValueForPrimitiveClipboard(text, 'string'),
            headerClipboardAriaLabel: HEADER_COPY_ARIA,
        };
    }

    if (explorer.kind === 'int_primitive' && nk === 'int' && typeof root.value === 'number' && Number.isFinite(root.value)) {
        const n = root.value;
        const subtitle = Number.isInteger(n) ? 'int' : 'number';
        return {
            expandNoRowsDetail: { payload: n, title, subtitle },
            headerClipboardText: formatValueForPrimitiveClipboard(n, subtitle),
            headerClipboardAriaLabel: HEADER_COPY_ARIA,
        };
    }

    if (explorer.kind === 'boolean_primitive' && nk === 'boolean' && typeof root.value === 'boolean') {
        const v = root.value;
        return {
            expandNoRowsDetail: { payload: v, title, subtitle: 'boolean' },
            headerClipboardText: formatValueForPrimitiveClipboard(v, 'boolean'),
            headerClipboardAriaLabel: HEADER_COPY_ARIA,
        };
    }

    if (explorer.kind === 'generic' && (nk === 'stop' || nk === 'response') && typeof root.text === 'string') {
        const text = root.text;
        return {
            expandNoRowsDetail: { payload: text, title, subtitle: 'string' },
            headerClipboardText: formatValueForPrimitiveClipboard(text, 'string'),
            headerClipboardAriaLabel: HEADER_COPY_ARIA,
        };
    }

    /** Document, structure, conditional, stop/response without string text, etc.: full serialized output for header modal. */
    if (explorer.kind === 'generic') {
        return {
            expandNoRowsDetail: { payload: nodeOutput, title, subtitle: FULL_OUTPUT_SUBTITLE },
        };
    }

    return {};
}
