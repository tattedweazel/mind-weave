/**
 * Shared “what to show for a node’s output” for Run logs, Last Run inspector, and Explore replay.
 * Audio outputs must check `kind === 'audio'` before generic `output_explorer` so inline playback works.
 * capture_url_snapshot success stores `data.image.artifact_id` — show preview + download before explorer-only.
 */
import React from 'react';

import { parseEffectiveOutputExplorer } from '../../api/types';
import { outputExplorerRunRowExtras } from '../../domain/outputExplorerRunRowExtras';
import { MarkdownRawPreview } from '../MarkdownRawPreview';
import { JsonTreeView } from './JsonTreeView';
import { OutputExplorer } from './OutputExplorer';
import { calendarDisplayTimeZoneForExplorer } from './outputExplorerCalendarTz';
import { TtsRunLogAudioPlayer } from './TtsRunLogAudioPlayer';
import { UrlSnapshotArtifactPreview } from './UrlSnapshotArtifactPreview';

export type WorkflowNodeRunOutputBodyProps = {
    nodeId: string;
    output: unknown;
    details: Record<string, unknown> | undefined;
    userSettings?: Record<string, unknown>;
    /** Height of Markdown preview for string outputs (Run logs default 10; inspector often 12). */
    markdownRows?: number;
};

export function WorkflowNodeRunOutputBody({
    nodeId,
    output,
    details,
    userSettings,
    markdownRows = 10,
}: WorkflowNodeRunOutputBodyProps): React.ReactNode {
    if (!output || typeof output !== 'object') {
        return null;
    }
    const out = output as Record<string, unknown> & {
        kind?: string;
        audio_base64?: unknown;
        mime_type?: unknown;
        text?: unknown;
        data?: unknown;
        value?: unknown;
        branch?: unknown;
    };
    const outputEx = parseEffectiveOutputExplorer(details);

    if (out.kind === 'dictionary' && out.data != null && typeof out.data === 'object') {
        const dataObj = out.data as Record<string, unknown>;
        if (dataObj.error == null) {
            const img = dataObj.image;
            if (img && typeof img === 'object' && img != null) {
                const rec = img as Record<string, unknown>;
                const aid = rec.artifact_id;
                if (typeof aid === 'string' && aid.length > 0) {
                    let explorerBelow: React.ReactNode = null;
                    if (outputEx) {
                        const calExTz = calendarDisplayTimeZoneForExplorer(outputEx, userSettings);
                        const runRowExtras = outputExplorerRunRowExtras(outputEx, out);
                        explorerBelow = (
                            <OutputExplorer
                                explorer={outputEx}
                                nodeOutput={out}
                                calendarDisplayTimeZone={calExTz}
                                {...runRowExtras}
                            />
                        );
                    }
                    return (
                        <>
                            <UrlSnapshotArtifactPreview artifactId={aid} nodeId={nodeId} />
                            {explorerBelow ?
                                <div className="mt-3 pt-3 border-t border-mw-border/80">{explorerBelow}</div>
                            : null}
                        </>
                    );
                }
            }
        }
    }

    if (out.kind === 'audio') {
        const b64 = out.audio_base64;
        const usable = typeof b64 === 'string' && b64.length > 0 && b64 !== '[redacted]';
        const mime = typeof out.mime_type === 'string' && out.mime_type ? out.mime_type : 'audio/wav';
        let explorerBelow: React.ReactNode = null;
        if (outputEx) {
            const calExTz = calendarDisplayTimeZoneForExplorer(outputEx, userSettings);
            const runRowExtras = outputExplorerRunRowExtras(outputEx, out);
            explorerBelow = (
                <OutputExplorer
                    explorer={outputEx}
                    nodeOutput={out}
                    calendarDisplayTimeZone={calExTz}
                    {...runRowExtras}
                />
            );
        }
        if (usable) {
            return (
                <>
                    <TtsRunLogAudioPlayer base64={b64} mimeType={mime} nodeId={nodeId} />
                    {explorerBelow ?
                        <div className="mt-3 pt-3 border-t border-mw-border/80">{explorerBelow}</div>
                    : null}
                </>
            );
        }
        return (
            <>
                <p className="text-xs text-mw-text-secondary mb-2">
                    Audio is only available during the live run; run history does not store audio bytes. Re-run the workflow
                    to hear this output.
                </p>
                {explorerBelow}
            </>
        );
    }

    if (outputEx) {
        const calExTz = calendarDisplayTimeZoneForExplorer(outputEx, userSettings);
        const runRowExtras = outputExplorerRunRowExtras(outputEx, out);
        return (
            <OutputExplorer
                explorer={outputEx}
                nodeOutput={out}
                calendarDisplayTimeZone={calExTz}
                {...runRowExtras}
            />
        );
    }

    if (out.text != null) {
        return <MarkdownRawPreview value={String(out.text)} editable={false} rows={markdownRows} />;
    }

    if (out.data != null && typeof out.data === 'object') {
        const dataObj = out.data as Record<string, unknown>;
        return <JsonTreeView data={dataObj} defaultExpandedDepth={3} />;
    }

    if (out.data != null) {
        return (
            <div className="bg-mw-card-alt text-mw-text-primary rounded p-2 whitespace-pre-wrap break-all max-h-96 overflow-y-auto text-[11px] font-mono">
                {String(out.data)}
            </div>
        );
    }

    if (out.value !== undefined && out.value !== null) {
        return (
            <div className="bg-mw-card-alt text-mw-text-primary rounded p-2 whitespace-pre-wrap break-all text-[11px] font-mono">
                {String(out.value)}
            </div>
        );
    }

    if (out.branch != null) {
        return (
            <div className="bg-mw-card-alt text-mw-text-primary rounded p-2 text-[11px] font-mono">
                Branch: {String(out.branch)}
            </div>
        );
    }

    return null;
}
