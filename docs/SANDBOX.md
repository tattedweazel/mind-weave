# Sandbox (board-driven simulation)

Operational reference for **Sandbox V2.1**: board templates, multi-creature sessions, per-creature workflow brains, **atomic navigation ticks**, and Phaser as view-only renderer.

Related: [BOARDS.md](BOARDS.md), [shared/sandbox_canonical.schema.json](../shared/sandbox_canonical.schema.json).

## Architecture

| Layer | Owns |
|-------|------|
| **Boards** | `sandbox_boards` table, `BoardDefinition` JSON — see [BOARDS.md](BOARDS.md) |
| **Domain** | `CreatureState` (position + **facing**), `SandboxState`, engine rules (`backend/app/domain/sandbox/engine.py`) |
| **Workflows** | Per-creature `workflow_id`; `SandboxTickInput` with focused `creature` + all `creatures` |
| **Persistence** | Session `Document.body` → `SandboxDocumentEnvelope` (`schema_version: 2.1.0`) |
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
| `POST` | `/sessions/{id}/grid` | Resize grid (paused only) |
| `POST` | `/sessions/{id}/save-board` | Save session layout as board |
| `GET` | `/starter-workflow-id` | Starter workflow UUID (for creature placement UI) |

## Interactions

| `type` | Payload | Behavior |
|--------|---------|----------|
| `place_item` | `cell`, `item_type`: `food` \| `wall` | Place if cell empty |
| `remove_item` | `cell` | Remove items at cell |
| `place_creature` | `cell`, `workflow_id`, optional `name` | Spawn creature (facing **N**) |
| `remove_creature` | `cell` | Remove creature at cell |

## UI

- **Simulation tab**: board picker, play/pause/step, cell action menu, per-creature Explorer + Run Logs
- **Board Builder tab**: edit/save boards without ticking; creature **facing** editable in Explorer

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
| Cell | 48px |

Constants: `frontend/src/sandbox/sandboxVisualDefaults.ts`, `backend/app/domain/sandbox/constants.py`.

## Feature flags

| Flag | Purpose |
|------|---------|
| `SANDBOX_ENABLED` | Backend 404 when false |
| `VITE_SANDBOX_ENABLED` | Hide nav when false |
