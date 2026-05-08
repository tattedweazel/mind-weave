/**
 * Client-built `output_explorer` + synthetic `nodeOutput` for each Last Run / Run logs **Inputs** field.
 * Shapes mirror `output_explorer.py` list/dict/primitive builders (see repo `backend/app/domain/workflow_executor/output_explorer.py`).
 */

import type { OutputExplorerItem, OutputExplorerV1 } from '../api/types';
import { formatValueForPrimitiveClipboard } from './formatValueForPrimitiveClipboard';

/** Must match `OUTPUT_EXPLORER_MAX_ITEMS` in backend `output_explorer.py`. */
export const CLIENT_OUTPUT_EXPLORER_MAX_ITEMS = 50;

const TEASER_MAX = 180;

function truncateTeaser(s: string, maxLen: number = TEASER_MAX): string {
    const t = s.trim();
    if (t.length <= maxLen) return t;
    return `${t.slice(0, maxLen - 1)}…`;
}

function jsonPreview(val: unknown, maxLen: number = TEASER_MAX): string {
    try {
        return truncateTeaser(JSON.stringify(val), maxLen);
    } catch {
        return truncateTeaser(String(val), maxLen);
    }
}

export function inferPrimitiveKindForExplorer(v: unknown): string {
    if (v === null) return 'null';
    if (v === undefined) return 'undefined';
    if (typeof v === 'boolean') return 'boolean';
    if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'number';
    if (typeof v === 'string') return 'string';
    if (Array.isArray(v)) return 'list';
    if (typeof v === 'object') return 'dictionary';
    return 'mixed';
}

/** When `explorer.items` is empty, pass as `expandNoRowsDetail` on `OutputExplorer` so the header opens the detail modal. */
export type OutputExplorerExpandNoRowsDetail = {
    payload: unknown;
    title: string;
    subtitle: string;
};

export type ClientInputFieldExplorerBundle = {
    explorer: OutputExplorerV1;
    nodeOutput: unknown;
    headerClipboardText?: string;
    headerClipboardAriaLabel?: string;
    expandNoRowsDetail?: OutputExplorerExpandNoRowsDetail;
};

const SYNTHETIC_NODE_ID = '';

function buildExpandNoRowsDetail(fieldKey: string, value: unknown): OutputExplorerExpandNoRowsDetail {
    return {
        payload: value,
        title: fieldKey,
        subtitle: inferPrimitiveKindForExplorer(value),
    };
}

export function buildClientExplorerForInputField(
    fieldKey: string,
    value: unknown,
): ClientInputFieldExplorerBundle {
    if (value === undefined) {
        return {
            explorer: {
                version: 1,
                kind: 'generic',
                summary: { line: fieldKey, detail_lines: ['undefined'] },
                items: [],
            },
            nodeOutput: { kind: 'string', node_id: SYNTHETIC_NODE_ID, text: '' },
            headerClipboardText: '',
            headerClipboardAriaLabel: 'Copy input value',
            expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
        };
    }

    if (value === null) {
        return {
            explorer: {
                version: 1,
                kind: 'generic',
                summary: { line: fieldKey, detail_lines: ['null'] },
                items: [],
            },
            nodeOutput: { kind: 'string', node_id: SYNTHETIC_NODE_ID, text: 'null' },
            headerClipboardText: 'null',
            headerClipboardAriaLabel: 'Copy input value',
            expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
        };
    }

    if (typeof value === 'string') {
        const s = value;
        return {
            explorer: {
                version: 1,
                kind: 'string_primitive',
                summary: {
                    line: fieldKey,
                    detail_lines: [s ? truncateTeaser(s, 500) : '(empty)'],
                },
                items: [],
            },
            nodeOutput: { kind: 'string', node_id: SYNTHETIC_NODE_ID, text: s },
            headerClipboardText: formatValueForPrimitiveClipboard(s, 'string'),
            headerClipboardAriaLabel: 'Copy input value',
            expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
        };
    }

    if (typeof value === 'boolean') {
        return {
            explorer: {
                version: 1,
                kind: 'boolean_primitive',
                summary: {
                    line: fieldKey,
                    detail_lines: [value ? 'true' : 'false'],
                },
                items: [],
            },
            nodeOutput: { kind: 'boolean', node_id: SYNTHETIC_NODE_ID, value },
            headerClipboardText: formatValueForPrimitiveClipboard(value, 'boolean'),
            headerClipboardAriaLabel: 'Copy input value',
            expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
        };
    }

    if (typeof value === 'number' && Number.isFinite(value)) {
        const asInt = Number.isInteger(value);
        const n = asInt ? Math.trunc(value) : value;
        return {
            explorer: {
                version: 1,
                kind: 'int_primitive',
                summary: {
                    line: fieldKey,
                    detail_lines: [String(n)],
                },
                items: [],
            },
            nodeOutput: { kind: 'int', node_id: SYNTHETIC_NODE_ID, value: n },
            headerClipboardText: formatValueForPrimitiveClipboard(n, asInt ? 'int' : 'number'),
            headerClipboardAriaLabel: 'Copy input value',
            expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
        };
    }

    if (Array.isArray(value)) {
        return buildListFieldExplorer(fieldKey, value);
    }

    if (typeof value === 'object') {
        return buildDictionaryFieldExplorer(fieldKey, value as Record<string, unknown>);
    }

    return {
        explorer: {
            version: 1,
            kind: 'generic',
            summary: { line: fieldKey, detail_lines: [String(value)] },
            items: [],
        },
        nodeOutput: { kind: 'string', node_id: SYNTHETIC_NODE_ID, text: String(value) },
        headerClipboardText: formatValueForPrimitiveClipboard(value, 'mixed'),
        headerClipboardAriaLabel: 'Copy input value',
        expandNoRowsDetail: buildExpandNoRowsDetail(fieldKey, value),
    };
}

