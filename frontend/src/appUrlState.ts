/**
 * Path-based shell routing for the SPA (no react-router).
 * Synced with the browser URL so refresh restores the Workflow Editor and optional workflow id.
 */

const WORKFLOW_ID_SEGMENT_RE =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isWorkflowIdSegment(segment: string): boolean {
    return WORKFLOW_ID_SEGMENT_RE.test(segment);
}

export type ParsedAppPath =
    | { kind: 'root' }
    | { kind: 'workspace' }
    | { kind: 'workflows'; workflowId: string | null }
    | { kind: 'workflowsBadId' }
    | { kind: 'sandbox' }
    | { kind: 'unknown' };

/** Normalize trailing slashes; leading slash optional in input. */
export function parseAppPathname(pathname: string): ParsedAppPath {
    const raw = pathname.trim();
    const noTrail = raw.replace(/\/+$/, '') || '/';
    const p = noTrail.startsWith('/') ? noTrail : `/${noTrail}`;

    if (p === '/') return { kind: 'root' };
    if (p === '/workspace') return { kind: 'workspace' };
    if (p === '/workflows') return { kind: 'workflows', workflowId: null };

    if (p.startsWith('/workflows/')) {
        const rest = p.slice('/workflows/'.length);
        if (rest === '') return { kind: 'workflows', workflowId: null };
        if (rest.includes('/')) return { kind: 'unknown' };
        if (isWorkflowIdSegment(rest)) return { kind: 'workflows', workflowId: rest };
        return { kind: 'workflowsBadId' };
    }

    if (p === '/sandbox') return { kind: 'sandbox' };
    return { kind: 'unknown' };
}

export type ActiveShellView = 'home' | 'workflows' | 'sandbox' | 'workspace';

export type InterpretedAppPath = {
    activeView: ActiveShellView;
    urlWorkflowId: string | null;
    /** When set, replace the URL once (invalid path or disabled feature). */
    normalizePath: string | null;
};

export function interpretParsedPath(
    parsed: ParsedAppPath,
    opts: { workspaceEnabled: boolean; sandboxEnabled: boolean },
): InterpretedAppPath {
    const homeFallback: InterpretedAppPath = {
        activeView: 'home',
        urlWorkflowId: null,
        normalizePath: null,
    };
    const workspaceFallback: InterpretedAppPath = {
        activeView: 'workspace',
        urlWorkflowId: null,
        normalizePath: null,
    };
    const defaultLanding = opts.workspaceEnabled ? workspaceFallback : homeFallback;

    switch (parsed.kind) {
        case 'root':
            return defaultLanding;
        case 'workspace':
            if (!opts.workspaceEnabled) {
                return { activeView: 'home', urlWorkflowId: null, normalizePath: '/' };
            }
            return workspaceFallback;
        case 'workflows':
            return {
                activeView: 'workflows',
                urlWorkflowId: parsed.workflowId,
                normalizePath: null,
            };
        case 'workflowsBadId':
            return {
                activeView: 'workflows',
                urlWorkflowId: null,
                normalizePath: '/workflows',
            };
        case 'sandbox':
            if (!opts.sandboxEnabled) {
                return {
                    ...defaultLanding,
                    normalizePath: opts.workspaceEnabled ? '/workspace' : '/',
                };
            }
            return { activeView: 'sandbox', urlWorkflowId: null, normalizePath: null };
        case 'unknown':
            return {
                ...defaultLanding,
                normalizePath: opts.workspaceEnabled ? '/workspace' : '/',
            };
    }
}

export function pathForTopLevelView(
    view: ActiveShellView,
    opts: { workspaceEnabled: boolean },
): string {
    switch (view) {
        case 'home':
            return '/';
        case 'workspace':
            return opts.workspaceEnabled ? '/workspace' : '/';
        case 'workflows':
            return '/workflows';
        case 'sandbox':
            return '/sandbox';
        default:
            return '/';
    }
}

export function pathForWorkflowEditor(workflowId: string | null): string {
    return workflowId ? `/workflows/${workflowId}` : '/workflows';
}
