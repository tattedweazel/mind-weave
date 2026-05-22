# Sandbox (board-driven simulation)

Operational reference for **Sandbox V2.2**: board templates, multi-creature sessions, per-creature workflow brains, **atomic navigation ticks**, and Phaser as view-only renderer.

Related: [BOARDS.md](BOARDS.md), [shared/sandbox_canonical.schema.json](../shared/sandbox_canonical.schema.json).

## Architecture

| Layer | Owns |
|-------|------|
| **Boards** | `sandbox_boards` table, `BoardDefinition` JSON — see [BOARDS.md](BOARDS.md) |
| **Domain** | `CreatureState` (position + **facing**), `SandboxState`, engine rules (`backend/app/domain/sandbox/engine.py`) |
| **Workflows** | Per-creature `workflow_id`; `SandboxTickInput` with focused `creature` + all `creatures` |
| **Persistence** | Session `Document.body` → `SandboxDocumentEnvelope` (`schema_version: 2.2.0`) |
| **HTTP** | `backend/app/api/v1/sandbox.py` |
| **SPA** | [SandboxView.tsx](../frontend/src/components/SandboxView.tsx) — **Simulation** + **Board Builder** tabs |

**Phaser is not the simulation engine.** It renders grid state and forwards cell clicks only.

## Atomic ticks

Each HTTP tick:

1. Apply interactions once
2. Advance global tick counter once
3. For each creature in **array order**:
   - **Always** run that creature's `workflow_id` graph with tick input scoped to that creature
   - Apply the resulting **one** navigation action (`move_forward`, `turn_left`, `turn_right`, or `idle`)

There is no multi-tick `move_to` or intent continuation. Every tick is a fresh brain execution.

Response includes `last_workflow_runs: Record<creatureId, WorkflowRunResult | null>` and `envelope.last_errors`.

## Sandbox Utilities (palette)

Navigation-focused utilities in the workflow editor (**Sandbox Utilities** section):

| Utility | Role |
|---------|------|
| **Tick input** (`sandbox_tick` primitive) | Full `SandboxTickInput` dict (includes `tick` for scripted sequences) |
| **Get position** | Focused creature `{x, y}` |
| **Get facing** | `"N"` \| `"E"` \| `"S"` \| `"W"` |
| **Get nearby** | Eight neighbors clockwise from facing; each `{x, y, kind}` where `kind` is `empty`, `wall`, `food`, `creature`, or `out_of_bounds` |
| **Move forward** | Emits `{action: "move_forward"}` for Stop |
| **Turn left** / **Turn right** | Emits turn action dict for Stop |
| **Idle** | Emits `{action: "idle"}` for Stop |

Wire one action node (or a conditional that picks one) to **Stop** `output` (dictionary).

Compass: **North = decreasing y**, East = +x. Default spawn facing: **North**.

### Starter workflow

Built-in graph: **Start → Get nearby → forward-cell kind → Is empty? → Move forward (true) / Turn left (false) → Stop** (left-hand wall follower). Wire **Is** `true`/`false` branch handles directly to action nodes — do not chain **Is → Basic Conditional**, because the conditional only schedules on its `true` incoming branch and will skip the `false` path from **Is**.

If forward `kind == "empty"`, **Move forward**; otherwise **Turn left** (walls, canvas edge / `out_of_bounds`, creatures, food).

Seeded as `starter_sandbox_behavior` via [`starter_workflow_seed.py`](../backend/app/domain/sandbox/starter_workflow_seed.py).

### Example brains

**Reactive wall follower** (same as starter): each tick, index `0` of **Get nearby** is the forward cell; if `kind == "empty"`, **Move forward**, else **Turn left**.

**Scripted brute-force path**: use **Tick input** → **Dictionary value by key** (`tick`) → conditionals mapping tick numbers to **Move forward** / **Turn left** / **Turn right** nodes.

## Schema 2.2.0 (regions)

