# Authoring Mind Weave workflow export JSON (no codebase required)

This document is written for a language model that has **no prior knowledge of Mind Weave** and **no access to any source repository**. Follow it **literally**. When your job is to turn a user’s natural-language request into a workflow, your **only** required deliverable is **one JSON document** in the format below (unless the user explicitly asks for explanation text in addition).

**Editor bundle exports are out of scope here:** The Workflow Editor’s **Export** button produces **`mind_weave_workflow_bundle_export`** (nested workflows plus referenced resources). LLM hosts should continue to emit **single-workflow** **`mind_weave_workflow_export`** only, as specified below—not the bundle envelope.

### Required root JSON shape (read second)

**Persona / host one-liner:** The model’s entire JSON reply must be **one object** whose **top-level** keys are **`kind`**, **`schema_version`**, **`exported_at`**, and **`definition`** only. Do **not** put **`name`**, **`description`**, or **`graph`** at the root (those live **inside** `definition`).

**Do not** use **`"nodes": []`**, **`"edges": []`**, or **only a Start node** in examples you write—the graph must always include **both** Start and Stop (see **Hard rules**) and **non-empty** `edges` for normal workflows.

Minimal skeleton (placeholders only—**replace** `nodes` / `edges` with real arrays, never leave them empty):

```json
{
  "kind": "mind_weave_workflow_export",
  "schema_version": 1,
  "exported_at": "2026-03-22T12:00:00.000Z",
  "definition": {
    "name": "…",
    "description": "…",
    "graph": {
      "schema_version": 1,
      "nodes": [ "… at least one start and one stop node object …" ],
      "edges": [ "… at least one edge object …" ]
    }
  }
}
```

**Structured output (JSON Schema) — read if your host enforces a schema:** Prose in this document **does not** override a **permissive** JSON Schema. If your **Structure** allows `data` to be any object, **`edges` without `minItems`**, or **`nodes` without requiring a Stop**, models will often emit **Start-only** graphs or **`edges: []`** because those still validate. **Replace** that schema with the reference file below (or add `minItems` on `edges`, **`contains`** a `kind: "stop"` node, and Start/Stop `data` constraints). Until the schema is tightened, expect **stub** outputs regardless of these instructions.

**Reference JSON Schema (strongly recommended for structured-output hosts):** [`shared/mind_weave_workflow_export_llm_response.schema.json`](shared/mind_weave_workflow_export_llm_response.schema.json) requires the full export envelope, **at least one Start and one Stop** in `nodes`, **`edges.minItems` ≥ 1**, and constrains Start/Stop `data`. Paste it into your **Structure** JSON field (or equivalent) when the host supports JSON Schema `response_format`.

**Output obligation (read third):** For almost every user request, your JSON **must** include: (1) **Start** `data` with a **non-empty** `required_inputs` array; (2) **Stop** `data` with a **non-empty** `required_outputs` array whose `type` matches the user’s desired result; (3) a **non-empty** `edges` array with at least **trigger** wiring from Start toward Stop and **data** wiring into Stop. **Never** respond with only Start + Stop and `"data": {}` on both, and **never** emit `"edges": []` when the user asked for a workflow that processes inputs. If you are unsure what to build, still satisfy (1)–(3) using the **Smallest acceptable graph** section below, then add steps.

**Collation:** These materials are combined into a single prompt: **Instructions** (this section) first, then **Tool Inventory** (referenced below). Nothing here points at other folders or repositories.

## Companion section (referenced below)

This section covers **how** to encode the graph in JSON. The **Tool Inventory** (below) covers **what** steps exist:

| Section | Responsibility |
|---------|-----------------|
| **Tool Inventory** (below) | **What** steps exist: `primitive_type` / `utility_type` / `control_type` / `skill_type`, typical handles, suggested usage, full **Dictionary merge** semantics. |
| **Instructions** (this section) | **How** to encode the graph in JSON: envelope, nodes/edges, triggers vs data, validation checklist, minimal example. |

