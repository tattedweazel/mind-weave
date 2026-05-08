/**
 * Collapsible JSON/object tree for workflow run output and skill diagnostics.
 */

import { useCallback, useEffect, useState } from 'react';
import { ChevronsDown, ChevronsUp } from 'lucide-react';

const pathKey = (segments: Array<string | number>) => JSON.stringify(segments);

function formatPrimitive(val: unknown): string {
    if (val === null) return 'null';
    if (typeof val === 'string') return JSON.stringify(val);
    if (typeof val === 'number' || typeof val === 'boolean') return String(val);
    if (val === undefined) return 'undefined';
    return JSON.stringify(val);
}

type Counter = { n: number };

export type JsonTreeViewProps = {
    data: unknown;
    defaultExpandedDepth?: number;
    maxDepth?: number;
    maxNodes?: number;
    className?: string;
};

const DEFAULT_MAX_DEPTH = 32;
const DEFAULT_MAX_NODES = 2500;

export function JsonTreeView({
    data,
    defaultExpandedDepth = 3,
    maxDepth = DEFAULT_MAX_DEPTH,
    maxNodes = DEFAULT_MAX_NODES,
    className = '',
}: JsonTreeViewProps) {
    const [depthLimit, setDepthLimit] = useState(defaultExpandedDepth);
    const [manual, setManual] = useState<Record<string, boolean>>({});

    useEffect(() => {
        setDepthLimit(defaultExpandedDepth);
        setManual({});
    }, [data, defaultExpandedDepth]);

    const isOpen = useCallback(
        (segments: Array<string | number>, depth: number) => {
            const k = pathKey(segments);
            if (Object.prototype.hasOwnProperty.call(manual, k)) {
                return manual[k];
            }
            return depth < depthLimit;
        },
        [depthLimit, manual],
    );

    const toggle = useCallback(
        (segments: Array<string | number>, depth: number) => {
            const k = pathKey(segments);
            setManual((prev) => {
                const cur =
                    Object.prototype.hasOwnProperty.call(prev, k) ?
                        prev[k]
                    :   depth < depthLimit;
                return { ...prev, [k]: !cur };
            });
        },
        [depthLimit],
    );

    const collapseAll = useCallback(() => {
        setDepthLimit(0);
        setManual({});
    }, []);

    const expandAll = useCallback(() => {
        setDepthLimit(maxDepth);
        setManual({});
    }, [maxDepth]);

    const hasManualOverrides = Object.keys(manual).length > 0;
    const isFullyExpanded = depthLimit >= maxDepth && !hasManualOverrides;

    const counter: Counter = { n: 0 };

    return (
        <div className={`rounded-lg border border-mw-border bg-mw-card-alt ${className}`}>
            <div className="flex items-center justify-end px-2 py-1 border-b border-mw-border bg-mw-card/80">
                <button
                    type="button"
                    onClick={isFullyExpanded ? collapseAll : expandAll}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-mw-text-secondary hover:text-mw-text-primary rounded transition-colors"
                    title={
                        isFullyExpanded ?
                            'Collapse tree'
                        :   `Expand up to ${maxDepth} levels`
                    }
                >
                    {isFullyExpanded ?
                        <>
                            <ChevronsUp size={12} /> Collapse
                        </>
                    :   <>
                            <ChevronsDown size={12} /> Expand
                        </>
                    }
                </button>
            </div>
            <div className="max-h-96 overflow-y-auto overflow-x-auto p-2 font-mono text-[11px] leading-snug text-mw-text-primary">
                <TreeNode
                    name={null}
                    value={data}
                    path={[]}
                    depth={0}
                    isOpen={isOpen}
                    onToggle={toggle}
                    maxDepth={maxDepth}
                    maxNodes={maxNodes}
                    counter={counter}
                />
                {counter.n >= maxNodes && (
                    <div className="mt-2 text-amber-700 dark:text-amber-300/90 text-[10px]">
                        Tree truncated ({maxNodes} nodes max). Collapse the tree or use a smaller payload to see more.
                    </div>
                )}
            </div>
        </div>
    );
}

