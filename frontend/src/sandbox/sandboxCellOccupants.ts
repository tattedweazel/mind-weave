import type { SandboxEnvelopeJson, SandboxGridCellJson, SandboxItemJson } from '../domain/sandbox/types';

export interface CellOccupants {
    items: SandboxItemJson[];
    petHere: boolean;
}

export function getCellOccupants(envelope: SandboxEnvelopeJson, cell: SandboxGridCellJson): CellOccupants {
    const { x, y } = cell;
    const items = (envelope.sandbox.world.items ?? []).filter(
        it => it.position.x === x && it.position.y === y,
    );
    const p = envelope.sandbox.pet.position;
    const petHere = p.x === x && p.y === y;
    return { items, petHere };
}

export function cellHasInspectableContent(occupants: CellOccupants): boolean {
    return occupants.items.length > 0 || occupants.petHere;
}
