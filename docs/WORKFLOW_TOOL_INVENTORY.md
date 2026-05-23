# Workflow tool inventory (Mind Weave graph steps)

**Collation:** These materials are combined into a single prompt: **Instructions** (referenced above) first, then **Tool Inventory** (this section). Nothing here points at other folders or repositories.

**Audience:** Authors and language models that **do not** have access to any source repository. Everything needed to choose steps and populate node `data` is in the Instructions above and in this Tool Inventory.

| You need | Use |
|----------|-----|
| Export shape, `edges`, triggers, phased algorithm, minimal example | **Instructions** (above) |
| What steps exist, handles, typical `data`, merge rules | **This inventory** |

**Anti-stub rule:** If the user asked for a workflow that processes inputs and produces outputs, a graph with **only** Start and Stop, **`"data": {}`** on either, or **`"edges": []`**, is **invalid**. Always fill **Start** / **Stop** `data` and add at least the **smallest acceptable** wiring from the Instructions (pass-through or placeholder), then extend with steps from this inventory.

**JSON Schema caveat:** If your host uses **JSON Schema** for structured output, a schema with **empty `properties` on `data`**, **`additionalProperties: true` everywhere**, **`edges` without `minItems`**, or **`nodes` without requiring both Start and Stop**, will **validate** outputs like **only `n_start`**, **`edges: []`**, or **`data: {}`**—models minimize tokens to the **easiest valid JSON**. Instructions alone cannot fix that. Use [`shared/mind_weave_workflow_export_llm_response.schema.json`](shared/mind_weave_workflow_export_llm_response.schema.json) (requires **`edges.minItems` ≥ 1**, **`contains`** Start and Stop in `nodes`, and Start/Stop `data` via `if`/`then`) **as your Structure**, or extend your schema the same way.

**Mind Weave product:** When a **Structure** is attached to **Simple LLM Call**, the workflow executor passes your JSON Schema to the model as **`response_format`** and stores the **parsed JSON** as the node output—**no** extra wrapping or stripping of the root object. If you need the full **`mind_weave_workflow_export`** envelope, your Structure schema must describe that **full** object at the root; the app does not infer it.

**Global rules**

- Every step has graph `kind` ∈ `start` | `stop` | `primitive` | `utility` | `control` | `skill` | `workflow`.
- Discriminators (exact strings): `primitive_type`, `utility_type`, `control_type`, `skill_type`.
- **Do not invent** new `*_type` strings; only use combinations listed in the **manifest JSON** at the end of this document.
- **Handles:** Most value-producing nodes expose **`output`**. Start exposes one **source** handle per **`required_inputs[].key`**. Many nodes take **`trigger`** (control flow) and emit **`signal_out`**. Utilities and controls use **`required_inputs`**; incoming data edges use **`target_handle`** equal to that input’s **`key`**.
- **Non-negotiable for primitives:** every `kind: "primitive"` node **must** include **`primitive_type`** and a valid `data` payload per the table below. **Never** emit a primitive with only `"data": {}` unless the type explicitly allows an empty object (e.g. **dictionary** merge targets may start empty). **Never** omit `primitive_type` because the `label` text describes the intent.

---

## Start and Stop

| Step | `kind` | Role |
|------|--------|------|
| Start | `start` | Declares run-time inputs; each slot becomes a **source** handle named exactly like its `key`. |
| Stop | `stop` | Declares final workflow output; wire upstream into **`target_handle`** = slot **`key`** (often `output`). |

**`data` shapes**

- **Start:** `required_inputs`: array of `{ "key": <string>, "type": <string>, "value": <any or null> }`. Types include `string`, `int`, `boolean`, `list`, `dictionary`, `structure`, `document`, `any`. `value: null` means the runner must supply that input at execution time.
- **Stop:** `required_outputs`: array of `{ "key": <string>, "type": <string> }`. The wired upstream value’s type must match.

**Invalid for generated exports**

- **`"data": {}` on Start** — missing `required_inputs`; the Instructions require a non-empty `required_inputs` array unless the user explicitly wanted zero inputs.
- **`"data": {}` on Stop** — missing `required_outputs`; always declare at least one output slot (typically `output`).

