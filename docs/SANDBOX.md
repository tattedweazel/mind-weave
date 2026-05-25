# Sandbox (board-driven simulation)

Operational reference for **Sandbox V2.5**: board templates, multi-creature sessions, per-creature workflow brains, **Definitions**-backed placeables, fixture workflows, **atomic navigation ticks**, creature **inventory**, and Phaser as view-only renderer.

Related: [BOARDS.md](BOARDS.md), [SANDBOX_DEFINITIONS.md](SANDBOX_DEFINITIONS.md), [shared/sandbox_canonical.schema.json](../shared/sandbox_canonical.schema.json).

## Architecture

| Layer | Owns |
|-------|------|
| **Boards** | `sandbox_boards` table, `BoardDefinition` JSON — see [BOARDS.md](BOARDS.md) |
| **Domain** | `CreatureState` (position + **facing**), `SandboxState`, engine rules (`backend/app/domain/sandbox/engine.py`) |
| **Workflows** | Per-creature `workflow_id`; `SandboxTickInput` with focused `creature` + all `creatures` |
| **Persistence** | Session `Document.body` → `SandboxDocumentEnvelope` (`schema_version: 2.4.0`) |
| **HTTP** | `backend/app/api/v1/sandbox.py` |
| **SPA** | [SandboxView.tsx](../frontend/src/components/SandboxView.tsx) — **Simulation**, **Board Builder**, and **Definitions** tabs |

**Phaser is not the simulation engine.** It renders grid state and forwards cell clicks only.

## Atomic ticks

Each HTTP tick:

1. Apply interactions once
2. Advance global tick counter once
3. For each creature in **array order**:
   - **Always** run that creature's `workflow_id` graph with tick input scoped to that creature
   - Apply the resulting **one** action (`move_forward`, `turn_left`, `turn_right`, `idle`, `pick_up_item`, `place_item`, or `use_fixture`)

There is no multi-tick `move_to` or intent continuation. Every tick is a fresh brain execution.

Response includes `last_workflow_runs: Record<creatureId, WorkflowRunResult | null>`, `nested_workflow_runs` (fixture and region-trigger runs from the tick, each with `meta` + full `WorkflowRunResult`), `envelope.last_errors` (brain/decision failures), `envelope.last_fixture_errors`, `envelope.last_region_trigger_errors`, and optional `simulation_effects` (e.g. `{ "force_pause": true }` when a region trigger workflow requests pause).

Nested sandbox runs are **ephemeral** tick payloads only — they are not persisted to `workflow_runs` / Explore history.

## Sandbox Utilities (palette)

Navigation-focused utilities in the workflow editor (**Sandbox Utilities** section):

