import type { SandboxEnvelopeJson } from '../domain/sandbox/types';

export interface SandboxVisibleError {
    key: string;
    message: string;
    source: 'brain' | 'fixture' | 'region_trigger';
    creatureId?: string;
}

function regionTriggerErrorCreatureId(message: string): string | null {
    const match = message.match(/creature_id=([^,)]+)/);
    return match?.[1]?.trim() ?? null;
}

/** Collect brain, fixture, and region-trigger errors for the simulation error banner. */
export function collectSandboxVisibleErrors(
    envelope: SandboxEnvelopeJson | null | undefined,
    selectedCreatureId: string | null,
): SandboxVisibleError[] {
    if (!envelope) return [];
    const out: SandboxVisibleError[] = [];

    for (const [creatureId, message] of Object.entries(envelope.last_errors ?? {})) {
        if (!message) continue;
        if (selectedCreatureId && creatureId !== selectedCreatureId) continue;
        out.push({ key: `brain:${creatureId}`, message, source: 'brain', creatureId });
    }

    for (const [creatureId, message] of Object.entries(envelope.last_fixture_errors ?? {})) {
        if (!message) continue;
        if (selectedCreatureId && creatureId !== selectedCreatureId) continue;
        out.push({ key: `fixture:${creatureId}`, message, source: 'fixture', creatureId });
    }

    for (const [index, message] of (envelope.last_region_trigger_errors ?? []).entries()) {
        const creatureId = regionTriggerErrorCreatureId(message);
        if (selectedCreatureId && creatureId && creatureId !== selectedCreatureId) continue;
        out.push({
            key: `region:${index}:${message}`,
            message,
            source: 'region_trigger',
            creatureId: creatureId ?? undefined,
        });
    }

    return out;
}