type TreeNodeProps = {
    name: string | number | null;
    value: unknown;
    path: Array<string | number>;
    depth: number;
    isOpen: (path: Array<string | number>, depth: number) => boolean;
    onToggle: (path: Array<string | number>, depth: number) => void;
    maxDepth: number;
    maxNodes: number;
    counter: Counter;
};

function TreeNode({
    name,
    value,
    path,
    depth,
    isOpen,
    onToggle,
    maxDepth,
    maxNodes,
    counter,
}: TreeNodeProps) {
    if (counter.n >= maxNodes) {
        return null;
    }

    if (value === null || typeof value !== 'object') {
        counter.n += 1;
        return (
            <div className="flex flex-wrap gap-x-1 break-all items-baseline">
                {name !== null && (
                    <>
                        <span className="text-violet-600 dark:text-violet-400 shrink-0">
                            {typeof name === 'number' ? `[${name}]` : name}
                        </span>
                        <span className="text-mw-text-secondary">:</span>
                    </>
                )}
                <span className="text-mw-text-primary">{formatPrimitive(value)}</span>
            </div>
        );
    }

    if (depth >= maxDepth) {
        counter.n += 1;
        return (
            <div className="text-amber-600 dark:text-amber-400/90 italic break-all">
                {name !== null && (
                    <span className="text-violet-600 dark:text-violet-400 not-italic mr-1">
                        {typeof name === 'number' ? `[${name}]` : `${name}:`}
                    </span>
                )}
                [Max depth]
            </div>
        );
    }

    const isArray = Array.isArray(value);
    const entries: [string | number, unknown][] = isArray ?
            value.map((v, i) => [i, v])
        :   Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, v]);

    if (entries.length === 0) {
        counter.n += 1;
        return (
            <div className="flex flex-wrap gap-x-1 items-baseline">
                {name !== null && (
                    <>
                        <span className="text-violet-600 dark:text-violet-400">
                            {typeof name === 'number' ? `[${name}]` : name}
                        </span>
                        <span className="text-mw-text-secondary">:</span>
                    </>
                )}
                <span className="text-mw-text-secondary">{isArray ? '[]' : '{}'}</span>
            </div>
        );
    }

    const open = path.length === 0 || isOpen(path, depth);
    const summary = isArray ? `[${entries.length}]` : `{${entries.length}}`;

    if (path.length === 0) {
        counter.n += 1;
        return (
            <ul className="space-y-1 list-none m-0 p-0">
                {entries.map(([key, child]) => (
                    <li key={pathKey([key])} className="m-0 p-0">
                        <TreeNode
                            name={key}
                            value={child}
                            path={[key]}
                            depth={0}
                            isOpen={isOpen}
                            onToggle={onToggle}
                            maxDepth={maxDepth}
                            maxNodes={maxNodes}
                            counter={counter}
                        />
                    </li>
                ))}
            </ul>
        );
    }

    counter.n += 1;
    return (
        <div>
            <div className="flex items-start gap-0.5">
                <button
                    type="button"
                    aria-expanded={open}
                    onClick={() => onToggle(path, depth)}
                    className="shrink-0 mt-0.5 p-0 w-4 h-4 flex items-center justify-center text-mw-text-secondary hover:text-mw-text-primary rounded"
                >
                    <span className="text-[10px] font-bold leading-none">{open ? '−' : '+'}</span>
                </button>
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-1 break-all">
                        <span className="text-violet-600 dark:text-violet-400">
                            {typeof name === 'number' ? `[${name}]` : name}
                        </span>
                        <span className="text-mw-text-secondary">:</span>
                        <span className="text-mw-text-secondary">{summary}</span>
                    </div>
                    {open && (
                        <ul className="mt-0.5 ml-2 border-l border-mw-border/70 pl-2 space-y-1 list-none m-0">
                            {entries.map(([key, child]) => (
                                <li key={pathKey([...path, key])} className="m-0 p-0">
                                    <TreeNode
                                        name={key}
                                        value={child}
                                        path={[...path, key]}
                                        depth={depth + 1}
                                        isOpen={isOpen}
                                        onToggle={onToggle}
                                        maxDepth={maxDepth}
                                        maxNodes={maxNodes}
                                        counter={counter}
                                    />
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </div>
        </div>
    );
}