**Suggested usage**

- **Start:** Use **distinct `key` values** when those fields should become **separate dictionary keys** in a Dictionary primitive merge.
- **Stop:** Set `required_outputs[0].type` to match the wired value (`string`, `dictionary`, `document`, etc.).

---

## Primitives (`kind: "primitive"` + `primitive_type`)

| `primitive_type` | Typical `data` | Output handle | Suggested usage |
|------------------|----------------|-----------------|-----------------|
| `string` | `{ "text": "..." }` | `output` | Constants, literals, seeds. |
| `int` | `{ "value": <int> }` | `output` | Numeric constants; wire to arithmetic or Stop. |
| `datetime` | `{ "iso": "<RFC3339 string>" \| null, optional "use_now": true \| false }` (canonical in `data`; root-level `use_now` / `useNow` or `data.useNow` are normalized at parse time) | `output` | RFC3339 instants for skills and Stop; optional **`use_now`** uses current UTC at run when there is no incoming wire (upstream still wins). Handles **`input`** / **`output`** match the editor. |
| `boolean` | `{ "value": true \| false }` | `output` | Flags. |
| `list` | The node’s `data` stores the list payload as JSON (commonly the array is the main content of `data`; importers accept the graph shape produced by the app—use a JSON array for static list values when authoring by hand). | `output` | Static lists; or build lists via utilities / loops. |
| `dictionary` | `{ ... }` or `{}` filled by incoming **data** wires to handle `input` | `output` | Merge many sources into one object (see **Dictionary merge** below). |
| `structure` | `{ "structure_id": "<uuid>" }` | `output` | References a saved **Structure** definition for schema-shaped data; often pairs with **Simple LLM Call** for JSON responses. |
| `document` | `{ "document_id": "<uuid>" }` | `output` | Loads a stored **Document** by id; output includes metadata and **`markdown`** (wire name for stored **body** text—often Markdown, may be JSON or other text). **Build** may wire **`output`** into any **`required_inputs`** slot typed **`string`** or **`any`** (e.g. **Simple LLM** **User Prompt**); **`string`** receives body text only at runtime; **`any`** receives the full dict. |
| `image` | `{ optional "artifact_id", "required_inputs": [{ "key": "image", "type": "dictionary", "value": null }] }` — wired **`image`** overrides **`artifact_id`** | `output` | User-owned **`url_snapshot_artifacts`** (upload via **POST** `/api/v1/url-snapshot-artifacts` or wire from **`capture_url_snapshot`**); emits **`{ artifact_id, mime_type, width, height }`** for **Multimodal LLM**. |

### Dictionary merge (parallel wires)

When multiple **data** edges connect to the Dictionary node’s **`input`** handle (and `target_handle` is not `trigger`):

- **Dictionary** upstream (`kind: "dictionary"` output): inner `data` objects are shallow-merged with `dict.update` (later keys overwrite).
- **Other** upstream (Int, String, Start slot, etc.): the value is stored under **`data[source_handle]`** on the merged result, where **`source_handle`** comes from the **source** end of the edge; if missing or blank, it defaults to **`output`**.
- If the same key would be written twice (e.g. several upstream nodes all use source handle **`output`**), the runtime assigns **`{source_handle}_{source_node_id}`** (suffix is the **source node’s `id`**) so each wire gets a **distinct** key—parallel scalars no longer silently overwrite a single `output` entry.

**Suggested usage:** Prefer **Start** slots with **distinct keys** for user-facing fields; parallel **Int** / **String** primitives are safe because of the disambiguation rule above.

---

## Utilities (`kind: "utility"` + `utility_type`)

Each utility typically includes `data.required_inputs`: `{ "key", "type", "value" }` with `value: null` when the port must be wired or supplied at run time.