Adds **`region`** items: colored full-cell underlays for visual reference. Regions **coexist** with food, walls, and creatures on the same cell; they do **not** block movement or **Get nearby** sensing (cells with only a region report `kind: "empty"`). Trigger metadata is stored on each region but **not executed** yet — see [Future: region triggers](#future-region-triggers).

## Breaking change (2.1.0)

Legacy pet-sim actions (`move_to`, `wander`, `eat_nearby`, `sleep`) and old sandbox utilities were removed. Saved workflows referencing removed node types parse as **invalid steps**. Existing boards/sessions are migrated to add `facing: "N"` and drop `hunger` / `energy` / `mood` / `intent`.

## HTTP API (authenticated)

Base: `/api/v1/sandbox/`

| Method | Path | Purpose |
|--------|------|---------|
| `GET/POST` | `/boards` | List / create boards |
| `GET/PATCH/DELETE` | `/boards/{id}` | Board CRUD |
| `POST` | `/boards/{id}/duplicate` | Duplicate board |
| `POST` | `/sessions` | Create session (`board_id` optional → Empty Board) |
| `GET` | `/sessions/{id}` | Load envelope |
| `POST` | `/sessions/{id}/tick` | Run tick (`interactions`, `state_version`) |
| `POST` | `/sessions/{id}/interactions` | Apply cell edits without advancing tick (paused only) |
| `POST` | `/sessions/{id}/grid` | Resize grid (paused only) |
| `POST` | `/sessions/{id}/save-board` | Save session layout as board |
| `GET` | `/starter-workflow-id` | Starter workflow UUID (for creature placement UI) |

## Interactions

| `type` | Payload | Behavior |
|--------|---------|----------|
| `place_item` | `cell`, `item_type`: `food` \| `wall` | Place if no creature and no food/wall at cell (regions ignored) |
| `remove_item` | `cell` | Remove food/wall only (regions remain) |
| `place_region` | `cell`, `color` (`#RRGGBB`) | Place or replace region at cell (allowed on occupied cells) |
| `remove_region` | `cell` | Remove region only |
| `place_creature` | `cell`, `workflow_id`, optional `name`, optional `facing` (`N`/`E`/`S`/`W`, default **N**) | Spawn creature if no creature and no food/wall (regions ignored) |
| `remove_creature` | `cell` | Remove creature at cell |

Paused cell edits in **Simulation** use `/interactions` so layout changes do not advance the tick counter or run workflow brains. Use **Play** or **Step** (`/tick`) to advance simulation.

## UI

- **Simulation tab**: board picker, play/pause/step, cell action menu, per-creature Explorer + Run Logs
- **Board Builder tab**: edit/save boards without ticking; creature **facing** editable in Explorer

When placing a creature (Simulation or Board Builder), the cell action modal includes an **Initial facing** picker (`N`/`E`/`S`/`W`, default North). Placement does not auto-advance ticks — press **Play** or **Step** to run brains.

**Tick ms** in Explorer sets the client-side Play interval (200–60000 ms). It does not advance simulation or require pause; commit with Enter or by leaving the field (partial values while typing do not affect playback until committed).

### Run Logs

Each tick runs the creature brain, so **Run Logs** update every tick (no movement-only skip).

Implementation: [`SandboxView.tsx`](../frontend/src/components/SandboxView.tsx), [`sandboxWorkflowRunMerge.ts`](../frontend/src/sandbox/sandboxWorkflowRunMerge.ts).

## Placeholder visuals

| Item | Default |
|------|---------|
| Grid | 16×16 (8–64 via resize) |
| Creature | Colored rectangles with facing indicator |
| Food | Pink circle |
| Wall | Gray square |
| Region | Full-cell colored underlay (~35% opacity), drawn under other items |
| Cell | 48px |

Constants: `frontend/src/sandbox/sandboxVisualDefaults.ts`, `backend/app/domain/sandbox/constants.py`.

Favorite region colors: **My Settings → View Settings → Favorite colors** (`User.settings.sandbox_favorite_colors`, up to 16 hex swatches).

## Future: region triggers

Each region may store a **trigger** stub (`enabled`, `mode`, `workflow_id`, `inputs`). Modes: `enter`, `exit`, `while_inside`, `on_enter_once`. When implemented, the engine will track creature overlap and run the configured workflow with static inputs (e.g. “reach the blue square” → `enter` trigger fires an end-state workflow). Configuration is editable in Board Builder Explorer today; simulation does not evaluate triggers yet.

## Feature flags

| Flag | Purpose |
|------|---------|
| `SANDBOX_ENABLED` | Backend 404 when false |
| `VITE_SANDBOX_ENABLED` | Hide nav when false |