Use the **Tool Inventory** (below) as the **catalog of allowed steps**; use the **manifest JSON** at the end of that section as the allowed step list when generating workflows. Any new `primitive_type` or `utility_type` you emit must appear in that inventory and manifest (regenerate or extend them in-repo when adding steps—do not invent discriminators).

---

## What you are building (one sentence)

A **Mind Weave workflow** is a **directed acyclic graph** of **steps** (nodes): exactly **one Start** node (entry), exactly **one Stop** node (exit), and zero or more **Primitives**, **Utilities**, **Controls**, **Skills**, or **nested Workflow** references. **Data** moves between steps on named **handles**; **execution order** follows **trigger** (signal) edges and **data** dependencies.

Editor-saved graphs may also include **`kind: "annotation"`** nodes (notes and regions); **LLM-authored exports may omit them**—they are not executable steps and are outside the Tool Inventory taxonomy.

---

## Hard rules (must pass before you output JSON)

1. **Count nodes in `definition.graph.nodes`:** exactly **one** object with `"kind": "start"` and exactly **one** with `"kind": "stop"`. Never emit two Stop nodes, never emit two Start nodes, and never use `kind: "stop"` for anything except the single workflow exit.
2. **Stop has no outgoing edges:** nothing may use the Stop node’s `id` as **`source`** in `edges`. Stop is **only** a sink.
3. **Start `data` is never empty:** it must contain **`required_inputs`** as a **non-empty** array (unless the user explicitly asked for a workflow with **zero** inputs). Do **not** emit `"data": {}` on Start.
4. **Stop `data` is never empty:** it must contain **`required_outputs`** as a **non-empty** array (usually at least `{ "key": "output", "type": "<type>" }`). Do **not** emit `"data": {}` on Stop.
5. **Every primitive** (`kind: "primitive"`) must include **`primitive_type`** (string from the Tool Inventory) **and** a `data` object that matches that type (see Tool Inventory). A node whose `label` says “Bucket” or “Merge” is **still** a primitive only if `primitive_type` and valid `data` are present.
6. **`label` is not behavior:** the runtime keys off **`kind`**, **`primitive_type`**, **`utility_type`**, **`control_type`**, **`skill_type`**, and **`data`**. Labels are display-only; they cannot substitute for missing discriminators or ports.

---

## Anti-patterns (do not emit these)

- **`"data": {}` on Start or Stop** — invalid for generated exports; always include `required_inputs` / `required_outputs` as above.
- **Primitives without `primitive_type`** or with **`data`{}`** when the type requires fields (e.g. `string` needs `"text"`, `int` needs `"value"`, `list` must contain the list payload).
- **Fake pipelines:** a chain of `signal_out` → `trigger` through nodes that are **not** valid typed steps (untyped “Bucket 0-9” placeholders). If you need buckets, use **real** `utility_type` / `control_type` / `primitive_type` combinations from the Tool Inventory, or a **List** primitive with explicit JSON `data`.
- **Start-only graphs** — `nodes` that include **no** `kind: "stop"` object, or **`edges": []`** when the user asked for a workflow with outputs — invalid; always include **Stop** and at least the **pass-through** edges from **Smallest acceptable graph**.
- **Multiple Stop nodes** or **Stop → something** edges — always forbidden.
- **Treating the graph as pseudocode** — every field required by this document and the Tool Inventory must appear in JSON; partial sketches are not acceptable.

---

## Note for coding-oriented models

Pipeline and “chain of steps” thinking is fine for **trigger** order, but a Mind Weave graph is **structured data**, not source code. You must output **complete** node objects: **empty `data` on Start/Stop**, **missing `primitive_type`**, and **untyped primitives** cause import or runtime failure. Completeness beats cleverness.

**Do not “stub” the graph:** an empty-looking export (Start/Stop only, `"data": {}`, or `"edges": []`) is **not** a safe default—it is a **failed** answer. **Prefer** a minimal **valid** pass-through (see below) over an empty graph.

---

