# Sandbox (workflow-driven simulation)

Operational reference for the **Sandbox** feature: a server-owned tick engine, document-backed sessions, and a replaceable **runtime adapter** on the SPA (default: Phaser for rendering and pointer input only).

Product background and iteration notes live in the repo-root drafts `[sandbox_environment_prd.md](../sandbox_environment_prd.md)`, `[starter_behavior_workflow.md](../starter_behavior_workflow.md)`, and `[json_structures.json](../json_structures.json)`. **This file is the implementer SSOT** for behavior, APIs, and placeholders.

## Architecture


| Layer               | Owns                                                                                                                                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Domain**          | `SandboxState`, validation (`app/domain/schemas/sandbox.py`), tick rules (`app/domain/sandbox/engine.py`)                                                                                      |
| **Workflows**       | Decisions as `DecisionIntent` — built-in starter uses **composable** `utility` steps (`sandbox_*`) plus Stop; legacy `sandbox_behavior` primitive remains available                            |
| **Persistence**     | `Document.body` JSON envelope (`SandboxDocumentEnvelope`)                                                                                                                                      |
| **HTTP**            | `app/api/v1/sandbox.py` — thin routes → `SandboxService`                                                                                                                                       |
| **Runtime adapter** | Phaser only under `frontend/src/sandbox/runtime/phaserSandboxAdapter.ts` + `sandboxVisualDefaults.ts`                                                                                          |
| **SPA shell**       | `[frontend/src/components/SandboxView.tsx](../frontend/src/components/SandboxView.tsx)` — three-column layout aligned with the Workflow Editor (resizable left/right, center toolbar + board). |


**Run Logs (Explorer → Run Logs):** The right-hand **Run Logs** tab shows the last brain run’s `node_results` using the same [`WorkflowRunLogsNodeResultsList`](../frontend/src/components/workflow-editor/WorkflowRunLogsNodeResultsList.tsx) component as the Workflow Editor. Expand a step to see **Output** (and the error message when `status` is `error`) and, when present, **Inputs** from `details.resolved_inputs` (merged per [`lastRunInputsPayload`](../frontend/src/components/workflow-editor/lastRunInputsPayload.ts)). On failed steps, **Inputs** is listed **above** **Output** when `resolved_inputs` exists so you see wiring context first. The executor attaches **`resolved_inputs`** for sandbox steps on most structured failures so you can compare what was wired into the node against the error. Contract and redaction rules: [`docs/WORKFLOW_SKILLS.md`](WORKFLOW_SKILLS.md) (`details.resolved_inputs`); values persisted at rest still pass through [`run_log_redaction.py`](../backend/app/core/run_log_redaction.py).

Canonical JSON Schema (shared tooling): `[shared/sandbox_canonical.schema.json](../shared/sandbox_canonical.schema.json)`.