function buildListFieldExplorer(fieldKey: string, arr: unknown[]): ClientInputFieldExplorerBundle {
    const n = arr.length;
    const kinds = arr.map(x => inferPrimitiveKindForExplorer(x));
    const distinct = new Set(kinds);
    const detailLines: string[] = [];
    if (distinct.size > 1) {
        detailLines.push('Heterogeneous list');
    }

    const overflow = Math.max(0, n - CLIENT_OUTPUT_EXPLORER_MAX_ITEMS);
    const items: OutputExplorerItem[] = [];
    for (let idx = 0; idx < Math.min(n, CLIENT_OUTPUT_EXPLORER_MAX_ITEMS); idx++) {
        const val = arr[idx];
        const inf = kinds[idx];
        const inferredRow = distinct.size > 1 ? 'mixed' : inf;
        items.push({
            index: idx,
            row_state: 'ok',
            primary_line: `[${idx}]`,
            secondary_line: inf,
            teaser: jsonPreview(val),
            badges: [],
            inferred_primitive: inferredRow,
        });
    }

    const explorer: OutputExplorerV1 = {
        version: 1,
        kind: 'list_primitive',
        summary: {
            line: fieldKey,
            detail_lines: [`${n} item(s)`, ...detailLines],
        },
        items,
    };
    if (overflow > 0) {
        explorer.overflow_count = overflow;
    }

    return {
        explorer,
        nodeOutput: { kind: 'list', node_id: SYNTHETIC_NODE_ID, data: arr },
    };
}

function buildDictionaryFieldExplorer(
    fieldKey: string,
    data: Record<string, unknown>,
): ClientInputFieldExplorerBundle {
    /** Preserve insertion order (matches typical `resolved_inputs` maps). */
    const keys = Object.keys(data);
    const n = keys.length;
    const overflow = Math.max(0, n - CLIENT_OUTPUT_EXPLORER_MAX_ITEMS);
    const items: OutputExplorerItem[] = [];
    for (let idx = 0; idx < Math.min(n, CLIENT_OUTPUT_EXPLORER_MAX_ITEMS); idx++) {
        const k = keys[idx];
        const val = data[k];
        const inf = inferPrimitiveKindForExplorer(val);
        items.push({
            index: idx,
            row_state: 'ok',
            primary_line: k,
            secondary_line: inf,
            teaser: jsonPreview(val),
            badges: [],
            inferred_primitive: inf,
        });
    }

    const kinds = new Set(keys.map(k => inferPrimitiveKindForExplorer(data[k])));
    const detailLines: string[] = [];
    if (kinds.size > 1) {
        detailLines.push('Multiple value types');
    }

    const explorer: OutputExplorerV1 = {
        version: 1,
        kind: 'dictionary_primitive',
        summary: {
            line: fieldKey,
            detail_lines: [`${n} key(s)`, ...detailLines],
        },
        items,
    };
    if (overflow > 0) {
        explorer.overflow_count = overflow;
    }

    return {
        explorer,
        nodeOutput: { kind: 'dictionary', node_id: SYNTHETIC_NODE_ID, data },
    };
}