| Utility | Role |
|---------|------|
| **Tick input** (`sandbox_tick` primitive) | Full `SandboxTickInput` dict (includes `tick` for scripted sequences) |
| **Get position** | Cell probe for the focused creature's current cell, or the **fixture cell** in fixture workflows — see [Cell probe shape](#cell-probe-shape) |
| **Get facing** | `"N"` \| `"E"` \| `"S"` \| `"W"` |
| **Get nearby** | Eight neighbors clockwise from facing; each cell uses the [cell probe shape](#cell-probe-shape) |
| **Get inventory** | List of held items on the focused creature (`{type, color?}` or `{type, energy?}`) |
| **Get cell items** | List of pickables at the **fixture cell** — **simulation-only** during fixture `use_fixture` workflows |
| **Remove item** | Remove a pickable by instance **`item_id`** at the fixture cell — fixture workflows only; set `item_id` in Explorer or wire from a loop |
| **Spawn item** | Spawn a pickable at the fixture cell (or neighbor via `target`) — fixture workflows only; set `definition_id`, `target`, optional `energy`/`color` in Explorer or wire handles |
| **Move forward** | Emits `{action: "move_forward"}` for Stop |
| **Turn left** / **Turn right** | Emits turn action dict for Stop |
| **Idle** | Emits `{action: "idle"}` for Stop |
| **Pick up item** | Emits `{action: "pick_up_item"}` — picks up **ball** or **food** in the **forward adjacent** cell into inventory |
| **Place item** | Emits `{action: "place_item", item_type?: "ball" \| "food", inventory_index?: number}` — places the chosen inventory entry (by index, or first / first matching `item_type`) on the **forward adjacent** cell |
| **Prompt for User Action** | Emits a `DecisionIntent` chosen in the **Simulation** remote-control modal (see below) |
| **Force Simulation Pause** | Emits `{ "pause": true }` and sets tick `simulation_effects.force_pause` — **simulation-only** (region trigger workflows, etc.) |

**Broadcast Message** (`broadcast_message` utility) is available in the general **Utilities** palette (not Sandbox-only). During a tick, creature brains, region triggers, and fixture workflows may emit segments collected server-side into `simulation_effects.broadcast_messages`. After the tick completes, the SPA shows **one combined modal** (numbered sections, optional source chips) and **pauses playback** until **Continue** — blocking the next auto-tick until dismissed.

Wire one action node (or a conditional that picks one) to **Stop** `output` (dictionary).

### Cell probe shape

**Get position**, **Get nearby** (each neighbor), and the Simulation **Position** / **Nearby** sensory probes share this dictionary shape:

| Field | Type | Notes |
|-------|------|-------|
| `x`, `y` | int | Cell coordinates |
| `kind` | string | `empty`, `wall`, `food`, `ball`, `fixture`, `creature`, or `out_of_bounds` |
| `region_label` | string \| null | Region underlay label; `null` when no region; `""` when region exists but is unlabeled |
| `stack_count` | int | Number of pickables at the cell (0 when none) |
| `items` | list | Pickable summaries at the cell (excludes fixture, region, wall, creatures) |

Each item summary: `{ id, kind, definition_id?, energy?, color?, label }`. **`kind`** is `item` for definition-backed pickables, or legacy built-in types (`food`, `ball`) when no definition is linked. **`energy`** and **`color`** use instance values when set, otherwise fall back to the item definition defaults. **`label`** is resolved for display: instance `label` when set, else the item definition's label, else a built-in fallback (`Food (48)`, `Ball (#RRGGBB)`, etc.).

In **creature brain** / `sandbox_tick` context, **Get position** probes the focused creature's cell. In **fixture workflows** (server-injected `sandbox_fixture` run override), **Get position** probes the **fixture cell** (where stacked pickables live). **Get facing**, **Get nearby**, and **Get inventory** still use the interacting actor's position/facing in fixture workflows. **Get cell items**, **Remove item**, and **Spawn item** run during fixture `use_fixture` workflows only; see [SANDBOX_DEFINITIONS.md — Fixture interaction](SANDBOX_DEFINITIONS.md#fixture-interaction-use_fixture).

### Manual control brain (Prompt for User Action)

Example graph for testing:

**Start** (`sandbox_tick`) → **Prompt for User Action** → **Stop** (`output`, dictionary)

On each **Step** or **Play** tick, the SPA **auto-pauses**, opens a **remote-control** modal per creature (in creature array order) whose brain includes this node, then submits all choices in one tick request.

| Simulation UI | Behavior |
|---------------|----------|
| D-pad | **Forward**, **Turn left**, **Turn right**, **Idle** |
| Secondary | **Pick up item** only when forward cell is **ball** or **food**; **Place item** only when the creature holds at least one item — opens **Inventory** selection (choose a held item; **Confirm** requires an empty forward cell) |
| Sensory probes | **Nearby**, **Position**, **Facing**, **Inventory** — client-side reads from the current envelope (no extra HTTP). One structured readout at a time (latest click replaces the previous): compass ring for **Nearby** (primary kind badge plus a separate **Region** chip when `region_label` is present; labeled regions show the label text, unlabeled regions show **Region**), coordinate rows for **Position**, compass badge for **Facing**, inventory cards for **Inventory** (balls show a colored **Ball** label and matching swatch; food shows **Food** with a separate energy badge; selectable rows when **Place item** is active). Optional collapsible **Raw JSON** for debugging. Re-click the active probe to collapse; cached results restore on re-open for the modal session. |
| Cancel | Aborts the tick; playback stays paused |
| Confirm | Submits the tick; **Play** resumes if it was active before the modal opened (**Step** stays paused) |

**Tick body** (optional):

```json
{
  "interactions": [],
  "state_version": 1,
  "creature_user_actions": {
    "creature-id": {
      "action": "place_item",
      "item_type": "ball",
      "inventory_index": 0
    }
  }
}
```

The executor receives `sandbox_user_action` in `input_overrides` for that creature’s brain run. `reason` is auto-filled (e.g. `user: move_forward`, `user: place_item:ball@0`) and appears in **Run Logs**. Brains without this node ignore `creature_user_actions`. Brains with the node but no entry for that creature record `last_errors` and skip applying a decision for that creature.

Compass: **North = decreasing y**, East = +x. Default spawn facing: **North**.

### Starter workflow

Built-in graph: **Start → Get nearby → forward-cell kind → Is empty? → Move forward (true) / Turn left (false) → Stop** (left-hand wall follower). Wire **Is** `true`/`false` branch handles directly to action nodes — do not chain **Is → Basic Conditional**, because the conditional only schedules on its `true` incoming branch and will skip the `false` path from **Is**.

If forward `kind == "empty"`, **Move forward**; otherwise **Turn left** (walls, canvas edge / `out_of_bounds`, creatures, food).

Seeded as `starter_sandbox_behavior` via [`starter_workflow_seed.py`](../backend/app/domain/sandbox/starter_workflow_seed.py).

### Example brains

**Reactive wall follower** (same as starter): each tick, index `0` of **Get nearby** is the forward cell; if `kind == "empty"`, **Move forward**, else **Turn left**.

**Scripted brute-force path**: use **Tick input** → **Dictionary value by key** (`tick`) → conditionals mapping tick numbers to **Move forward** / **Turn left** / **Turn right** nodes.

## Schema 2.4.0 (region labels)

Each **`region`** item stores a required string **`label`** (may be `""`). **Get nearby** exposes region metadata on each neighbor cell as **`region_label`**: `null` when no region is present, otherwise the region’s label (including empty string). Primary **`kind`** is unchanged — a cell with only a region still reports `kind: "empty"`; food/wall/ball/creature kinds take precedence when stacked. Regions **do not** block movement.

Example brain pattern: **Get nearby** → index `0` (forward) → **Dictionary value by key** `region_label` → **Is?** vs `"target"` → branch to an action.

## Schema 2.2.0 (regions)

Adds **`region`** items: colored full-cell underlays. Regions **coexist** with food, walls, and creatures on the same cell. Each region stores optional **trigger** metadata (`enabled`, `mode`, `workflow_id`, `inputs`) — see [Region triggers](#region-triggers).

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
| `POST` | `/sessions/{id}/tick` | Run tick (`interactions`, `state_version`, optional `creature_user_actions` for [Prompt for User Action](#manual-control-brain-prompt-for-user-action) brains) |
| `POST` | `/sessions/{id}/interactions` | Apply cell edits without advancing tick (paused only) |
| `POST` | `/sessions/{id}/grid` | Resize grid (paused only) |
| `POST` | `/sessions/{id}/save-board` | Save session layout as board |
| `GET` | `/starter-workflow-id` | Starter workflow UUID (for creature placement UI) |

## Interactions

| `type` | Payload | Behavior |
|--------|---------|----------|
| `place_item` | `cell`, `item_type`: `food` \| `wall` \| `ball`, optional `definition_id`, `color` required for `ball` | Place pickable or terrain if no creature; pickables may stack on fixture cells (0..N pickables); terrain blocked when any solid exists (regions ignored) |
| `remove_item` | `cell`, optional `item_id` | Remove pickables and non-fixture solids at cell; fixtures and regions remain; omit `item_id` to clear all removable items at once |
| `place_fixture` | `cell`, `definition_id` | Place solid fixture if no creature and no existing solid |
| `remove_fixture` | `cell` | Remove fixture only; pickables at cell remain |
| `place_region` | `cell`, `color` (`#RRGGBB`), optional `label` (string, default `""`) | Place or replace region at cell (allowed on occupied cells) |
| `remove_region` | `cell` | Remove region only |
| `place_creature` | `cell`, `workflow_id`, `color` (`#RRGGBB`), optional `name`, optional `facing` (`N`/`E`/`S`/`W`, default **N**) | Spawn creature if no creature and no food/wall (regions ignored) |
| `remove_creature` | `cell` | Remove creature at cell |

Paused cell edits in **Simulation** use `/interactions` so layout changes do not advance the tick counter or run workflow brains. Use **Play** or **Step** (`/tick`) to advance simulation.

## UI

- **Simulation tab**: board picker, play/pause/step, cell action menu, per-creature Explorer + Run Logs
- **Board Builder tab**: edit/save boards without ticking; creature **facing** editable in Explorer. After **Save**, switching to **Simulation** starts a fresh session from the saved board so the grid matches your edits.

On first Sandbox visit after a page load, **Simulation** renders the session grid immediately (including the default **Empty Board** 16×16 grid). **Apply grid** in Explorer is only for intentional resize — not required to see the board on load.

When placing a creature (Simulation or Board Builder), the cell action modal steps through **workflow** → **initial facing** (`N`/`E`/`S`/`W`, default North) → **color** (presets, favorites, or custom hex). Placement does not auto-advance ticks — press **Play** or **Step** to run brains.

**Place item** on an empty cell opens **Item** (user item definitions from Definitions) → **Terrain** (user terrain definitions) → **Built-ins** (legacy food, wall, and ball placement). Seeded system definitions (`is_system`) are excluded from the Item/Terrain pickers; use **Built-ins** for Food/Wall/Ball.

**Tick ms** in Explorer sets the client-side Play interval (200–60000 ms). It does not advance simulation or require pause; commit with Enter or by leaving the field (partial values while typing do not affect playback until committed).

### Viewport (board zoom)

The Phaser board uses a **camera viewport** sized to the center panel (not the full board pixel canvas). Large grids (up to **64×64**) stay usable by zooming out to fit.

| Input | Behavior |
|-------|----------|
| **Scroll wheel** over the board | Smooth zoom in/out (cursor-anchored; magnitude-scaled) |
| **Middle mouse drag** | Pan the board |
| **Left drag** on the board | Pan (short click without drag still opens the cell menu) |
| **Pinch** (touch) | Zoom in/out (viewport center) |
| **+ / − / fit** controls | Bottom-right overlay on the board canvas |
| **Auto-fit** | When opening or switching boards/sessions, applying a grid resize, or when the center panel resizes |

**Fit** centers the board in the canvas. When the grid is **smaller** than the viewport, the board stays at **native 48px/cell** (no upscale) with even letterboxing on all sides; use **+** or scroll to zoom in. When the grid is **larger**, fit zooms out (with padding) until the whole board is visible, also centered.

Minimum zoom is **dynamic** (fit entire board with padding, capped at **1×** so small boards are not upscaled). Maximum zoom is **2×** native cell size (`SANDBOX_BOARD_MAX_ZOOM` in [`sandboxBoardViewport.ts`](../frontend/src/sandbox/sandboxBoardViewport.ts)). After zooming in, **pan** with middle-mouse or left-drag to inspect a region; use **fit** or zoom out to see the whole board again.

Implementation: [`phaserSandboxAdapter.ts`](../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts), [`sandboxBoardViewport.ts`](../frontend/src/sandbox/sandboxBoardViewport.ts).

### Run Logs

Each tick runs the creature brain, so **Run Logs** update every tick (no movement-only skip).

When fixture or region-trigger workflows fire during a tick, their full node logs appear under **Triggered workflows** in the same Run Logs tab (latest run per source, sticky across ticks). Sub-workflows invoked inside those graphs expose step details on Workflow nodes when present. The tick transcript summarizes brain, fixture, and region-trigger activity counts.

Simulation error banners surface **brain** errors (`last_errors`), **fixture** errors (`last_fixture_errors`), and **region trigger** errors (`last_region_trigger_errors`).

Implementation: [`SandboxView.tsx`](../frontend/src/components/SandboxView.tsx), [`sandboxWorkflowRunMerge.ts`](../frontend/src/sandbox/sandboxWorkflowRunMerge.ts), [`sandboxNestedWorkflowRunMerge.ts`](../frontend/src/sandbox/sandboxNestedWorkflowRunMerge.ts).

## Placeholder visuals

| Item | Default |
|------|---------|
| Grid | 16×16 (8–64 via resize) |
| Creature | Colored rectangles with facing indicator (color chosen at placement; legacy creatures without `color` use index palette) |
| Food | Pink circle |
| Ball | Colored circle (placement color) |
| Wall | Gray square |
| Fixture | Purple inset square with white stroke |
| Definition item | Circle or square from ItemDefinition `shape`; color from instance or definition `default_color` |
| Region | Full-cell colored underlay (~35% opacity), drawn under other items |
| Cell | 48px |

**Draw order (bottom → top):** region → solid (wall or fixture) → pickable (food, ball, definition-backed items) → creature.

Constants: `frontend/src/sandbox/sandboxVisualDefaults.ts`, `backend/app/domain/sandbox/constants.py`.

Favorite placement colors: **My Settings → View Settings → Favorite colors** (`User.settings.sandbox_favorite_colors`, up to 16 hex swatches). The first favorite is the default when placing a new region or creature.

## Region triggers

Each **board instance** region may store a **trigger** (`enabled`, `mode`, `workflow_id`, `inputs`). Configure triggers in the Simulation or Board Builder region inspector (per instance; definition catalog triggers are authoring templates only). The workflow picker lists workflows from **Shared** and **sandbox-enabled** projects, **grouped by project folder** (same eligibility rules as creature brains).

| Mode | When it fires |
|------|----------------|
| `enter` | Creature **moves onto** the region cell |
| `exit` | Creature **leaves** the region cell |
| `while_inside` | **Every tick** while a creature stands on the cell (after all creature brains act) |
| `on_enter_once` | First **enter** per creature per session (`region_trigger_state.enter_once_fired`) |

When a trigger fires, the engine runs its `workflow_id` graph with run override **`sandbox_region`** (`RegionTriggerInput`: tick, mode, region, actor, trigger_inputs, world) and merges `trigger.inputs` into Start overrides. Failures append to `envelope.last_region_trigger_errors`.

### Goal region + pause example

1. Place a region labeled **Goal** on the board; enable trigger, mode **Enter**, pick a workflow.
2. Workflow: **Start** → **Force Simulation Pause** → **Stop** (`output` = dictionary).
3. When a creature moves onto Goal during a tick, the trigger workflow runs; the tick response includes `simulation_effects.force_pause: true` and the SPA stops **Play**.

Implementation: [`region_triggers.py`](../backend/app/domain/sandbox/region_triggers.py), [`region_trigger_runner.py`](../backend/app/domain/sandbox/region_trigger_runner.py).

## Feature flags

| Flag | Purpose |
|------|---------|
| `SANDBOX_ENABLED` | Backend 404 when false |
| `VITE_SANDBOX_ENABLED` | Hide nav when false |