| `utility_type` | Main inputs (`target_handle` = `key`) | Output | Suggested usage |
|----------------|----------------------------------------|--------|-----------------|
| `list_to_string` | `list` | `output` (string) | **Joined text** for prompts when `data.use_text_join` is true (editor default): concatenate items with newlines or spaces via `data.add_line_breaks_between_items` (default true). **JSON array** (pretty-printed) when `use_text_join` is false or omitted — use with **String to List** for round-trips. |
| `string_to_list` | `string` | `output` (list) | Parse JSON array text; pair with **List to String** only when the latter emits JSON (`use_text_join` false / legacy empty `data`). |
| `prepend_text` | `target_string`, `text_to_prepend`; optional `data.add_additional_line` (boolean) for a blank line between chunks | `output` (string) | Prefix one string onto another. |
| `string_trunc` | `target_string`, `start_index`, `end_index` | `output_string` (string) | Substring with inclusive `end_index`, or `end_index == -1` through end; `start_index` must be ≥ 0. |
| `len_from_list` | `list` | `output` (int) | Count items. |
| `random_item_from_list` | `list` | `output` (typed by element: string, list, dictionary, int, boolean) | Pick one uniform random element (`secrets.randbelow` index); empty list errors. |
| `int_to_string` | `input` | `output` (string) | Format int as decimal string. |
| `list_item_by_index` | `list`, `index` | `output` | Indexed access. |
| `dictionary_value_by_key` | `dictionary`, `key`, optional `fallback` wire; optional `data.fallback_value` (JSON) | typed output | Read one key; optional fallback when the key is absent or the value is null (wire overrides `fallback_value`); wrong type at an existing key still errors. |
| `read_document_property` | `document`, plus key / property selection in `data` | typed per `output_value_type` | Read fields such as **body**, **name**, **description**, **id** from document output. |
| `load_document` | `document_id` **or** `document_name` (exactly one) | `output` (**document**) | Load a document at run time by id or by globally unique name. **`output`** may wire into **`string`** / **`any`** slots (body text vs full dict — same rules as **Document** primitive). |
| `upsert_document` | `name`, `content`, optional `existing_document_id`, `write_mode` (`replace` \| `append` \| `merge_json`) | `output` (**document**) | **Inverse of the Document primitive:** persists **plain text** (or JSON for **`merge_json`**) to a user-owned **`documents`** row and emits **`DocumentNodeOutput`**. Wire any string producer (e.g. formatted multi-speaker transcript, **Simple LLM Call** text) to **`content`**; set globally unique **`name`** (inline or wired). Default **`write_mode`** **`replace`** overwrites the stored body—typical for saving a full transcript. Use **`append`** / **`merge_json`** for incremental or JSON merge flows; **`merge_json`** requires JSON objects and deterministic stored JSON. **`output`** may wire into **`string`** / **`any`** slots like **Load Document**. |
| `parse_document_body` | `document` | dictionary or list | Parse JSON from document body text; root must be object or array. |
| `google_docs_parse_document` | `document` (dictionary from **Google Docs Get Document** or compatible **`document_payload`**) | `output` (list) | Split curated **`document_payload`** into generic **chunk** objects (`kind`: `text` \| `table` \| `image`). **`chunk_strategy`**: `structure` (default), `tab`, or `flat`. Optional **`max_chunk_text_chars`**. No network I/O. |
| `html_parse_basic` | `html` | `output` (dictionary) | Structural HTML parse: **`title`** (always from the full document `<title>`), **`text_blocks`** (list of objects ``{"tag": "...", "text": "..."}`` in document order: `tag` is the lowercased source element; `text` is normalized like before; one block per **leaf** `article` (e.g. product cards in a `div` grid), plus headings, `p`, list items, and `div` / `section` / `main` only when they are “pure” wrappers with no more-specific descendants we already expand—so listing pages can yield many blocks, not a single huge outer `div`; then any candidate that is a **strict DOM ancestor** of another emitted candidate is **dropped**, so parent elements are not emitted as a concatenated “rollup” when more specific child blocks are already present; downstream steps that need plain strings should read each object’s `text` or map the list), **`links`** (anchor `href` plus visible text; entries with **no** visible text after cleaning—e.g. image-only links—are **omitted**). Optional **`data.content_root_css`** (CSS selector, BeautifulSoup `select_one`) scopes blocks, links, and segment extraction to a subtree; title stays document-wide. If `content_root_css` is set and matches nothing, the step **errors**. Optional **`data.granularity`**: omit or **`default`** keeps the legacy output shape (only `title`, `text_blocks`, `links`). Non-default values add **`segment_text_blocks`** and **`parse_options`** (`granularity`, `content_root_css`, the latter `null` when unset): **`list_items`** (direct `li` under `ol`/`ul` in order), **`articles`** (`article` tags in order). No main-content or boilerplate removal. Non-rendering elements (`script`, `style`, `noscript`, `template`) are removed before text extraction. String fields are passed through the shared text-noise pipeline (invisible Unicode, HTML entities, plain-text `\uFFFF` / `\U00000000`-style runs decoded to real characters—including over-escaped `\\u…` from scrapes), literal `\\n`-style backslash-escape *characters* in text are turned into space, and output is collapsed to single-line spacing (newlines/tabs/NBSP → spaces). Link `href` values are unwrapped when the parser delivers spurious backslash–quote runs or extra ASCII quotes (e.g. from `&quot;` in attributes). Typical chain: **Fetch URL** → **Dictionary value by key** (`body`) → this node → LLM or **Stop** (`dictionary`). |
| `write_object_to_document_body` | `value` (dict or list) | `output` (string) | Deterministic JSON text for chaining into **Upsert Document**. |
| `append_value_to_document` | `document`, `value` | `output` (string) | Append serialized value to body text in memory (does not persist). |
| `validate_against_structure` | `value`, optional wired `structure`; optional `data.structure_id` | typed output | Validate instance against a Structure JSON Schema (`Draft202012Validator`). |
| `add_to_list` | `list`, `value` | `output` (list) | Append an item. **Inside a For loop body**, the executor keeps **loop-scoped carry** so the same Add-to-List node can accumulate across iterations; after the loop finishes, downstream nodes see the **final** list. |
| `add_ints` | `input_a`, `input_b` | `output` (int) | Sum. |
| `add_days` | `input` (datetime / RFC3339), `days` (int, may be negative) | `output` (datetime) | Shift instant by whole days (UTC `timedelta`); compose with DateTime **`use_now`** for relative windows. |
| `subtract_ints` | two int inputs | `output` | |
| `multiply_ints` | two int inputs | `output` | |
| `divide_ints` | two int inputs | `output` | |
| `modulo_ints` | two int inputs | `output` | |
| `min_ints` | two int inputs | `output` | |
| `max_ints` | two int inputs | `output` | |
| `sandbox_tick` | (run override or wired tick) | `output` (dictionary) | Full `SandboxTickInput` for sandbox brains. See [SANDBOX.md](SANDBOX.md). |
| `sandbox_get_position` | `sandbox_tick` | `output` (dictionary) | Creature `{x, y}`. |
| `sandbox_get_facing` | `sandbox_tick` | `output` (string) | Creature facing `N`/`E`/`S`/`W`. |
| `sandbox_get_nearby` | `sandbox_tick` | `output` (list) | Eight typed neighbor cells clockwise from facing. |
| `sandbox_move_forward` | optional `reason` | `output` (dictionary) | `{action: "move_forward"}` for Stop. |
| `sandbox_turn_left` / `sandbox_turn_right` / `sandbox_idle` | optional `reason` | `output` (dictionary) | Navigation action dict for Stop. |
| `sandbox_pick_up_item` | optional `reason` | `output` (dictionary) | `{action: "pick_up_item"}` — forward-adjacent ball/food into creature inventory. |
| `sandbox_place_item` | optional `reason`, optional `item_type` (`ball` \| `food`) | `output` (dictionary) | `{action: "place_item", item_type?: ...}` — place from inventory on forward cell. |
| `sandbox_get_inventory` | `sandbox_tick` | `output` (list) | Focused creature held items. |