## Smallest acceptable graph (when unsure, extend this)

If you are not confident about the full algorithm, **start from this pattern** and add nodes: it always satisfies Start/Stop `data`, typed Stop output, and **non-empty** `edges`. Replace slot names and types to match the user message (e.g. list input → `type: "list"`; list output → Stop `type: "list"`).

**Pass-through (two edges):** one **trigger** edge (`signal_out` → `trigger`), one **data** edge from the Start slot key to Stop’s `output` handle.

**Minimal example (structure only—adjust IDs and types as needed):**

```json
{
  "kind": "mind_weave_workflow_export",
  "schema_version": 1,
  "exported_at": "2026-03-22T12:00:00.000Z",
  "definition": {
    "name": "Minimal pass-through",
    "description": "Placeholder: wire user inputs to Stop; extend with primitives/utilities/controls.",
    "graph": {
      "schema_version": 1,
      "nodes": [
        {
          "id": "n_start",
          "kind": "start",
          "label": "Start",
          "data": {
            "required_inputs": [
              { "key": "user_input", "type": "string", "value": null }
            ]
          },
          "position": { "x": 0, "y": 0 }
        },
        {
          "id": "n_stop",
          "kind": "stop",
          "label": "Stop",
          "data": {
            "required_outputs": [{ "key": "output", "type": "string" }]
          },
          "position": { "x": 400, "y": 0 }
        }
      ],
      "edges": [
        {
          "source": "n_start",
          "target": "n_stop",
          "source_handle": "signal_out",
          "target_handle": "trigger"
        },
        {
          "source": "n_start",
          "target": "n_stop",
          "source_handle": "user_input",
          "target_handle": "output"
        }
      ]
    }
  }
}
```

For a **list** in / **list** out request, change `user_input` to e.g. `integers`, set `type` to `"list"` on Start, and set Stop `required_outputs[0].type` to `"list"`, then insert processing nodes **between** Start and Stop and rewire.

---

## Sole output contract

- **Primary deliverable:** one JSON object with top-level `kind` equal to `mind_weave_workflow_export` and `schema_version` equal to `1`.
- **When embedded in a product:** return **only** that JSON (pretty-printed with 2-space indentation is recommended). Do **not** wrap it in Markdown code fences unless the user asks for Markdown.
- **`exported_at`:** use an ISO-8601 UTC timestamp string (example: `2026-03-22T12:00:00.000Z`).

---

## Export envelope (required shape)

Top-level keys:

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `kind` | string | yes | Must be exactly `mind_weave_workflow_export`. |
| `schema_version` | number | yes | Must be `1` for this document. |
| `exported_at` | string | yes | ISO-8601 instant. |
| `source_definition_id` | string | no | Opaque id from an export; **omit** when generating new workflows. |
| `definition` | object | yes | See below. |

The `definition` object:

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `name` | string | yes | Human-readable workflow title. |
| `description` | string or null | yes | Short summary of what the workflow does. |
| `graph` | object | yes | The graph; see **Graph object** below. |
| `palette_id` | string or null | no | Theme/palette uuid; **omit** or set `null` when generating new exports unless the host supplies a valid id. |

### Envelope shape (do not ship empty graphs)

The top-level keys are the same as in any export. **Do not** use **`"nodes": []`** or **`"edges": []`** as your final answer when the user described a workflow—those were only ever meant as an **illustration of key names**, not a valid output. A real response always includes at least **Start** and **Stop** with populated `data` and **edges** as in **Smallest acceptable graph** below or the **Minimal end-to-end example** section below.

---

## Graph object

Inside `definition.graph`:

| Key | Type | Notes |
|-----|------|--------|
| `schema_version` | number | Use `1`. |
| `nodes` | array | Each element is one node object (see **Node shape** below). |
| `edges` | array | Each element is one edge object (see **Edges** below). |

### Node shape

**Every node** must include:

- `id` — non-empty string, **unique** within the graph. Use a stable pattern such as `n_<short_prefix>_<suffix>`; avoid collisions.
- `kind` — one of: `start`, `stop`, `primitive`, `utility`, `control`, `skill`, `workflow`.
- `label` — short string shown in UIs.
- `position` — object `{ "x": <number>, "y": <number> }` (canvas coordinates; rough layout is fine).
- `data` — object; shape depends on `kind` (see Tool Inventory below for per-type fields).

**Discriminators** (required when applicable):

- If `kind` is `primitive`, include `primitive_type`.
- If `kind` is `utility`, include `utility_type`.
- If `kind` is `control`, include `control_type`.
- If `kind` is `skill`, include `skill_type`.
- If `kind` is `workflow`, include `data.workflow_id` (uuid string of another workflow definition).

**Critical (Mind Weave import / canvas):** Put **`primitive_type`**, **`utility_type`**, **`control_type`**, and **`skill_type`** on the **node object** as **siblings** of **`kind`** and **`id`**—**not** nested inside **`data`**. Models sometimes emit **`"data": { "primitive_type": "dictionary", … }`**; that shape is **wrong** for import. Omitting **`control_type`** / **`utility_type`** on control/utility nodes also breaks the graph. The editor may show **Invalid step** (amber) for those rows until fixed.

Exact allowed strings for each discriminator are listed in the Tool Inventory below and its manifest JSON.

---

## Edges

Each edge is an object:

```json
{
  "source": "<source_node_id>",
  "target": "<target_node_id>",
  "source_handle": "<string or omit>",
  "target_handle": "<string or omit>"
}
```

Omitted handles may be treated as defaults by the runtime; **prefer explicit handles** for clarity and determinism.

### Triggers (execution order)

- Most nodes have a **trigger** input on handle **`trigger`**.
- The Start node and most steps expose a **signal output** on handle **`signal_out`**.
- **Pattern:** connect `source_handle`: **`signal_out`** → `target_handle`: **`trigger`** so the downstream step runs after its upstream step in the control-flow chain.

**Rule of thumb:** every non-Start node should be **reachable** from Start through a chain of trigger edges (possibly with parallel branches), and Stop should be reachable from the subgraph that produces the final result.

### Data edges

- Connect a **source output handle** to a **target input handle**.
- **`target_handle`** must equal the **input port key** defined in the target node’s `required_inputs` (for utilities, controls, and many skills).
- **`source_handle`** is usually **`output`** for primitives and utilities, or a **Start slot key** when wiring from Start.

### Dictionary merge (summary)

When assembling a **Dictionary** primitive from several upstream steps (see Tool Inventory below for full detail):

- Each **data** wire to the Dictionary’s **`input`** contributes one entry; the dictionary **key** is derived from the edge’s **`source_handle`** on the **source** side, defaulting to **`output`** if blank.
- **Dictionary** outputs wired in merge as objects via `dict.update`.
- If several wires would use the **same** key (e.g. all use **`output`**), the runtime makes keys unique by appending **`_`** + **source node `id`**, so parallel scalars do not silently overwrite each other.
- For predictable **named** keys, use **Start** slots with **distinct `key`** values and wire from those handles.

---

## Phased algorithm (follow in order)

**Phase A — Extract**  
From the user message, list: required **inputs**, required **final output type**, and any **constraints** (no external APIs, no LLM, etc.). **Immediately** write down the **Start** `required_inputs` entries (keys + types) and **Stop** `required_outputs` type—you will **not** emit empty `data` on either node.

**Phase B — Plan**  
Pick node types **only** from the Tool Inventory below (or the host’s allowed list). Prefer **Primitives, Utilities, Controls** for simple tasks. Avoid **Skills** and **nested workflows** unless requested and fully specified.

**Phase C — Instantiate**  
Create each node with a **unique** `id`, sensible `label`, `position`, and fully populated `data`. Use `value: null` in `required_inputs` where the user must supply data at run time.

**Phase D — Wire**

