import { describe, expect, it } from 'vitest';
import {
    interpretParsedPath,
    isWorkflowIdSegment,
    parseAppPathname,
    pathForTopLevelView,
    pathForWorkflowEditor,
} from './appUrlState';

const SAMPLE_ID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';

describe('isWorkflowIdSegment', () => {
    it('accepts lowercase UUID v4-shaped strings', () => {
        expect(isWorkflowIdSegment(SAMPLE_ID)).toBe(true);
    });
    it('rejects non-UUID text', () => {
        expect(isWorkflowIdSegment('not-a-uuid')).toBe(false);
        expect(isWorkflowIdSegment('')).toBe(false);
    });
});

describe('parseAppPathname', () => {
    it('parses root variants', () => {
        expect(parseAppPathname('/')).toEqual({ kind: 'root' });
        expect(parseAppPathname('')).toEqual({ kind: 'root' });
        expect(parseAppPathname('///')).toEqual({ kind: 'root' });
    });
    it('parses workspace and sandbox', () => {
        expect(parseAppPathname('/workspace')).toEqual({ kind: 'workspace' });
        expect(parseAppPathname('/sandbox')).toEqual({ kind: 'sandbox' });
    });
    it('parses workflows list and detail', () => {
        expect(parseAppPathname('/workflows')).toEqual({ kind: 'workflows', workflowId: null });
        expect(parseAppPathname('/workflows/')).toEqual({ kind: 'workflows', workflowId: null });
        expect(parseAppPathname(`/workflows/${SAMPLE_ID}`)).toEqual({
            kind: 'workflows',
            workflowId: SAMPLE_ID,
        });
    });
    it('treats invalid workflow id segment as workflowsBadId', () => {
        expect(parseAppPathname('/workflows/nope')).toEqual({ kind: 'workflowsBadId' });
    });
    it('treats nested paths under workflows as unknown', () => {
        expect(parseAppPathname(`/workflows/${SAMPLE_ID}/edit`)).toEqual({ kind: 'unknown' });
    });
    it('treats arbitrary paths as unknown', () => {
        expect(parseAppPathname('/nope')).toEqual({ kind: 'unknown' });
    });
});

describe('interpretParsedPath', () => {
    it('maps root to workspace when enabled else home', () => {
        expect(interpretParsedPath({ kind: 'root' }, { workspaceEnabled: true, sandboxEnabled: true })).toEqual({
            activeView: 'workspace',
            urlWorkflowId: null,
            normalizePath: null,
        });
        expect(interpretParsedPath({ kind: 'root' }, { workspaceEnabled: false, sandboxEnabled: true })).toEqual({
            activeView: 'home',
            urlWorkflowId: null,
            normalizePath: null,
        });
    });
    it('normalizes workspace path when workspace disabled', () => {
        expect(interpretParsedPath({ kind: 'workspace' }, { workspaceEnabled: false, sandboxEnabled: true })).toEqual({
            activeView: 'home',
            urlWorkflowId: null,
            normalizePath: '/',
        });
    });
    it('normalizes sandbox when disabled', () => {
        expect(
            interpretParsedPath({ kind: 'sandbox' }, { workspaceEnabled: true, sandboxEnabled: false }),
        ).toEqual({
            activeView: 'workspace',
            urlWorkflowId: null,
            normalizePath: '/workspace',
        });
        expect(
            interpretParsedPath({ kind: 'sandbox' }, { workspaceEnabled: false, sandboxEnabled: false }),
        ).toEqual({
            activeView: 'home',
            urlWorkflowId: null,
            normalizePath: '/',
        });
    });
    it('keeps workflows detail id', () => {
        expect(
            interpretParsedPath(
                { kind: 'workflows', workflowId: SAMPLE_ID },
                { workspaceEnabled: true, sandboxEnabled: true },
            ),
        ).toEqual({
            activeView: 'workflows',
            urlWorkflowId: SAMPLE_ID,
            normalizePath: null,
        });
    });
    it('normalizes bad workflow id to /workflows', () => {
        expect(
            interpretParsedPath({ kind: 'workflowsBadId' }, { workspaceEnabled: true, sandboxEnabled: true }),
        ).toEqual({
            activeView: 'workflows',
            urlWorkflowId: null,
            normalizePath: '/workflows',
        });
    });
});

describe('path helpers', () => {
    it('pathForTopLevelView respects workspace flag for workspace view', () => {
        expect(pathForTopLevelView('workspace', { workspaceEnabled: true })).toBe('/workspace');
        expect(pathForTopLevelView('workspace', { workspaceEnabled: false })).toBe('/');
    });
    it('pathForWorkflowEditor', () => {
        expect(pathForWorkflowEditor(null)).toBe('/workflows');
        expect(pathForWorkflowEditor(SAMPLE_ID)).toBe(`/workflows/${SAMPLE_ID}`);
    });
});