---

## Controls (`kind: "control"` + `control_type`)

| `control_type` | Behavior | Typical handles | Suggested usage |
|----------------|----------|-----------------|-----------------|
| `basic_conditional` | Branch on condition | `condition`, **`true`** / **`false`** (signal paths) | If/else style flows. |
| `is`, `gt`, `lt`, `gte`, `lte` | Compare | Value inputs + **`true`** / **`false`** branches | Comparisons. |
| `is_empty` | True when value is `[]` or `{}` | `value` (list or dictionary) + **`true`** / **`false`** branches | Branch on empty collection without **Len from List** / extra compares. |
| `between` | Range test | `low`, `value`, `high` + branches | Inclusive range. |
| `and`, `or`, `xor` | Boolean combine | inputs → **`output`** (boolean) | Logic without separate branch wires. |
| `not` | Negate | `input` → **`output`** | |
| `try_catch` | **`try`** region first; failures route to **`catch`**; structured envelope output | **`trigger`** schedules the region; **`try`** / **`catch`** are signal handles for interior wiring; optional **`value`** binds a wired result **from inside `try`** (feeds **`{ ok: true, value }` when `try` succeeds); **`output`** / **`envelope`** emit dictionary payloads (**`ok`**, **`value`** or **`error`**). | Interior graphs are validated separately (overlap, missing **`try`** edge → **422**). Handled failures record **`handled_by_try_catch`** on the inner **`node.failed`** (and SSE metadata on streamed runs). **Global cycle detection** ignores edges that exist only to wire **`value`** (producer → **`value`** feedback is allowed). See [ARCHITECTURE.md](ARCHITECTURE.md). |
| `for_loop` | Iterate over a list | **`input`** (list), **`item`**, **`signal_out`**, **`trigger`**; optional **`summary`** (**dictionary**: items processed/failed + per-item results/errors when enabled) | **`data.iteration_mode`**: **`sequential`** (default), **`parallel`** (same semantics as legacy **`parallel_iterations: true`**), **`batched`** (**`batch_size`**, capped by deployment ceiling **`WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING`**). Optional **`continue_on_error`**, **`max_iterations`**. List length is checked against resolved **`execution_limits.max_loop_iterations`** before the loop runs. |
| `for_loop_end` | Aggregate named exports from the loop body | **`trigger`** from the paired For loop’s **`signal_out`**; **data** edges from body nodes with `target_handle` = export key → **`output`** (dictionary) | Persist `data.for_loop_id` as the **For Loop** node’s `id` (the workflow editor sets this when you wire **`signal_out` → `trigger`**; you can still override in the inspector). **Not** part of the per-iteration body—runs **once** on the main schedule after the loop completes. |

