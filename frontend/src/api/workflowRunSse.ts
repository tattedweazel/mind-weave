/**
 * Converts workflow run SSE payloads (POST …/runs + GET …/workflow-runs/{id}/events)
 * into the legacy NDJSON-shaped events the Workflow Editor already handles.
 */

export type LegacyNdjsonWorkflowEvent = Record<string, unknown> & { event: string };

export function ssePayloadToLegacyWorkflowEvent(
    sseEventName: string,
    payload: Record<string, unknown>,
): LegacyNdjsonWorkflowEvent | null {
    const seq = typeof payload.seq === 'number' ? payload.seq : undefined;
    const withSeq =
        seq !== undefined ? ({ ...payload, seq } as Record<string, unknown>) : ({ ...payload } as Record<string, unknown>);

    switch (sseEventName) {
        case 'workflow.started':
            return {
                event: 'start',
                workflow_id: withSeq.workflow_id,
                run_id: withSeq.run_id,
                ...(seq !== undefined ? { seq } : {}),
            };
        case 'node.started':
            return {
                event: 'node_start',
                node_id: withSeq.node_id,
                ...(seq !== undefined ? { seq } : {}),
            };
        case 'node.completed':
        case 'node.failed': {
            const handledRaw = withSeq.handled_by_try_catch;
            const handledTc =
                typeof handledRaw === 'string' && handledRaw.trim() !== '' ? handledRaw.trim() : undefined;
            return {
                event: 'node_end',
                node_id: withSeq.node_id,
                result: withSeq.result,
                ...(handledTc !== undefined ? { handled_by_try_catch: handledTc } : {}),
                ...(seq !== undefined ? { seq } : {}),
            };
        }
        case 'workflow.completed':
            return {
                event: 'end',
                result: withSeq.result,
                ...(seq !== undefined ? { seq } : {}),
            };
        case 'workflow.failed':
            return {
                event: 'error',
                error: withSeq.error ?? 'Workflow failed',
                ...(seq !== undefined ? { seq } : {}),
            };
        case 'workflow.events_timeout':
            return {
                event: 'error',
                error: 'SSE events stream timed out; reconnect.',
                ...(seq !== undefined ? { seq } : {}),
            };
        case 'input_required':
            return { event: 'input_required', ...withSeq };
        case 'transcription_job_status':
            return { event: 'transcription_job_status', ...stripNestedEvent(withSeq) };
        default:
            return null;
    }
}

/** Remove accidental ``event`` collision from payloads cloned from NDJSON-era dicts. */
function stripNestedEvent(row: Record<string, unknown>): Record<string, unknown> {
    const { event: _nested, ...rest } = row;
    return rest;
}

export async function consumeWorkflowRunSseResponse(
    response: Response,
    onLegacyEvent: (event: LegacyNdjsonWorkflowEvent) => void,
): Promise<void> {
    if (!response.body) throw new Error('ReadableStream not yet supported in this browser.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split('\n\n');
            buffer = chunks.pop() ?? '';
            for (const chunk of chunks) {
                processSseChunk(chunk, onLegacyEvent);
            }
        }
        if (buffer.trim()) {
            processSseChunk(buffer, onLegacyEvent);
        }
    } finally {
        try {
            reader.releaseLock();
        } catch {
            /* best effort */
        }
    }
}

function processSseChunk(chunkRaw: string, onLegacyEvent: (event: LegacyNdjsonWorkflowEvent) => void): void {
    let evName: string | null = null;
    const dataLines: string[] = [];
    for (const rawLine of chunkRaw.split('\n')) {
        const line = rawLine.replace(/\r$/, '');
        if (!line.trim()) continue;
        if (line.startsWith(':')) continue;
        if (line.startsWith('event:')) evName = line.slice('event:'.length).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart());
    }
    if (!evName || dataLines.length === 0) return;
    let parsed: Record<string, unknown>;
    try {
        parsed = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
    } catch {
        console.warn('failed to parse workflow run SSE JSON', dataLines.join('\n'));
        return;
    }
    const legacy = ssePayloadToLegacyWorkflowEvent(evName, parsed);
    if (legacy) onLegacyEvent(legacy);
}
