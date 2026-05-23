# Sandbox Boards

Boards are persisted playing-field templates for the Sandbox. A board defines grid size, static objects (walls, food, regions), and optional pre-placed creatures (each with a `workflow_id` brain).

See also: [SANDBOX.md](SANDBOX.md) for simulation runtime, tick API, and creature behavior.

## Concepts

| Concept | Description |
|---------|-------------|
| **Board** | Saved template in `sandbox_boards` table (`BoardDefinition` JSON in `body`) |
| **Session** | Live simulation document (`SandboxDocumentEnvelope` in `documents.body`) |
| **Snapshot** | Starting a session copies a board into session state; the session evolves independently |
| **Save back** | Paused sessions can **Save as Board** (new row) or **Update Board** (overwrite source) |

## BoardDefinition JSON (`schema_version: 2.4.0`)

```json
{
  "schema_version": "2.4.0",
  "grid": { "width": 16, "height": 16 },
  "items": [
    { "id": "w1", "type": "wall", "position": { "x": 3, "y": 3 } },
    { "id": "f1", "type": "food", "position": { "x": 5, "y": 5 }, "energy": 48 },
    {
      "id": "r1",
      "type": "region",
      "position": { "x": 2, "y": 2 },
      "color": "#3B82F6",
      "label": "target",
      "trigger": {
        "enabled": false,
        "mode": null,
        "workflow_id": null,
        "inputs": {}
      }
    }
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
| `food` | Reported by **Get nearby**; does not block movement; pickable | **Energy** editable in Explorer (default `48`) |
| `ball` | Reported by **Get nearby** as `ball`; does not block movement; pickable | **Color** at placement (read-only in Explorer after place) |
| `region` | Colored underlay; coexists with other occupants; non-blocking; **`label`** readable via **Get nearby** (`region_label` on each neighbor cell) | **Label**, **Color**, **trigger** stub (editable; not executed yet) |

### Cell occupancy layers

- **Region layer** — at most one region per cell; non-blocking; separate **Place region** / **Remove region** actions
- **Item layer** — at most one food, **ball**, or wall per cell
- **Creature layer** — at most one creature per cell

Regions can be placed on cells that already have creatures or items. Food/wall placement still requires an empty item layer (no creature, no food/wall).

### Creature placement

- **`facing`**: `"N"` \| `"E"` \| `"S"` \| `"W"` (default `"N"` if omitted). Editable in Board Builder Explorer.
- **`color`**: `#RRGGBB` hex (chosen in the placement wizard; not editable in Explorer after placement). Legacy board creatures without `color` render with the index palette.
- **`inventory`**: ordered list of held items (`ball` with `color`, `food` with `energy`). Editable in Board Builder Explorer; read-only during Simulation.
- Compass: North = decreasing y, East = +x.

### Item metadata editing

In **Board Builder**, inspect a cell with an item to open the Explorer. Type-specific metadata fields are editable immediately (changes update local board state and mark the board dirty until **Save**). **Simulation** shows the same fields read-only.

| Item type | Editable fields |
|-----------|-----------------|
| `food` | `energy` (integer ≥ 0) |
| `ball` | — (color chosen at placement) |
| `wall` | — |
| `region` | `label`; `color`; `trigger.enabled`, `trigger.mode`, `trigger.workflow_id`, `trigger.inputs` |

**Adding a new item type:** extend `ItemType` in [`shared/sandbox_canonical.schema.json`](../shared/sandbox_canonical.schema.json) and backend schemas; engine occupancy + movement in [`engine.py`](../backend/app/domain/sandbox/engine.py); **Get nearby** in [`query.py`](../backend/app/domain/sandbox/query.py); interactions + cell modal; Phaser in [`phaserSandboxAdapter.ts`](../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts); Explorer fields in [`sandboxItemInspectorFields.ts`](../frontend/src/sandbox/sandboxItemInspectorFields.ts); tests in `backend/tests/test_sandbox_*.py` and frontend sandbox unit tests.

### Favorite colors

Users can save up to **16** favorite hex colors under **My Settings → View Settings → Favorite colors** (`User.settings.sandbox_favorite_colors`). The first favorite is the default when placing a new region or creature.

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

1. **Simulation** — select a board, run ticks, spawn creatures/items/regions, save layout back to boards
2. **Board Builder** — edit and save board templates without running simulation

### Renaming boards

The toolbar shows an editable **board name** field when a user-owned board is active (same pattern as the Workflow Editor name field).

| Tab | Rename behavior |
|-----|-----------------|
| **Simulation** | Edit the name in the toolbar; rename is saved on **blur** or **Enter** via `PATCH /boards/{id}` (name only) |
| **Board Builder** | Edit the name in the toolbar or Explorer; changes are local until **Save** (name + definition) |

System boards (e.g. **Empty Board**) show a read-only name and cannot be renamed or saved from Board Builder.

Implementation: [frontend/src/components/SandboxView.tsx](../frontend/src/components/SandboxView.tsx), [frontend/src/sandbox/boardBuilderLocalEdits.ts](../frontend/src/sandbox/boardBuilderLocalEdits.ts), [frontend/src/sandbox/sandboxBoardRename.ts](../frontend/src/sandbox/sandboxBoardRename.ts).