**Suggested usage:** For branching controls, only **one** of **`true`** / **`false`** runs per evaluation. **For Loop End** must reference the correct **`for_loop_id`** and use **named** `target_handle` values matching your export keys.

### For loop and For loop end (minimal valid `data` fragments)

Use these shapes when emitting JSON (ids must match your graph’s node `id` strings):

**For loop** (`control_type`: `for_loop`):

```json
"data": {
  "required_inputs": [
    { "key": "input", "type": "list", "value": null }
  ]
}
```

Wire the list to **`target_handle`: `input`**. The loop exposes **`item`**, **`signal_out`**, and **`trigger`** per app wiring; optional **`summary`** is wired like other outputs when you need an aggregated **`dictionary`**.

**Try / Catch** (`control_type`: `try_catch`):

```json
"data": {}
```

Schedule with **`trigger`**; wire the **`try`** handle for the happy path and **`catch`** for the recovery path. Optional **`value`** accepts a **data** edge from a node **inside** `try` (for example **Stop** output) when you want **`ok: true`** to carry that payload.

**For loop end** (`control_type`: `for_loop_end`):

```json
"data": {
  "for_loop_id": "<id-of-the-for-loop-node>",
  "exports": ["bucket_a", "bucket_b"]
}
```

**Trigger:** `for_loop` **`signal_out`** → `for_loop_end` **`trigger`** (the editor fills `for_loop_id` from that connection). **Data** edges from body nodes into **For loop end** use **`target_handle`** equal to an export name in `exports`.

**Bucket-style problems (design guidance, not a full graph):** iterate the input **list** with **`for_loop`**, classify each **integer** with **`between`** / **`modulo_ints`** / comparators, accumulate with **`add_to_list`** and/or **`dictionary`** primitives, then assemble a **final list** (often via **List** primitive or utilities) and wire **`Stop`** with `type: "list"`. Do **not** create untyped primitive nodes labeled “Bucket” without **`primitive_type`** and real `data`.