1. Add **trigger** edges so execution can flow **Start → … → Stop**.
2. Add **data** edges; verify **`source_handle`** / **`target_handle`** names match ports.
3. For **Dictionary** assembly, follow **Dictionary merge (summary)** above and the Tool Inventory below.

**Phase E — Stop match**  
Ensure the **type** in Stop `required_outputs` matches the wired upstream value (`dictionary` vs `string`, etc.).

**Phase F — Pre-flight checklist (tick every item before emitting)**

1. **Start count:** exactly one node has `"kind": "start"`.
2. **Stop count:** exactly one node has `"kind": "stop"`.
3. **Stop edges:** no edge has `source` equal to the Stop node’s `id`.
4. **Start `data`:** object contains `required_inputs` (non-empty array) with valid `key`, `type`, and `value` (use `null` for run-time inputs unless a default is intended).
5. **Stop `data`:** object contains `required_outputs` (non-empty array) with `key` and `type` matching what you wire into Stop.
6. **Primitives:** every `kind: "primitive"` node has `primitive_type` and type-appropriate `data` (Tool Inventory).
7. **Utilities / controls / skills:** each has the right `*_type` and `data` including `required_inputs` where that step requires ports.
8. **Acyclic** graph (no cycles).
9. **Handles:** every `source_handle` / `target_handle` in `edges` matches real ports for those node types.
10. **Final output type:** Stop’s first `required_outputs` entry’s `type` matches the wired upstream value (`list`, `dictionary`, `string`, etc.).
11. **Edges non-empty:** `edges` is **not** `[]` unless the user explicitly asked for a graph with no connections (almost never). If the graph would be empty, use **Smallest acceptable graph** at minimum.

**Phase G — Emit**  
Output **only** the final `mind_weave_workflow_export` JSON (pretty-printed).

---

## Minimal end-to-end example (toy graph)

**Intent:** pass through a single string from Start to Stop.

```json
{
  "kind": "mind_weave_workflow_export",
  "schema_version": 1,
  "exported_at": "2026-03-22T12:00:00.000Z",
  "definition": {
    "name": "Echo string",
    "description": "Passes the start input through to Stop as the final string.",
    "graph": {
      "schema_version": 1,
      "nodes": [
        {
          "id": "n_start",
          "kind": "start",
          "label": "Start",
          "data": {
            "required_inputs": [
              { "key": "message", "type": "string", "value": null }
            ]
          },
          "position": { "x": 0, "y": 0 }
        },
        {
          "id": "n_stop",
          "kind": "stop",
          "label": "Stop",
          "data": {
            "required_outputs": [{ "key": "output", "type": "string" }]
          },
          "position": { "x": 400, "y": 0 }
        }
      ],
      "edges": [
        {
          "source": "n_start",
          "target": "n_stop",
          "source_handle": "signal_out",
          "target_handle": "trigger"
        },
        {
          "source": "n_start",
          "target": "n_stop",
          "source_handle": "message",
          "target_handle": "output"
        }
      ]
    }
  }
}
```

---

## Reference: list-shaped output (bucket-style placeholder)

**Intent:** Show a **valid** graph whose **Stop** output is a **list** of **dictionaries** with keys like `Range`, `Count`, and `Items`—the same **shape** often requested for “bucket” problems.

**Important:** This example uses a **static** **List** primitive so the export is **importable and runnable**. It does **not** compute buckets from the Start input; real bucket logic needs **controls** (e.g. **For loop**, **between**, **modulo_ints**, **add_to_list**) per the Tool Inventory. The **Start** slot `integers` is declared to match the usual **input** (list of ints) but is **not** wired through in this placeholder—**you** must wire it into a loop and utilities when implementing a real sort.

