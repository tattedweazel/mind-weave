# Sandbox Definitions

Operational reference for **Sandbox Definitions**: reusable templates for Items, Terrain, Fixtures, Creatures, and Regions. Definitions are authored in the **Definitions** tab and referenced by `definition_id` on board instances.

See also: [SANDBOX.md](SANDBOX.md) (runtime, `use_fixture`, Remote Control), [BOARDS.md](BOARDS.md) (board JSON, stacked cells), [DOMAIN_MODEL.md](DOMAIN_MODEL.md) (resource vocabulary).

## Concepts

| Concept | Table | Role |
|---------|-------|------|
| **ItemDefinition** | `item_definitions` | Pickable world items (formerly built-in food/ball) |
| **TerrainDefinition** | `terrain_definitions` | Solid, non-traversable terrain (formerly wall) |
| **FixtureDefinition** | `fixture_definitions` | Solid, workflow-powered interactables |
| **CreatureDefinition** | `creature_definitions` | Full placement template (workflow, color, facing, inventory) |
| **RegionDefinition** | `region_definitions` | Region underlay with required trigger config |

Definitions are **flat, user-scoped lists** (like Personas/Structures). Seeded defaults for Food, Ball, and Wall are **fully user-editable**.

## Definitions tab

Sandbox toolbar: **Simulation | Board Builder | Definitions**

- Card gallery with category filters (Items / Terrain / Fixtures / Creatures / Regions)
- Slide-over detail editor for CRUD
- Workflow pickers use the same eligibility rules as creature brains (`sandbox_enabled` projects plus **Shared**), grouped by project folder
- Cell **Place item** pickers list **user** item/terrain definitions only (`!is_system`); seeded Food/Ball/Wall remain reachable via **Built-ins** in the cell action modal
- Saving or deleting a definition refreshes shared Sandbox pickers (cell action modal, region inspector workflow lists) without a page reload
- Item definitions include a **Custom metadata** key/value editor (JSON values). Metadata is **opaque** at runtime — workflows read keys explicitly (e.g. **Dictionary Value by Key**).

## Definition JSON shapes

### ItemDefinition

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Unique per user |
| `label` | yes | Display label on cards and probes |
| `custom_metadata` | no | Free-form JSON object (default `{}`). Opaque key/value bag for workflows (e.g. `{ "energy": 48, "ingredients": ["milk"] }`). **Not** auto-materialized onto board instances — legacy food semantics apply only to built-in Food/Ball and explicit instance `energy`/`color`. |
| `default_color` | no | Visual default (`#RRGGBB`); when set, Board Builder materializes instance `color` (ball-like rendering path) |
| `shape` | no | `circle` \| `square` (render hint; consumed by Phaser for definition-backed instances; defaults to `circle` when unknown) |
| `pickable` | yes | Default `true`. When `false`, the item remains placeable and visible but is excluded from pick-up lists, **Get Cell Items**, and probe `stack_count` (e.g. recipe cards). |

### TerrainDefinition

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Unique per user |
| `label` | yes | Display label |
| `default_color` | no | Visual default |
| `shape` | no | `rect` (default) |

Terrain is always **solid** (blocks movement).

### FixtureDefinition

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Unique per user |
| `label` | yes | Shown in sensory probes and Explorer |
| `workflow_id` | yes | Must resolve to an existing workflow |
| `color` | no | Visual accent (`#RRGGBB`) |