---

## Bucket / range aggregation (conceptual map)

| Stage | Typical steps |
|-------|----------------|
| Input | **Start** slot `type: "list"` (e.g. integers) |
| Iterate | **`for_loop`** over that list |
| Classify range | **`between`** (inclusive bounds) or **`modulo_ints`** / **`divide_ints`** + **`gt`** / **`lte`** to map to Decade index |
| Per-bucket accumulators | **`add_to_list`** (and optionally **Dictionary** primitives for per-bucket dicts) |
| Finish loop | **`for_loop_end`** with **`exports`** naming wired lists |
| Final output | Build **list** of **dictionaries** (utilities + primitives) → **Stop** `type: "list"` |

This table is **design guidance** only; the exact graph depends on the user request and the **manifest** above.

---

## Skills (`kind: "skill"` + `skill_type`)

Skills need **live configuration** (accounts, models, time zones). For hand-authored exports, include them only if you can fill `data` plausibly; otherwise omit and use primitives/utilities.

| `skill_type` | Typical `data` (non-exhaustive) | Suggested usage |
|--------------|---------------------------------|-----------------|
| `simple_llm_call` | `persona_id` (uuid string), `required_inputs` for **user prompt** and optional **additional context**, optional `structure_id` when structured JSON is required, model settings as stored by the app | Chat/completion step with persona system prompt. **`user_prompt`** / **`additional_context`** may be wired from **Document** / **Load Document** / **Upsert Document** (**`string`** slots get document body text). |
| `multimodal_llm` | `persona_id`, **`required_inputs`** for **`user_prompt`** (or **`prompt`**) and **`images`** (list of `{ artifact_id, ... }` or snapshot-shaped dict), optional **`model`** override, optional **`structure_id`** / Structure wire — same structured-output rules as **`simple_llm_call`** | Vision/chat step: resolves user-owned **`url_snapshot_artifacts`** into OpenAI-style image parts; output is **`ResponseNodeOutput`** or structured **`DictionaryNodeOutput`**. Non-vision models yield **`MODEL_NOT_MULTIMODAL`**. **`user_prompt`** / **`additional_context`** may be wired from **Document** / **Load Document** / **Upsert Document** (**`string`** slots get document body text). See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md#multimodal-llm--skill-multimodal_llm). |
| `text_to_speech` | **`tts_model_id`** (registry UUID), **`required_inputs`** for **`text`**, optional **`engine`** override, optional **`tts_options`** (opaque object) | Local TTS via HTTP bridge; output is **`audio`** (base64 WAV in JSON). |
| `transcribe_audio` | Optional **`language`**, optional **`task`** (`transcribe` \| `translate`), optional reserved **`model`**; wire **`trigger`** from upstream (e.g. **Start**) for ordering | **Editor Run (stream) only** — the browser records audio; the API transcribes via the **STT bridge** (`faster-whisper`). Output is **plain string** (transcript) for downstream **Simple LLM Call**, **TTS**, **Stop**, etc. Sync **`POST .../run`** is rejected for graphs that contain this node unless you use **`output_overrides`**. |
| `audio_file_input` | Optional **`audio_artifact_id`** (saved file UUID), optional **`language`**, optional **`task`** (`transcribe` \| `translate`), optional reserved **`model`**; wire **`trigger`** from upstream for ordering | Select an audio file and transcribe it via the same **STT bridge** as Voice input. With **`audio_artifact_id`**, sync or streamed runs can execute without prompting. Without a saved file, **Run (stream)** emits a file-picker prompt and uploads the file for that run only. Output is **plain string** (transcript). |
| `transcribe_file` | **`provider`** (`local_whisper` \| `assemblyai`; default `local_whisper`), optional **`provider_model_id`** (when the provider lists models in **`GET /transcription/providers`**; empty → deployment default, e.g. **`ASSEMBLYAI_SPEECH_MODELS`**), optional **`audio_artifact_id`**, optional **`language`**, optional **`task`** (`transcribe` \| `translate`), optional **`prompt`** (bias / word-boost), boolean **`diarization_enabled`**, boolean **`include_word_timestamps`**; wire **`trigger`** from upstream for ordering | Provider-abstracted speech-to-text emitting a rich **Transcript primitive** (`{type: "transcript", segments, optional words & speakers, …}`). Saved artifact runs sync or via Build SSE (`POST …/runs` + `GET …/events`); runtime upload uses the same `input_required` pattern as `audio_file_input` but with `kind: "transcribe_file"`. Long-running cloud jobs persist as `transcription_jobs` rows and survive client disconnects via the lifespan poller; clients reconnect with **`GET /api/v1/workflow-runs/{run_id}/events`** (replay + tail). Provider list (with optional **`models`**) at **`GET /transcription/providers`**. AssemblyAI keys live under **My Settings → API Settings** (`assemblyai`). |
| `gmail_list_messages` | optional **`max_results`**, **`after`** / **`before`** (RFC3339), **`unread_only`**, raw **`query`** (Gmail search string), inbox category filters; `required_inputs` may wire overrides; OAuth from My Settings → Google for workflows | Search/list mailbox messages; output is a **dictionary** with **`messages`** and **`resultSizeEstimate`**. |
| `calendar_list_events` | **`calendar_id`**, **`time_min`** / **`time_max`** (RFC3339) via `required_inputs` or static fields; OAuth from My Settings | List events in a window; output is **`dictionary`** with curated **`events`**. |
| `google_docs_get_document` | **`document_url_or_id`** (URL or id; wireable), optional **`include_tabs_content`** (default true); OAuth from My Settings | Read-only Google Docs fetch; output **`dictionary`** with **`document_payload`** (curated tabs/blocks; inline images stored as **`url_snapshot_artifacts`** refs). See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md#google-docs-get-document--skill-google_docs_get_document). |
| `fetch_url` | **`url`** (static or `required_inputs` wire), optional **`method`** (default `GET`), optional **`headers`** (JSON object of string values), optional **`timeout_ms`**, **`cache_policy`**: `default` \| `refresh` \| `bypass` | Server-side HTTP fetch; output is **`dictionary`** with **`status_code`**, **`final_url`**, **`headers`**, **`body`** (text), **`fetched_at`**, **`duration_ms`**, **`cached`**. On transport failure the step still succeeds with an **`error`** object `{ type, message, retryable }` instead of HTTP fields. Non-2xx HTTP responses are still **successful steps**; inspect **`status_code`**. See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md#fetch-url-skill-fetch_url). |
| `capture_url_snapshot` | **`url`**, optional **`full_page`**, optional **`viewport_width`** / **`viewport_height`**, **`wait_until`**: `load` \| `domcontentloaded` \| `networkidle`, optional **`timeout_ms`**, **`cache_policy`**: `default` \| `refresh` \| `bypass` | Headless Chromium (Playwright) **PNG screenshot** of the rendered page; output is **`dictionary`** with **`image`** (`artifact_id`, `mime_type`, `width`, `height`), **`final_url`**, **`captured_at`**, **`duration_ms`**, **`cached`**. Complements **`fetch_url`** for client-rendered or blocked content. No DOM/text extraction. See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md#url-snapshot-rendered-page--skill-capture_url_snapshot). |

