# Sandbox Boards

Boards are persisted playing-field templates for the Sandbox. A board defines grid size, static objects (walls, food), and optional pre-placed creatures (each with a `workflow_id` brain).

See also: [SANDBOX.md](SANDBOX.md) for simulation runtime, tick API, and creature behavior.

## Concepts

| Concept | Description |
|---------|-------------|
| **Board** | Saved template in `sandbox_boards` table (`BoardDefinition` JSON in `body`) |
| **Session** | Live simulation document (`SandboxDocumentEnvelope` in `documents.body`) |
| **Snapshot** | Starting a session copies a board into session state; the session evolves independently |
| **Save back** | Paused sessions can **Save as Board** (new row) or **Update Board** (overwrite source) |

## BoardDefinition JSON (`schema_version: 2.1.0`)

```json
{
  "schema_version": "2.1.0",
  "grid": { "width": 16, "height": 16 },
  "items": [
    { "id": "w1", "type": "wall", "position": { "x": 3, "y": 3 } },
    { "id": "f1", "type": "food", "position": { "x": 5, "y": 5 }, "energy": 48 }
  ],
  "creatures": [
    {
      "id": "c1",
      "workflow_id": "<uuid>",
      "name": "Scout",
      "position": { "x": 8, "y": 8 },
      "facing": "N"
    }
  ]
}
```

### Item types

| Type | Behavior | Board Builder metadata |
|------|----------|------------------------|
| `wall` | Blocks movement and placement | None (read-only Id/Type/Position in Explorer) |
| `food` | Reported by **Get nearby**; does not block movement | **Energy** editable in Explorer (default `48`) |

### Creature placement

- **`facing`**: `"N"` \| `"E"` \| `"S"` \| `"W"` (default `"N"` if omitted). Editable in Board Builder Explorer.
- Compass: North = decreasing y, East = +x.

### Item metadata editing

In **Board Builder**, inspect a cell with an item to open the Explorer. Type-specific metadata fields are editable immediately (changes update local board state and mark the board dirty until **Save**). **Simulation** shows the same fields read-only.

| Item type | Editable fields |
|-----------|-----------------|
| `food` | `energy` (integer ≥ 0) |
| `wall` | — |

**Adding a new item type with metadata:** extend `ItemType` in [`shared/sandbox_canonical.schema.json`](../shared/sandbox_canonical.schema.json) and backend schemas, then register Explorer fields in [`sandboxItemInspectorFields.ts`](../frontend/src/sandbox/sandboxItemInspectorFields.ts).

## HTTP API

Base: `/api/v1/sandbox/boards`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/boards` | List user boards + system boards |
| `POST` | `/boards` | Create board |
| `GET` | `/boards/{id}` | Read board |
| `PATCH` | `/boards/{id}` | Update board (not system rows) |
| `DELETE` | `/boards/{id}` | Delete board (not system rows) |
| `POST` | `/boards/{id}/duplicate` | Duplicate board |

Session save-back: `POST /api/v1/sandbox/sessions/{id}/save-board` with `{ "mode": "save_as_new" | "update_source", "name"?: string }` (requires paused playback).

## Built-in Empty Board

System row `builtin_slug = empty_sandbox_board` (`EMPTY_SANDBOX_BOARD_ID` in `builtins.py`). Used when `POST /sessions` omits `board_id`.

## UI

Sandbox view has two tabs:

1. **Simulation** — select a board, run ticks, spawn creatures/items, save layout back to boards
2. **Board Builder** — edit and save board templates without running simulation

Implementation: [frontend/src/components/SandboxView.tsx](../frontend/src/components/SandboxView.tsx), [frontend/src/sandbox/boardBuilderLocalEdits.ts](../frontend/src/sandbox/boardBuilderLocalEdits.ts).
