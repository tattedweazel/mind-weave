import React from 'react';
import type { DocumentMetadata } from '../api/types';

interface Props {
    metadata: DocumentMetadata;
}

function formatTimestamp(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
}

const integerFormatter = new Intl.NumberFormat();

const ROW_LABELS: ReadonlyArray<{ label: string; valueWidth: string; withHint?: boolean }> = [
    { label: 'Token count', valueWidth: 'w-20', withHint: true },
    { label: 'Characters', valueWidth: 'w-16' },
    { label: 'Words', valueWidth: 'w-12' },
    { label: 'Lines', valueWidth: 'w-10' },
    { label: 'Document ID', valueWidth: 'w-64' },
    { label: 'Created', valueWidth: 'w-44' },
    { label: 'Updated', valueWidth: 'w-44' },
];

/**
 * Definition list of derived size statistics + identity fields for a focused
 * Document, rendered inside the Manage Documents → Metadata tab. Token counts
 * are estimated (see ``tokenizer`` field) and the panel says so honestly.
 */
export const DocumentMetadataPanel: React.FC<Props> = ({ metadata }) => {
    const rows: Array<{ label: string; value: React.ReactNode; hint?: string }> = [
        {
            label: 'Token count',
            value: integerFormatter.format(metadata.token_count),
            hint: `Estimated with ${metadata.tokenizer} (GPT-4o family)`,
        },
        { label: 'Characters', value: integerFormatter.format(metadata.character_count) },
        { label: 'Words', value: integerFormatter.format(metadata.word_count) },
        { label: 'Lines', value: integerFormatter.format(metadata.line_count) },
        {
            label: 'Document ID',
            value: <span className="font-mono text-xs break-all">{metadata.id}</span>,
        },
        { label: 'Created', value: formatTimestamp(metadata.created_at) },
        { label: 'Updated', value: formatTimestamp(metadata.updated_at) },
    ];

    return (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm" data-testid="document-metadata-panel">
            {rows.map(row => (
                <React.Fragment key={row.label}>
                    <dt className="text-mw-text-secondary">{row.label}</dt>
                    <dd className="text-mw-text-primary">
                        {row.value}
                        {row.hint && (
                            <div className="text-xs text-mw-text-secondary mt-0.5">{row.hint}</div>
                        )}
                    </dd>
                </React.Fragment>
            ))}
        </dl>
    );
};

/**
 * Pulsing skeleton mirror of {@link DocumentMetadataPanel} for the in-flight
 * metadata fetch. Mirrors the same dl grid layout so the eventual swap to real
 * data does not jump the surrounding container around.
 */
export const DocumentMetadataPanelSkeleton: React.FC = () => (
    <dl
        className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm animate-pulse"
        data-testid="document-metadata-panel-skeleton"
        aria-busy="true"
        aria-live="polite"
    >
        <span className="sr-only">Loading metadata…</span>
        {ROW_LABELS.map(row => (
            <React.Fragment key={row.label}>
                <dt className="text-mw-text-secondary">{row.label}</dt>
                <dd>
                    <div
                        className={`h-4 rounded bg-mw-text-secondary/20 ${row.valueWidth} max-w-full`}
                        aria-hidden="true"
                    />
                    {row.withHint && (
                        <div
                            className="mt-1 h-3 w-56 max-w-full rounded bg-mw-text-secondary/15"
                            aria-hidden="true"
                        />
                    )}
                </dd>
            </React.Fragment>
        ))}
    </dl>
);