**Explorer UI note (optional):** The runtime may attach a typed **output explorer** in run details. For **dictionary** outputs, built-in **Gmail** / **Calendar** / **fetch_url** / **`capture_url_snapshot`** views apply when the inner `data` **matches** those shapes. Otherwise use the normal **dictionary** row view.

---

## Nested workflow (`kind: "workflow"`)

| Field | Notes |
|-------|--------|
| `data.workflow_id` | UUID string of another saved workflow definition. |
| `expose_as_custom_skill` (on **WorkflowDefinition**, not on the node) | When `true`, the workflow appears in the editor **Custom Skills** palette (same `workflow` node shape). |

**Suggested usage:** Only when a real id is known. **Bundle export/import** (Workflow Editor **Export** / **Import**) transitively includes nested definitions and remaps **`workflow_id`** on import; legacy single-file `mind_weave_workflow_export` imports still require manual re-linking. **Custom Skills** entries are normal **Workflow** nodes; they differ only in how the palette is populated (`expose_as_custom_skill` on the child definition is preserved in bundles).

---

## Machine-readable manifest (same as above)

Single JSON list of allowed `(kind, type_string)` pairs for validators or LLM tooling.

```json
{
  "manifest_version": 1,
  "steps": [
    { "kind": "primitive", "primitive_type": "string" },
    { "kind": "primitive", "primitive_type": "list" },
    { "kind": "primitive", "primitive_type": "dictionary" },
    { "kind": "primitive", "primitive_type": "boolean" },
    { "kind": "primitive", "primitive_type": "int" },
    { "kind": "primitive", "primitive_type": "structure" },
    { "kind": "primitive", "primitive_type": "document" },
    { "kind": "skill", "skill_type": "simple_llm_call" },
    { "kind": "skill", "skill_type": "multimodal_llm" },
    { "kind": "skill", "skill_type": "text_to_speech" },
    { "kind": "skill", "skill_type": "transcribe_audio" },
    { "kind": "skill", "skill_type": "audio_file_input" },
    { "kind": "skill", "skill_type": "transcribe_file" },
    { "kind": "skill", "skill_type": "gmail_list_messages" },
    { "kind": "skill", "skill_type": "calendar_list_events" },
    { "kind": "skill", "skill_type": "google_docs_get_document" },
    { "kind": "skill", "skill_type": "fetch_url" },
    { "kind": "skill", "skill_type": "capture_url_snapshot" },
    { "kind": "utility", "utility_type": "list_to_string" },
    { "kind": "utility", "utility_type": "string_to_list" },
    { "kind": "utility", "utility_type": "prepend_text" },
    { "kind": "utility", "utility_type": "string_trunc" },
    { "kind": "utility", "utility_type": "len_from_list" },
    { "kind": "utility", "utility_type": "int_to_string" },
    { "kind": "utility", "utility_type": "list_item_by_index" },
    { "kind": "utility", "utility_type": "dictionary_value_by_key" },
    { "kind": "utility", "utility_type": "read_document_property" },
    { "kind": "utility", "utility_type": "load_document" },
    { "kind": "utility", "utility_type": "upsert_document" },
    { "kind": "utility", "utility_type": "parse_document_body" },
    { "kind": "utility", "utility_type": "html_parse_basic" },
    { "kind": "utility", "utility_type": "google_docs_parse_document" },
    { "kind": "utility", "utility_type": "write_object_to_document_body" },
    { "kind": "utility", "utility_type": "append_value_to_document" },
    { "kind": "utility", "utility_type": "validate_against_structure" },
    { "kind": "utility", "utility_type": "add_to_list" },
    { "kind": "utility", "utility_type": "add_ints" },
    { "kind": "utility", "utility_type": "add_days" },
    { "kind": "utility", "utility_type": "subtract_ints" },
    { "kind": "utility", "utility_type": "multiply_ints" },
    { "kind": "utility", "utility_type": "divide_ints" },
    { "kind": "utility", "utility_type": "modulo_ints" },
    { "kind": "utility", "utility_type": "min_ints" },
    { "kind": "utility", "utility_type": "max_ints" },
    { "kind": "control", "control_type": "basic_conditional" },
    { "kind": "control", "control_type": "is" },
    { "kind": "control", "control_type": "gt" },
    { "kind": "control", "control_type": "lt" },
    { "kind": "control", "control_type": "gte" },
    { "kind": "control", "control_type": "lte" },
    { "kind": "control", "control_type": "and" },
    { "kind": "control", "control_type": "or" },
    { "kind": "control", "control_type": "xor" },
    { "kind": "control", "control_type": "not" },
    { "kind": "control", "control_type": "between" },
    { "kind": "control", "control_type": "for_loop" },
    { "kind": "control", "control_type": "for_loop_end" },
    { "kind": "start" },
    { "kind": "stop" },
    { "kind": "workflow" }
  ]
}
```

---

*Schema: `mind_weave_workflow_export` graph, version 1. Instructions (JSON encoding and wiring) are above.*
