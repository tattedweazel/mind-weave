# Sandbox Boards

Boards are persisted playing-field templates for the Sandbox. A board defines grid size, static objects (walls, food, regions), and optional pre-placed creatures (each with a `workflow_id` brain).

See also: [SANDBOX.md](SANDBOX.md) for simulation runtime, tick API, and creature behavior. [SANDBOX_DEFINITIONS.md](SANDBOX_DEFINITIONS.md) for definition templates and schema 2.5 migration.

## Concepts

| Concept | Description |
|---------|-------------|
| **Board** | Saved template in `sandbox_boards` table (`BoardDefinition` JSON in `body`) |
| **Board project** | Per-user folder in `board_projects` (independent from workflow projects); boards link via `sandbox_boards.project_id` |
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
| `wall` / terrain definition | Blocks movement and placement | Definition label/name; read-only Id/Position in Explorer |
| `food` / item definition (pickable) | Reported by **Get nearby**; does not block movement; pickable | **Energy** editable in Explorer when the item has energy semantics |
| `ball` | Reported by **Get nearby** as `ball`; does not block movement; pickable | **Color** at placement (read-only in Explorer after place) |
| `fixture` | Solid; workflow-powered; allows pickable stack | Definition label/name, workflow, color — read-only in Explorer |
| `region` | Colored underlay; coexists with other occupants; non-blocking; **`label`** readable via **Get nearby** (`region_label` on each neighbor cell) and **Get position** (`region_label` on the creature’s current cell) | **Label**, **Color**, **trigger** (`enabled`, `mode`, `workflow_id`, `inputs` — executed at runtime; see [SANDBOX.md — Region triggers](SANDBOX.md#region-triggers)) |

### Cell occupancy layers

See [SANDBOX_DEFINITIONS.md — Stacked cells](SANDBOX_DEFINITIONS.md#stacked-cells) for the authoritative 2.5 model:

- **Region layer** — 0..1 per cell; non-blocking; separate **Place region** / **Remove region** actions
- **Solid layer** — 0..1 terrain (wall) **or** fixture; blocks movement
- **Pickable layer** — 0..N food, ball, or definition-backed items; may stack on a fixture
- **Creature layer** — 0..1 per cell

Regions can be placed on cells that already have creatures, fixtures, or pickables. Pickables may stack on fixture cells. Terrain (wall) and fixtures are mutually exclusive at the solid layer.

### Creature placement

- **`facing`**: `"N"` \| `"E"` \| `"S"` \| `"W"` (default `"N"` if omitted). Editable in Board Builder Explorer.
- **`color`**: `#RRGGBB` hex (chosen in the placement wizard; not editable in Explorer after placement). Legacy board creatures without `color` render with the index palette.
- **`inventory`**: ordered list of held items (`ball` with `color`, `food` with `energy`; optional `definition_id` for definition-backed pickables). Editable in Board Builder Explorer; read-only during Simulation.
- Compass: North = decreasing y, East = +x.

### Item metadata editing

In **Board Builder**, inspect a cell with an item to open the Explorer. Type-specific metadata fields are editable immediately (changes update local board state and mark the board dirty until **Save**). **Simulation** shows the same fields read-only.

| Item type | Editable fields |
|-----------|-----------------|
| `food` / definition-backed pickable with energy | `energy` (integer ≥ 0) |
| `ball` | — (color chosen at placement) |
| `wall` / terrain definition | — |
| `fixture` | — (placed/removed via cell action modal) |
| `region` | `label`; `color`; `trigger.enabled`, `trigger.mode`, `trigger.workflow_id`, `trigger.inputs` |

**Adding a new item type:** extend `ItemType` in [`shared/sandbox_canonical.schema.json`](../shared/sandbox_canonical.schema.json) and backend schemas; engine occupancy + movement in [`engine.py`](../backend/app/domain/sandbox/engine.py); **Get nearby** in [`query.py`](../backend/app/domain/sandbox/query.py); interactions + cell modal; Phaser in [`phaserSandboxAdapter.ts`](../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts); Explorer display in [`sandboxItemInspectorDisplay.ts`](../frontend/src/sandbox/sandboxItemInspectorDisplay.ts) and fields in [`sandboxItemInspectorFields.ts`](../frontend/src/sandbox/sandboxItemInspectorFields.ts); tests in `backend/tests/test_sandbox_*.py` and frontend sandbox unit tests.

### Favorite colors

Users can save up to **16** favorite hex colors under **My Settings → View Settings → Favorite colors** (`User.settings.sandbox_favorite_colors`). The first favorite is the default when placing a new region or creature.

## HTTP API

### Board projects

Base: `/api/v1/board-projects`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | List folders + board counts (includes seeded **Shared**) |
| `POST` | `/` | Create folder |
| `PATCH` | `/{id}` | Rename / reorder |
| `DELETE` | `/{id}?delete_boards=` | Delete folder (non-empty requires `delete_boards=true` to cascade-delete boards) |

### Boards

Base: `/api/v1/sandbox/boards`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/boards` | List user boards + system boards |
| `POST` | `/boards` | Create board (optional `project_id`; defaults to **Shared**) |
| `GET` | `/boards/{id}` | Read board |
| `PATCH` | `/boards/{id}` | Update board (not system rows); optional `project_id` to move between folders |
| `DELETE` | `/boards/{id}` | Delete board (not system rows) |
| `POST` | `/boards/{id}/duplicate` | Duplicate board (copy inherits source `project_id`) |

Session save-back: `POST /api/v1/sandbox/sessions/{id}/save-board` with `{ "mode": "save_as_new" | "update_source", "name"?: string, "project_id"?: string }` (requires paused playback; `project_id` applies to **save_as_new** only).

Existing user boards are backfilled into **Shared** on migration. System boards keep `project_id = null`.

## Built-in Empty Board

System row `builtin_slug = empty_sandbox_board` (`EMPTY_SANDBOX_BOARD_ID` in `builtins.py`). Used when `POST /sessions` omits `board_id`. On first Sandbox load, selecting **Empty Board** shows the default 16×16 grid on the canvas immediately — no **Apply grid** step required.

## UI

Sandbox view has two tabs:

1. **Simulation** — select a board, run ticks, spawn creatures/items/regions, save layout back to boards
2. **Board Builder** — edit and save board templates without running simulation

### Board projects (left sidebar)

The **Boards** sidebar mirrors Workflow Editor project organization (independent folders):

- **System boards** (e.g. **Empty Board**) stay pinned at the top, outside any project
- **Project list** — **New project…**, then folders with board counts (seeded **Shared** row)
- **Drill-in** — **Back**, folder title, **Delete project** (inline confirm; non-empty warns before cascade), sort (**Last updated** / **Name A–Z**), **Filter…**, board rows with **Move** and **Delete**
- **Delete board** — trash on each board row and in the toolbar when a user-owned board is active; inline confirm; after deleting the active board, stay in the project and select the next board (or clear the canvas if it was the last)

New boards (**Board Builder → Save**, **Simulation → Save as Board**) land in the currently open project, or **Shared** when no project is drilled in.

### Renaming boards

The toolbar shows an editable **board name** field when a user-owned board is active (same pattern as the Workflow Editor name field).

| Tab | Rename behavior |
|-----|-----------------|
| **Simulation** | Edit the name in the toolbar; rename is saved on **blur** or **Enter** via `PATCH /boards/{id}` (name only) |
| **Board Builder** | Edit the name in the toolbar or Explorer; changes are local until **Save** (name + definition) |

System boards (e.g. **Empty Board**) show a read-only name and cannot be renamed or saved from Board Builder.

Implementation: [frontend/src/components/SandboxView.tsx](../frontend/src/components/SandboxView.tsx), [frontend/src/domain/boardProjectMembership.ts](../frontend/src/domain/boardProjectMembership.ts), [frontend/src/sandbox/boardBuilderLocalEdits.ts](../frontend/src/sandbox/boardBuilderLocalEdits.ts), [frontend/src/sandbox/sandboxBoardRename.ts](../frontend/src/sandbox/sandboxBoardRename.ts).
