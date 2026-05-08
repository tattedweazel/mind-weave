import { describe, it, expect } from 'vitest';
import type { OutputExplorerV1 } from '../api/types';
import { outputExplorerRunRowExtras } from './outputExplorerRunRowExtras';

describe('outputExplorerRunRowExtras', () => {
    it('returns expandNoRowsDetail and header copy for stop generic output', () => {
        const long = `${'x'.repeat(200)}END`;
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'generic',
            summary: { line: 'stop output', detail_lines: ['truncated…'] },
            items: [],
        };
        const nodeOutput = { kind: 'stop', node_id: 'n1', text: long };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail).toEqual({
            payload: long,
            title: 'stop output',
            subtitle: 'string',
        });
        expect(x.headerClipboardText).toBe(long);
        expect(x.headerClipboardAriaLabel).toBe('Copy output value');
    });

    it('returns extras for response generic output', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'generic',
            summary: { line: 'response output', detail_lines: ['hi'] },
            items: [],
        };
        const nodeOutput = { kind: 'response', text: 'hello' };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail?.payload).toBe('hello');
        expect(x.expandNoRowsDetail?.title).toBe('response output');
    });

    it('returns extras for string_primitive explorer', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'string_primitive',
            summary: { line: 'String value', detail_lines: ['ab…'] },
            items: [],
        };
        const nodeOutput = { kind: 'string', node_id: '', text: 'full text here' };
        expect(outputExplorerRunRowExtras(explorer, nodeOutput).expandNoRowsDetail?.payload).toBe('full text here');
    });

    it('returns extras for int_primitive', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'int_primitive',
            summary: { line: 'Integer value', detail_lines: ['42'] },
            items: [],
        };
        const nodeOutput = { kind: 'int', node_id: '', value: 42 };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail).toEqual({ payload: 42, title: 'Integer value', subtitle: 'int' });
        expect(x.headerClipboardText).toBe('42');
    });

    it('returns extras for boolean_primitive', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'boolean_primitive',
            summary: { line: 'Boolean value', detail_lines: ['true'] },
            items: [],
        };
        const nodeOutput = { kind: 'boolean', node_id: '', value: true };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail?.payload).toBe(true);
        expect(x.expandNoRowsDetail?.subtitle).toBe('boolean');
    });

    it('returns expandNoRowsDetail with full nodeOutput when explorer has rows', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'list_primitive',
            summary: { line: 'L', detail_lines: ['1 item(s)'] },
            items: [
                {
                    index: 0,
                    row_state: 'ok',
                    primary_line: '[0]',
                    secondary_line: 'string',
                    teaser: '"a"',
                    badges: [],
                    inferred_primitive: 'string',
                },
            ],
        };
        const nodeOutput = { kind: 'list', node_id: '', data: ['a'] };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail).toEqual({
            payload: nodeOutput,
            title: 'L',
            subtitle: 'Full output',
        });
        expect(x.headerClipboardText).toBeUndefined();
    });

    it('returns full nodeOutput for generic stop when text is not a string', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'generic',
            summary: { line: 'stop output', detail_lines: ['(empty)'] },
            items: [],
        };
        const nodeOutput = { kind: 'stop', text: null };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail).toEqual({
            payload: nodeOutput,
            title: 'stop output',
            subtitle: 'Full output',
        });
    });

    it('returns full nodeOutput for generic document output (Last Run header parity)', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'generic',
            summary: {
                line: 'document output',
                detail_lines: ['Document: My doc', 'Some teaser…'],
            },
            items: [],
        };
        const nodeOutput = {
            kind: 'document',
            node_id: 'n1',
            name: 'My doc',
            markdown: '# Hello',
        };
        const x = outputExplorerRunRowExtras(explorer, nodeOutput);
        expect(x.expandNoRowsDetail?.payload).toBe(nodeOutput);
        expect(x.expandNoRowsDetail?.title).toBe('document output');
        expect(x.expandNoRowsDetail?.subtitle).toBe('Full output');
    });

    it('uses title fallback when summary line is whitespace', () => {
        const explorer: OutputExplorerV1 = {
            version: 1,
            kind: 'generic',
            summary: { line: '   ', detail_lines: ['x'] },
            items: [],
        };
        const nodeOutput = { kind: 'stop', text: 't' };
        expect(outputExplorerRunRowExtras(explorer, nodeOutput).expandNoRowsDetail?.title).toBe('Output');
    });
});