```json
{
  "kind": "mind_weave_workflow_export",
  "schema_version": 1,
  "exported_at": "2026-03-22T12:00:00.000Z",
  "definition": {
    "name": "Bucket-shaped list output (static placeholder)",
    "description": "Stop outputs a list of dicts with Range, Count, Items. Static list only—wire integers through For loop and utilities for real bucketing.",
    "graph": {
      "schema_version": 1,
      "nodes": [
        {
          "id": "n_start",
          "kind": "start",
          "label": "Start",
          "data": {
            "required_inputs": [
              { "key": "integers", "type": "list", "value": null }
            ]
          },
          "position": { "x": 0, "y": 0 }
        },
        {
          "id": "n_buckets",
          "kind": "primitive",
          "primitive_type": "list",
          "label": "Bucket list (static shape)",
          "data": [
            { "Range": "0-9", "Count": 0, "Items": [] },
            { "Range": "10-19", "Count": 0, "Items": [] },
            { "Range": "20-29", "Count": 0, "Items": [] },
            { "Range": "30-39", "Count": 0, "Items": [] },
            { "Range": "40-49", "Count": 0, "Items": [] },
            { "Range": "50-59", "Count": 0, "Items": [] },
            { "Range": "60-69", "Count": 0, "Items": [] },
            { "Range": "70-79", "Count": 0, "Items": [] },
            { "Range": "80-89", "Count": 0, "Items": [] },
            { "Range": "90-99", "Count": 0, "Items": [] }
          ],
          "position": { "x": 320, "y": 0 }
        },
        {
          "id": "n_stop",
          "kind": "stop",
          "label": "Stop",
          "data": {
            "required_outputs": [{ "key": "output", "type": "list" }]
          },
          "position": { "x": 640, "y": 0 }
        }
      ],
      "edges": [
        {
          "source": "n_start",
          "target": "n_buckets",
          "source_handle": "signal_out",
          "target_handle": "trigger"
        },
        {
          "source": "n_buckets",
          "target": "n_stop",
          "source_handle": "signal_out",
          "target_handle": "trigger"
        },
        {
          "source": "n_buckets",
          "target": "n_stop",
          "source_handle": "output",
          "target_handle": "output"
        }
      ]
    }
  }
}
```

---

## Reference export (optional)

A host may attach an additional **example export JSON file** (any filename) showing a larger multi-step graph. That attachment is **not** required to apply the rules in this document.

---

## Non-goals and safety

- Do **not** fabricate **UUIDs** for nested workflows or external resources.
- Do **not** assume **Skills** are configured; omit them unless explicitly required.
- Do **not** call live HTTP APIs to “validate” the graph; **structural** validation using these Instructions and the Tool Inventory below is enough.
- JSON **does not** support comments; do not add `//` or `/* */` inside the file.

---

## Failure modes checklist

| Symptom | Likely cause |
|---------|----------------|
| Import rejects JSON | Missing `kind`, wrong `schema_version`, or invalid JSON. |
| Run fails on a step | Wrong `target_handle` / `source_handle`, or `value: null` not wired. |
| Start/Stop have empty `data` | Omitted `required_inputs` / `required_outputs`; see **Hard rules** above. |
| Primitive missing `primitive_type` or wrong `data` | Untyped or placeholder “bucket”/“merge” nodes; every primitive needs `primitive_type` + valid `data` per Tool Inventory. |
| Multiple Stop nodes or edges from Stop | Violates **Hard rules** above; only one Stop, no outgoing edges from Stop. |
| Dictionary missing expected keys | Unintended key overlap before disambiguation; prefer distinct **Start** slot keys, or see **Dictionary merge (summary)** above. |
| Stop type error | Stop `required_outputs[0].type` does not match wired value. |
| **`nodes` has Start but no Stop**, or only one node | Often caused by **permissive JSON Schema** + token minimization; tighten **Structure** (see **Reference JSON Schema** above) so `nodes` must **contain** Stop and `edges` cannot be empty. |
| Only Start+Stop, empty `data`, or `edges: []` | Model reverted to a stub; **forbidden** for normal requests—use **Smallest acceptable graph** above or **Reference: list-shaped output (bucket-style placeholder)** below. |

---

*Document version: Mind Weave workflow export schema version 1. Tool Inventory follows below in the same prompt.*