**Phaser is not the simulation engine.** Phaser must not own authoritative state or tick timing. References: [What is Phaser](https://docs.phaser.io/phaser/getting-started/what-is-phaser), [Phaser + React](https://phaser.io/news/2024/03/phaser-3-and-react-typescript-template), [Scenes](https://docs.phaser.io/phaser/concepts/scenes), [Game objects](https://docs.phaser.io/phaser/concepts/gameobjects), [Input](https://docs.phaser.io/phaser/concepts/input).

## Composable sandbox brain (workflows)

Simulation logic should stay **deterministic** (no LLM on the default path). Authors compose **utility** steps with `utility_type` prefix `sandbox_*` (see `[shared/workflow_graph_step_kinds.json](../shared/workflow_graph_step_kinds.json)`) to read `[SandboxTickInput](../json_structures.json)` and emit a validated `[DecisionIntent](../json_structures.json)` into **Stop**, using existing controls (conditionals, int compares, dictionary helpers) for branching.

**Example subgraph:** wire **Start**’s `sandbox_tick` dictionary into `sandbox_tick_items` (optional **Item type** on the node to filter to `food`; default **All** lists every item) → (optional) `sandbox_filter_items_by_type` if you need a separate filter step → (optional) list/conditional steps → `sandbox_decision_intent` → **Stop** (dictionary output).

### Multiple Stop nodes

You may place **more than one** `kind: "stop"` node in a workflow. The executor runs the graph in topological order; each Stop resolves when reached. For **sandbox** ticks, `[SandboxService.run_tick](../backend/app/domain/services/sandbox_service.py)` still needs **one** `DecisionIntent`: `[decision_intent_from_workflow_result](../backend/app/domain/sandbox/workflow_bridge.py)` chooses **one** successful Stop using **`data.stop_priority`** (integer, default `0`), then **`step_number`** from the run (higher = later in the schedule), then **`node_id`** lexicographically—see `[select_best_stop_node_result](../backend/app/domain/sandbox/stop_selection.py)`. Set **`stop_priority`** on each Stop (editor: Stop inspector → **Multi-Stop / sandbox**) so the winning branch is explicit when several Stops could succeed.

**Workflow ref typing (editor):** nested **Workflow** nodes infer sub-workflow outputs from a **graph-only** rule: highest **`stop_priority`**, then lexicographically smallest **`node_id`**. That matches the runtime tie-break when **`step_number`** ties; if two Stops share the same priority and both succeed with **different** step numbers, runtime prefers the **later**-scheduled Stop—avoid relying on equal priorities across mutually exclusive branches without setting priorities.

### Authoring: bundled brain vs custom policy

The simulation does **not** care how you build the graph. It only requires that **Stop** receives a **dictionary** matching `[DecisionIntent](../json_structures.json)` (`action`, optional `target_item_id`, `target_cell`, `reason`). `[SandboxService](../backend/app/domain/services/sandbox_service.py)` passes the current tick as `input_overrides["sandbox_tick"]`; **Start** should declare a `sandbox_tick` input (type dictionary) so the editor can wire it like the starter workflow.


| Approach                                                  | Role                                                                                                                                                                                                          | When to use                                                                                                                                                                                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `**sandbox_starter_decision`** (utility)                  | Runs the **built-in** deterministic policy from `[starter_behavior.py](../backend/app/domain/sandbox/starter_behavior.py)` in **one** step—the same behavior the legacy `**sandbox_behavior`** primitive had. | You want the default pet brain **without** editing graph logic. This is **not** a customization hook; it replaces the old opaque node.                                                                                                                             |
| `**sandbox_decision_intent`** (utility)                   | **Builds and validates** a `DecisionIntent` from wired or inline inputs (`action`, `target_item_id`, `target_cell`, `reason`).                                                                                | **This** is the composable “output” step: combine it with **dictionary** / **list** / **int** primitives, **dictionary value by key**, **conditionals**, `**sandbox_tick_items`**, `**sandbox_filter_items_by_type**`, etc., to decide **what** the creature does. |
| `**sandbox_tick_items`** | **Get items** from the tick: `**world.items**` as a list of item dicts. Optional `data.item_type`: `all` (default) or `food` to filter.                                                                                                                                         | Listing all items on the board or narrowing to one type (e.g. food) without a separate filter step.                                                                                                                                                                                          |
| `**sandbox_filter_items_by_type`** | Filter an **already-wired** list of item dicts by `type` (V1: `food`).                                                                                                                                         | When items come from upstream steps (not only from the tick utility).                                                                                                                                                                                          |
| `**sandbox_world_grid`**                                   | Dictionary `{ width, height }` from the tick’s `world.grid`.                                                                                                                                                  | Board metadata for composing “random cell” / empty-cell logic without a dedicated random node.                                                                                                                                                                       |
| `**sandbox_available_cells`**                               | **List** of `{ x, y }` dicts: every in-bounds cell not occupied by the pet or any item (row-major order).                                                                                                      | Enumerate empty cells for “pick a random free tile” or path-style logic without subtracting occupied cells by hand.                                                                                                                                                    |
| `**sandbox_nearest_item_by_type`**                         | **Dictionary**: one serialized item matching minimum Manhattan distance from the pet for `item_type` (`"food"` or `"all"` for every item), or **`{}`** when none match; ties break by `world.items` order. Inline `item_type` is configurable in the editor (same **All** / **Food** idea as `sandbox_tick_items`). Same geometry as **`sandbox_closest_item`**. | Nearest food (`item_type: "food"`) or nearest item of any type (`"all"`). Differs from `**sandbox_filter_items_by_type**` (full list) and from `**sandbox_first_nearby_food**` (first adjacent in order, not min distance).                                     |
| `**sandbox_closest_item`** (utility; palette **Get Closest Item**) | **Dictionary**: same as `**sandbox_nearest_item_by_type**`—one serialized item object, or **`{}`** when no matching item exists. | Palette alias for the same behavior; use whichever label you prefer. |
| `**sandbox_decision_move_to`**                             | Same dictionary shape as `**sandbox_decision_intent**` with `action: "move_to"`—convenience for exactly one of `target_item_id` or `target_cell`.                                                          | Fewer mis-wires than setting `action` manually on `sandbox_decision_intent`.                                                                                                                                                                                        |
| `**sandbox_tick_pet`**                                      | Validated `pet` subtree as a dictionary (`PetState` JSON).                                                                                                                                                    | Prefer over ad-hoc `dictionary value by key` on the tick when you need reliable pet fields.                                                                                                                                                                         |


**Why the default workflow still looks “opaque”:** the seeded **Starter Sandbox Behavior** graph is intentionally **Start → `sandbox_starter_decision` → Stop** so behavior stays identical to the original product. That graph **does not** demonstrate branching; copying it only duplicates the bundled policy.

### Starter graph export fixture (`sandbox-behavior-imported.json`)

The repo-root file [`sandbox-behavior-imported.json`](../sandbox-behavior-imported.json) holds the same graph as the canonical seed in [`starter_workflow_seed.py`](../backend/app/domain/sandbox/starter_workflow_seed.py), wrapped in workflow-export shape `{ "definition": { "graph": … } }`. [`test_starter_workflow_seed.py`](../backend/tests/test_starter_workflow_seed.py) asserts the built-in graph stays aligned with that file so exports and the seeded row do not drift.

When you change the minified graph in code, regenerate the JSON from the **`backend/`** directory using the heredoc in the module docstring at the top of [`starter_workflow_seed.py`](../backend/app/domain/sandbox/starter_workflow_seed.py), then run `pytest tests/test_starter_workflow_seed.py` and commit both the Python and JSON changes.

**Smallest truly custom graph:** **Start** (with `sandbox_tick`) → `**sandbox_decision_intent`** → **Stop** (dictionary), with `action` set inline (e.g. `wander`) or wired from upstream. That proves your workflow drives the pet; you can then add branches, tick inspection, and filters.

**Workflow editor:** Sandbox-specific steps use the same persisted `kind: "utility"` as other utilities; in the editor they are listed under a separate **Sandbox Utilities** collapsible section (between **Utilities** and **Controls**), so the general Utilities list stays focused on document/string/list math.

### Message utility (`message`)

The **Message** step is a general utility (listed under **Utilities**, not under Sandbox Utilities). It has one string input handle **`message`**, incoming **`trigger`** (same control-flow pattern as other signal-gated steps: previous **`signal_out`** → **`trigger`**), and only **`signal_out`** for data flow—**no** separate data output handle. The executor resolves the string, stores it on the run as **`details.user_message`**, and emits an empty **`StringNodeOutput`** so the graph shape stays consistent. **Sandbox:** after each successful tick, the SPA reads `user_message` from `last_workflow_run.node_results` and shows a short auto-dismissing toast over the center board (full text remains in Run Logs).

### Decision action primitive (`decision_action`)

The **Decision action** step is a **primitive** (`kind: "primitive"`, `primitive_type: "decision_action"`) listed under **Sandbox Utilities** for discoverability. It has no free-text configuration—only a dropdown of canonical **`DecisionAction`** values (`move_to`, `wander`, `eat_nearby`, `sleep`, `idle`). It emits a normal **`StringNodeOutput`** whose text is the selected value, so you can wire **`output` → `action`** on **`sandbox_decision_intent`** without typos or hand-edited JSON.

### Sandbox tick primitive (`sandbox_tick`)

The **Sandbox tick** step is a **primitive** (`primitive_type: "sandbox_tick"`) in **Sandbox Utilities**. It outputs the full current **`SandboxTickInput`** as a **dictionary** (`DictionaryNodeOutput`), so you can fan the tick out to several utilities without chaining everything from **Start**. On each Sandbox tick, the server injects `input_overrides["sandbox_tick"]`; the primitive reads that first, or falls back to a wired **Start** `sandbox_tick` / tick-shaped dictionary on the optional **override** input. Editor test runs should wire **Start** or supply tick data via run overrides.

### Composable utilities (inventory)

Mid-level `sandbox_*` utilities wrap pure helpers in `[backend/app/domain/sandbox/query.py](../backend/app/domain/sandbox/query.py)` so authors can approximate `[starter_behavior_decision](../backend/app/domain/sandbox/starter_behavior.py)` without `sandbox_starter_decision` or long dictionary plumbing.


| `utility_type`                              | Role                                                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `sandbox_tick_items`                        | `world.items` as a list of item dicts; optional `data.item_type` (`all` or `food`) to filter inline |
| `sandbox_world_grid`                        | `{ width, height }` board size from the tick                                                     |
| `sandbox_available_cells`                   | List of `{ x, y }` for cells inside `world.grid` not occupied by pet or items (row-major)         |
| `sandbox_tick_pet`                          | Validated `pet` dictionary (stats, position, intent)                                           |
| `sandbox_filter_items_by_type`              | Filter item dicts by `type` (V1: `food`)                                                       |
| `sandbox_nearest_item_by_type`              | Dictionary: one nearest item or `{}`; `item_type` `food` or `all` (inline or wired)             |
| `sandbox_closest_item`                      | Dictionary: same as `sandbox_nearest_item_by_type` (palette **Get Closest Item**)               |
| `sandbox_decision_move_to`                    | `DecisionIntent` with `action: "move_to"` (one target)                                         |
| `sandbox_pet_hunger` / `sandbox_pet_energy` | `pet.hunger` / `pet.energy` as **int** from the tick                                           |
| `sandbox_pet_cell`                          | `pet.position` as `{ x, y }` **dictionary** (same shape as grid cells) for **is nearby8** / distance wiring |
| `sandbox_is_nearby8`                        | **boolean**: two wired cell dicts (`x`, `y`) are 8-neighbors (excludes identity)               |
| `sandbox_first_nearby_food`                 | **list** (0–1 items): first food in `world.items` order adjacent to the pet                    |
| `sandbox_first_food_world_order`            | **list** (0–1 items): first food in `world.items` iteration order (`foods[0]` in starter seek) |
| `sandbox_decision_intent`                   | Build validated `DecisionIntent` for **Stop** (dictionary output)                              |
| `sandbox_starter_decision`                  | One-step bundled starter policy                                                                |


**Thresholds (starter-aligned):** `[STARTER_HUNGER_SEEK_THRESHOLD](../backend/app/domain/sandbox/constants.py)` (60) and `[STARTER_ENERGY_SLEEP_THRESHOLD](../backend/app/domain/sandbox/constants.py)` (30) match the built-in starter policy. The starter **seeks food when hunger is above** the seek threshold (not below). Use **Int** primitives or inline values with **Gt** / **Lt** (or **Basic Conditional**) on `sandbox_pet_hunger` / `sandbox_pet_energy`.

**Reference policy (priority ladder):** Branch with **Basic Conditional** + list/int controls: if `**sandbox_first_nearby_food`** is non-empty (e.g. **Len from List** → compare to 0), wire `**sandbox_decision_intent`** with `eat_nearby` and `target_item_id` from **list item by index**; else if hunger ≥ seek threshold, use `**sandbox_first_food_world_order`** for seek; else if energy ≤ sleep threshold, emit `sleep`; else `wander`. Only `**sandbox_decision_intent**` should feed **Stop** as the dictionary output step.

**Composable seek / move / eat (example):** `**sandbox_closest_item**` or `**sandbox_nearest_item_by_type**` with `item_type: "food"` → `**sandbox_decision_move_to**` with `target_item_id` from **dictionary value by key** (`id`) on the item dict. Next decision tick, `**sandbox_decision_intent**` with `eat_nearby` when adjacent. For wandering to a random empty cell, wire `**sandbox_available_cells**` (or `**sandbox_world_grid**` plus manual subtraction) and pick from the list with primitives—there is no dedicated “random empty cell” node.

**Workflow defaults (optional):** Persisted workflow JSON may include top-level `**sandbox_defaults**`: `{ "grid_width": 12, "grid_height": 10 }` (ignored by the executor). New sandbox sessions created with that workflow apply the grid after the default envelope (clamped to min 8 × max 64). Same pattern as other extra graph keys—see `WorkflowDefinitionService` round-trip.

**Structured pet / items (incremental):** Prefer **`sandbox_tick_pet`** (validated `PetState` JSON), **`sandbox_pet_cell`** when you only need **`pet.position`** as a cell dict for **`sandbox_is_nearby8`**, item lists from **`sandbox_tick_items`**, and a single nearest item dict from **`sandbox_nearest_item_by_type`** or **`sandbox_closest_item`**, over hand-slicing the tick dictionary. Canonical field shapes live in [`app/domain/schemas/sandbox.py`](../backend/app/domain/schemas/sandbox.py) and [`json_structures.json`](../json_structures.json). Wire **Start → `sandbox_tick`** into these utilities, then into **`sandbox_decision_intent`** / **`sandbox_decision_move_to`** for **Stop**. Future **`primitive_type`** values for sandbox objects would require manifest and editor work; extract utilities keep a lower blast radius.

### Decision ticks vs intent continuation

When `[SandboxService.run_tick](../backend/app/domain/services/sandbox_service.py)` runs, if `pet.intent.status == "in_progress"`, the service **does not execute the workflow graph**; it only advances the current intent via `[SandboxEngine.continue_intent_step](../backend/app/domain/sandbox/engine.py)` (movement, eating, etc.). The **composable brain** therefore runs on **decision ticks**—when the pet is **not** in the middle of a multi-step `move_to` / `eat_nearby` / `sleep` / `wander` intent. Do not assume the graph re-plans on every physics tick while an intent is executing.

**`move_to` completion:** The pet cannot walk onto a cell occupied by an item. If the goal cell is **empty**, `move_to` completes when the pet **reaches** that cell. If the goal cell **has an item** (e.g. food), `move_to` completes when the pet is **8-adjacent** to that cell (same adjacency rule as `sandbox_is_nearby8`), so the next decision tick can wire `eat_nearby` or another action. Use `target_item_id` or `target_cell` per validation rules; both resolve to the same completion geometry once the goal cell is known.

**`eat_nearby` resolution:** During intent continuation, if `target_item_id` is missing, does not refer to adjacent food, or points at food that is not 8-adjacent, the engine **falls back** to the **first food in `world.items` order** that **is** adjacent to the pet (same ordering as **`sandbox_first_nearby_food`**). If there is no adjacent food, the intent retries up to **`MAX_RETRY`** then clears. Intent steps use a bounded retry counter so failed ticks cannot leave the pet stuck in `in_progress` indefinitely.

## Changing the brain workflow during a session

The SPA **Workflows** list selects which saved definition drives the simulation. You can **change that selection while ticks are running** (including switching between the built-in starter and a custom graph). Each `POST .../tick` may include optional **`workflow_id`**; when present, the server loads that definition for the tick and **persists** it on the session envelope as **`workflow_id`**—so the choice survives **reload** and is not a one-tick preview.

**Why this is useful:** compare multiple policies in one session without creating separate documents (side-by-side behavior as you step or play).

**Intent continuation:** While `pet.intent.status == "in_progress"`, the service **does not** run the workflow graph on that tick (see [Decision ticks vs intent continuation](#decision-ticks-vs-intent-continuation)). A newly selected brain therefore takes effect on the **next decision tick**—not necessarily the very next HTTP tick if the pet is still finishing a move or other intent.

**Incompatible graphs:** A workflow whose **Stop** does not yield a valid [`DecisionIntent`](json_structures.json) dictionary (wrong type, missing wiring, or **Start** without a **`sandbox_tick`** slot so utilities never see tick data) surfaces as **`last_error`** on the envelope and in Run Logs; the simulation keeps running, and selecting a compatible workflow clears the error on the next successful parse. For graphs with **multiple Stop** nodes, set **`stop_priority`** on each Stop so the winning branch stays explicit when you swap between definitions—see [Multiple Stop nodes](#multiple-stop-nodes).

## API (authenticated)

Base path: `/api/v1/sandbox/`


| Method | Path                           | Purpose                                                                                                                                                                                                                                                                                                           |
| ------ | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST` | `/sessions`                    | Create session document + initial envelope (optional `workflow_id`; defaults to starter)                                                                                                                                                                                                                          |
| `GET`  | `/sessions/{document_id}`      | Load envelope                                                                                                                                                                                                                                                                                                     |
| `POST` | `/sessions/{document_id}/tick` | Run one tick (`interactions`, `state_version`, optional `workflow_id`; 409 on version mismatch). Response includes `envelope` and `last_workflow_run` (null when this tick only continued an in-progress intent without executing the graph). Sending `workflow_id` updates the persisted `envelope.workflow_id`. |
| `POST` | `/sessions/{document_id}/grid` | Resize the simulation grid (`width`, `height`, `state_version`). **Requires playback paused** (`envelope.playback.paused`); 422 if playing, 409 on version mismatch. Dimensions must be **8–64** (see `SANDBOX_GRID_MIN_SIZE` / `SANDBOX_GRID_MAX_SIZE`). Pet position is clamped; items outside the new bounds are removed; `pet.intent` is cleared. |
| `GET`  | `/starter-workflow-id`         | UUID of the built-in starter workflow                                                                                                                                                                                                                                                                             |


When `SANDBOX_ENABLED` is `False` on the server, these routes return **404**.

## Feature flags


| Where                           | Purpose                                                     |
| ------------------------------- | ----------------------------------------------------------- |
| Backend `SANDBOX_ENABLED`       | Disable sandbox routes in production without removing code  |
| Frontend `VITE_SANDBOX_ENABLED` | If set to `false`, hides **Sandbox** nav (default: enabled) |


## Placeholder catalog (V1 visuals)

All values are **adapter-local**; changing art does not change `SandboxState` or API contracts.


| Item                | Default                                                                             | Notes                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Grid size           | Default 16×16; **8–64** via API + Explorer when paused                                | `DEFAULT_GRID_*`, `SANDBOX_GRID_MIN_SIZE` / `SANDBOX_GRID_MAX_SIZE` in `constants.py`; `POST .../grid` |
| Cell size           | 48 px                                                                               | `CELL_PX` in `frontend/src/sandbox/sandboxVisualDefaults.ts`                              |
| Board padding       | 8 px                                                                                | `BOARD_PADDING`                                                                           |
| Colors              | `#0f172a` board, `#334155` grid, `#38bdf8` pet (rectangle), `#f472b6` food (circle) | `sandboxVisualDefaults.ts`                                                                |
| Initial pet stats   | hunger 45, energy 70, mood 45                                                       | `constants.py`                                                                            |
| Tick rate UI        | 1000 ms                                                                             | `DEFAULT_TICK_RATE_MS`                                                                    |
| Play / Pause / Step | Client timers calling `POST .../tick`                                               | Server runs one tick per request                                                          |


## Cell actions (UI wizard + interactions)

Clicking a grid cell opens a **stepped modal** (not a raw tick). The shell **pauses** auto-tick while the modal is open and **restores** the previous play/pause state when the user finishes or dismisses.

1. If the cell is **occupied** (the pet is on that cell, or any world item is), **Inspect** appears first. Choosing it closes the modal and focuses the right-hand **Explorer** tab with live details for that cell (pet stats / intent and each item’s id, type, position, and energy when present)—similar to selecting a node in the Workflow Editor. Opening the modal for a **different** cell clears that Explorer focus.
2. Choose **Place item** or **Remove item** (more root actions can be added later).
3. For **Place item**, choose **Item type** (today only **Food**).
4. The SPA sends one `POST .../tick` with the chosen interaction payload (Inspect does **not** send a tick).


| Interaction `type` | Payload                     | Engine behavior (V1)                                                                                                                               |
| ------------------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `place_item`       | `cell`, `item_type`: `food` | Appends food at `cell` if the cell is empty and the pet is not on it (same rules as legacy add half of `cell_click`). |
| `remove_item`      | `cell`                      | Removes all items at `cell`; clears pet intent if it targeted a removed item.                                                                      |
| `cell_click`       | `cell`                      | **Legacy:** toggles food on that cell (still accepted; the default UI does not send it).                                                           |


Canonical schema: `SandboxInteractionEvent` in `[shared/sandbox_canonical.schema.json](../shared/sandbox_canonical.schema.json)`.

**Future:** replace shapes with sprites/tilemaps inside the Phaser adapter only.

## V1 limitations

- Single pet; multiple food items allowed (one item per cell). Default starter brain uses the `sandbox_starter_decision` utility (same policy as the legacy `sandbox_behavior` primitive).
- No LLM decision path in the starter workflow (extend with same `DecisionIntent` contract later).
- `docs/Audits/TEST_AUDIT.md` maps tests; this repo does not mandate a global line-coverage percentage.

### Phase 3 (deferred): multiple item types

Extending `ItemType` beyond `food`, engine placement rules, and parameterized `sandbox_*` filter utilities is **out of scope for V1**; keep composable graphs food-focused until product adds new types and schema updates.

## Removing or disabling Sandbox

1. Set `SANDBOX_ENABLED=false` and `VITE_SANDBOX_ENABLED=false`.
2. To remove code: delete `backend/app/api/v1/sandbox.py`, `backend/app/domain/sandbox/`, `backend/app/domain/services/sandbox_service.py`, register block in `app/main.py`, `frontend/src/sandbox/`, `frontend/src/components/SandboxView.tsx`, App shell nav + lazy import; remove `phaser` from `frontend/package.json`.
3. **Do not** revert Alembic migrations that added `workflow_definitions.is_system` / seeded rows without a coordinated downgrade strategy.

## Troubleshooting

- **Run Logs: error visible but no Inputs section:** The UI only renders **Inputs** when `node_results[].details.resolved_inputs` is non-empty (see [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md)). The executor should populate this for sandbox utilities and for structured utility failures (e.g. **Dictionary value by key**) when inputs were resolved; if a step fails with an internal exception before resolution, **Inputs** may be absent. **Persisted** run logs may redact prompt-like keys inside `details` ([`run_log_redaction.py`](../backend/app/core/run_log_redaction.py)); the in-memory `last_workflow_run` from `POST .../tick` is intended for debugging parity with workflow **Run**.
- **Sandbox is nearby8 — `cell_b: invalid JSON` with a valid dictionary upstream:** The executor matches inputs by `edges[].target_handle` (`cell_a` / `cell_b`). If the saved graph has `target_handle: null` on the second wire, the backend now assigns null-handle edges to the next unfilled structured slot in order (see [`workflow_executor/inputs.py`](../backend/app/domain/workflow_executor/inputs.py) `_resolve_inputs_by_target_handle`). Re-saving the workflow from the editor with explicit handles is still best; the canvas may display a default handle for null edges without persisting it.
- **UI shows `workflow not found` on Sandbox load:** `SandboxService.create_session` could not load the starter workflow. Run `**alembic upgrade head`** from the `backend/` directory. Revision `**c0d1e2f3a4b5**` fixes an SQLite-only bug where the seeded row used dashed UUID text while ORM queries use 32 hex characters. Revision `**e1f2a3b4c5d6**` updates the built-in starter graph JSON to the export-shaped canonical (`nodes` + `edges` only). Revision `**f1a2b3c4d5e6**` replaces the starter’s two implicit edges with four explicit edges (`signal_out`→`trigger` and data handles for `sandbox_tick` / `output`). Revision `**g1h2i3j4k5l6**` switches the starter brain node to the `sandbox_starter_decision` utility. Then restart the API. If it still fails, confirm a `workflow_definitions` row exists with `builtin_slug = starter_sandbox_behavior`.
- **409 on tick:** `state_version` out of sync; refetch `GET /sessions/{id}`.
- **Workflow errors in `last_error`:** Stop output was not a valid `DecisionIntent` dictionary; check assigned workflow graph.
- **Tests:** Pytest uses an in-memory DB (migrations are not applied to it); `tests/conftest.py` calls `ensure_starter_sandbox_workflow` alongside other built-in seeds. On startup, that helper **re-syncs** the starter row’s `graph` when the stored JSON is not equivalent to the canonical export (including legacy top-level `schema_version`, or SQLite number quirks such as `0.0` vs `0`), so tests and local dev DBs converge without a manual row edit.
- **Starter graph still looks unlike a fresh export after upgrading:** Restart the API once so `ensure_starter_sandbox_workflow` runs; then reload the workflow in the editor. The built-in definition name stays **Starter Sandbox Behavior** (the export filename may say “imported”).

