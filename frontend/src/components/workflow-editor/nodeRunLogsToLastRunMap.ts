import type { NodeRunLog, NodeRunResult } from '../../api/types';

/**
 * Converts persisted node run logs into the same map shape as live stream `node_end` results.
 * When the same `node_id` appears more than once (e.g. for-loop iterations), keeps the row with the highest `step_number`.
 */
export function nodeRunLogsToLastRunMap(logs: NodeRunLog[]): Record<string, NodeRunResult> {
    const map: Record<string, NodeRunResult> = {};
    for (const log of logs) {
        const nr: NodeRunResult = {
            node_id: log.node_id,
            status: log.status,
            output: log.output_data as NodeRunResult['output'],
            error: log.error,
            latency_ms: log.latency_ms,
            details: log.details ?? {},
            step_number: log.step_number ?? undefined,
        };
        const cur = map[log.node_id];
        const sn = nr.step_number ?? 0;
        const prevSn = cur?.step_number ?? 0;
        if (!cur || sn >= prevSn) {
            map[log.node_id] = nr;
        }
    }
    return map;
}