Fixtures are **solid** and allow **non-solid item stacks** on the same cell (see [Stacked cells](#stacked-cells)).

### CreatureDefinition

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Unique per user |
| `label` | yes | Display name default |
| `workflow_id` | yes | Brain workflow |
| `default_color` | yes | `#RRGGBB` |
| `default_facing` | no | `N`/`E`/`S`/`W` (default `N`) |
| `default_inventory` | no | List of inventory entries |

### RegionDefinition

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Unique per user |
| `label` | yes | Region label (may be `""`) |
| `color` | yes | `#RRGGBB` underlay |
| `trigger` | yes | `enabled`, `mode`, `workflow_id`, `inputs` |

Region triggers on **RegionDefinition** rows are authoring templates. Runtime execution uses the **trigger stored on each placed region instance** on the board (configure in the region inspector). See [SANDBOX.md — Region triggers](SANDBOX.md#region-triggers).

## Board instances (`schema_version: 2.5.0`)

Placed objects reference definitions:

```json
{
  "id": "i1",
  "definition_id": "<uuid>",
  "definition_kind": "item",
  "role": "pickable",
  "position": { "x": 5, "y": 5 },
  "color": "#FF6B6B"
}
```

| `definition_kind` | `role` | Notes |
|-------------------|--------|-------|
| `item` | `pickable` | Optional instance overrides: `energy`, `color`. Board Builder materializes from **`default_color` only** (instance `color`, ball-like) when the definition has a color default; otherwise the instance stays a **generic pickable** with no forced `type: food` and no auto `energy`. Explicit instance `energy` or `color` on save still normalizes invalid pairs (e.g. strips instance `color` when instance `energy` is present). **`custom_metadata` is not copied to instances** — probes expose it from the definition lookup. |
| `terrain` | `solid` | Blocks movement |
| `fixture` | `solid` | Blocks movement; allows pickable stack. Visual color resolved at render/probe time from fixture definition `color` (optional instance `color` override). |
| `region` | — | Region layer; optional trigger override |

Creatures reference `creature_definition_id` or inline template fields during migration.

### Chai Recipe pattern

Use `pickable: false` plus opaque metadata (e.g. `{ "ingredients": ["steamed_milk", "chai_powder"] }`). Ingredient items are separate **pickable** definitions placed on the fixture cell. Fixture workflows match pickable ingredients via **Get Cell Items**; recipe metadata is read from the wired `definition_id` or **Dictionary Value by Key** on probe `custom_metadata` — not via pick-up.

## Stacked cells

| Layer | Rule |
|-------|------|
| Region | 0..1 |
| Solid | 0..1 terrain **or** fixture |
| Pickables | 0..N non-solid items (may share cell with fixture) |
| Creature | 0..1 |

**Pick up** (workflow **Pick Up Item** utility) removes the **most recently placed** pickable from the forward cell stack when `item_id` and `pick_all` are omitted. Pick-up succeeds only when the instance resolves to inventoryable **food** (`energy` on instance) or **ball** (`color` on instance) — metadata alone does not inventory.

Remote Control **Pick up** accepts optional `item_id` (one pickable) or `pick_all: true` (every pickable on the forward cell). Omit both only for workflow-emitted `{action: "pick_up_item"}` (LIFO single pick).

In Board Builder and paused Simulation cell edits, **Remove item** clears pickables and terrain only (fixtures remain). When multiple pickables share a cell, the cell action menu opens a picker to remove one item or **Remove all**.

**Explorer (cell inspect):** When you inspect a cell in Simulation or Board Builder, the Explorer lists each occupant in layer order (region, fixture, terrain, pickables). Fixture and definition-backed item instances show their definition **label**, **name**, and role-appropriate fields (workflow for fixtures; shape, color, instance energy, and read-only **custom metadata** for items). Built-in food/ball/wall instances keep legacy section titles (**Food**, **Ball**, **Terrain**).

## Fixture interaction (`use_fixture`)

When a creature (or Remote Control user) emits `{ "action": "use_fixture" }`:

1. Engine resolves the **forward adjacent** fixture instance and `FixtureDefinition`
2. Rejects if no fixture or workflow_id does not resolve
3. Runs the fixture workflow with `FixtureInteractionInput` via `sandbox_fixture` override
4. Fixture utility nodes may mutate world state (list/remove/spawn items). **Get Position** probes the **fixture cell** (including `stack_count` and pickable `items` with resolved `label` and `custom_metadata`); **Get Facing**, **Get Nearby**, and **Get Inventory** resolve context from the injected `sandbox_fixture` override using the **actor** position/facing without requiring a Start `sandbox_tick` slot.
5. No Stop/DecisionIntent parse — side effects are the outcome

When a fixture workflow runs during simulation, its node logs appear in the Simulation **Run Logs** tab under **Triggered workflows** (see [SANDBOX.md — Run Logs](SANDBOX.md#run-logs)). Fixture failures are recorded in `envelope.last_fixture_errors`, separate from creature brain errors.

See [WORKFLOW_TOOL_INVENTORY.md](WORKFLOW_TOOL_INVENTORY.md) for handle details. In the Workflow Editor, **Get Cell Items**, **Remove Item**, and **Spawn Item** appear in **Sandbox Utilities** (same palette section as creature-brain navigation steps).

### Consume item and spawn replacement (fixture workflow recipe)

Common pattern: when the fixture cell holds a specific pickable (e.g. a **Key**), remove it and spawn a different item (e.g. a reward) at the **same cell** on `use_fixture`.

Fixture workflows receive `FixtureInteractionInput` via the injected `sandbox_fixture` run override. **Get Cell Items** and **Get Position** read pickables from the **initial** cell snapshot for that interaction (safe for find → remove → spawn in one run without re-probing).

#### Recipe A — via **Get Position**

```
Get Position
  → Dictionary Value by Key "items"
  → For Loop
      item → Dictionary Value by Key "label" (or "definition_id")
           → Is? vs String primitive (expected value)
           → [first-match guard — see below]
           → true branch:
                Dictionary Value by Key "id" → Remove Item
                Spawn Item (definition_id in Explorer or wired, target "self")
```

#### Recipe B — via **Get Cell Items** (shorter)

Same loop body, but the list comes directly from **Get Cell Items** (no Start / `sandbox_tick` required).

#### Matching: label vs definition_id

| Match on | Wire | Notes |
|----------|------|-------|
| Display **label** | Loop item → `label` → **Is?** vs String primitive (e.g. `"Key"`) | Uses resolved display label from the cell probe |
| **definition_id** | Loop item → `definition_id` → **Is?** vs String primitive (ItemDefinition UUID) | Prefer for definition-backed pickables where probe `kind` is always `"item"` |
| **Metadata key** | Loop item → `custom_metadata` → **Dictionary Value by Key** | Read opaque definition metadata exposed on the probe summary |

Copy UUIDs from the **Definitions** tab, or pick an item definition in the **Spawn Item** Explorer panel (dropdown + manual override).

#### First match only; skip when none found

- If **no** item matches, the loop completes with **no** remove and **no** spawn.
- **For Loop** evaluates every list entry. To avoid removing/spawning for **each** matching item when multiple share the same label or definition, add a guard:
  1. Dictionary primitive `{ found: false }` before the loop
  2. Loop body: **Is? (match) AND Is? (found == false)** → on true: **Remove Item**, **Spawn Item**, then **Dictionary Set Value by Key** `found = true`
  3. Later iterations skip because `found` is true

#### Spawn location

**Spawn Item** defaults `target` to **`self`** (same cell as the fixture). Optional `target` offset strings (`"dx dy"`) spawn on a neighbor cell instead.

See [SANDBOX.md — Cell probe shape](SANDBOX.md#cell-probe-shape) for the `items[]` summary fields (`id`, `label`, `definition_id`, `custom_metadata`).

## HTTP API

Base: `/api/v1/sandbox-definitions`

| Resource | Paths |
|----------|-------|
| Items | `GET/POST /items`, `GET/PUT/DELETE /items/{id}` |
| Terrain | `GET/POST /terrain`, `GET/PUT/DELETE /terrain/{id}` |
| Fixtures | `GET/POST /fixtures`, `GET/PUT/DELETE /fixtures/{id}` |
| Creatures | `GET/POST /creatures`, `GET/PUT/DELETE /creatures/{id}` |
| Regions | `GET/POST /regions`, `GET/PUT/DELETE /regions/{id}` |

## Migration from 2.4.0

One-time Alembic migration maps legacy inline types:

| Legacy `type` | Definition |
|---------------|------------|
| `food` | Seeded Food ItemDefinition |
| `ball` | Seeded Ball ItemDefinition |
| `wall` | Seeded Wall TerrainDefinition |
| `region` | Inline → RegionDefinition or instance with `definition_kind: region` |

Existing boards and live sessions are rewritten to `definition_id` references.

Former `default_energy` values on item definitions were copied into `custom_metadata.energy` as preserved data for workflows; the column was dropped. That key does **not** auto-materialize food semantics on placement or pickup.

## Seeded defaults

| Slug | Kind |
|------|------|
| `builtin-food` | ItemDefinition |
| `builtin-ball` | ItemDefinition |
| `builtin-wall` | TerrainDefinition |

Seeds are `is_system=true` but **user-editable and deletable**.
