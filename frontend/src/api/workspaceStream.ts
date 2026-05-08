/**
 * Consume Server-Sent Events style stream from POST /workspaces/.../turns/stream
 * and POST .../turns/confirm-stream.
 */

export type WorkspaceStartSlotMeta = {
    key: string;
    input_type: string;
    required: boolean;
};

export type WorkspaceCapabilityProposalCap = {
    capability_key: string;
    name: string;
    input_bindings: Record<string, unknown>;
    start_slots?: WorkspaceStartSlotMeta[];
    missing_start_binding_keys?: string[];
};

export type WorkspaceStreamDoneMeta = {
    phase?: 'proposal' | 'completed' | 'cancelled';
    proposal_id?: string;
    turn_id?: string;
    replay_id?: string;
    memory_proposed?: number;
};

export type WorkspaceStreamStageEvent = {
    stage: string;
    status: 'started' | 'completed';
    ms?: number;
    detail?: Record<string, unknown>;
};

export async function consumeWorkspaceTurnStream(
    response: Response,
    onToken: (text: string) => void,
    onDone: (meta: WorkspaceStreamDoneMeta) => void,
    onProposal?: (p: { proposal_id: string; capabilities: WorkspaceCapabilityProposalCap[] }) => void,
    onStage?: (e: WorkspaceStreamStageEvent) => void,
): Promise<void> {
    if (!response.body) {
        throw new Error('No response body');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const segments = buffer.split('\n\n');
        buffer = segments.pop() ?? '';
        for (const segment of segments) {
            for (const line of segment.split('\n')) {
                if (line.startsWith('data: ')) {
                    const raw = line.slice(6).trim();
                    if (!raw) {
                        continue;
                    }
                    try {
                        const json = JSON.parse(raw) as {
                            event?: string;
                            text?: string;
                            turn_id?: string;
                            replay_id?: string;
                            memory_proposed?: number;
                            phase?: string;
                            proposal_id?: string;
                            capabilities?: WorkspaceCapabilityProposalCap[];
                            stage?: string;
                            status?: string;
                            ms?: number;
                            detail?: Record<string, unknown>;
                        };
                        if (json.event === 'token' && typeof json.text === 'string') {
                            onToken(json.text);
                        }
                        if (
                            json.event === 'stage' &&
                            onStage &&
                            typeof json.stage === 'string' &&
                            (json.status === 'started' || json.status === 'completed')
                        ) {
                            onStage({
                                stage: json.stage,
                                status: json.status,
                                ms: typeof json.ms === 'number' ? json.ms : undefined,
                                detail: json.detail,
                            });
                        }
                        if (json.event === 'capability_proposal' && onProposal && typeof json.proposal_id === 'string') {
                            onProposal({
                                proposal_id: json.proposal_id,
                                capabilities: Array.isArray(json.capabilities) ? json.capabilities : [],
                            });
                        }
                        if (json.event === 'done') {
                            onDone({
                                phase:
                                    json.phase === 'proposal' ||
                                    json.phase === 'completed' ||
                                    json.phase === 'cancelled'
                                        ? json.phase
                                        : undefined,
                                proposal_id: typeof json.proposal_id === 'string' ? json.proposal_id : undefined,
                                turn_id: json.turn_id,
                                replay_id: json.replay_id,
                                memory_proposed: json.memory_proposed,
                            });
                        }
                    } catch {
                        /* ignore malformed line */
                    }
                }
            }
        }
    }
}
