# Output Explorer UI (`details.output_explorer`)

## Forced outputs (output overrides)

When a run uses **`output_overrides`**, affected nodes skip execution and **`NodeRunResult.details.forced_output`** is set. **Last Run** / run logs still show the usual **`output`** and **`output_explorer`** (built from the injected output). The UI labels these steps as **Overridden** where applicable.

On the workflow **canvas**, nodes with an active session output override render an **Overridden** chip in a reserved **top inset** (see **`NODE_OUTPUT_OVERRIDE_BADGE_TOP_RESERVE_PX`** in [`frontend/src/components/workflow-editor/constants.ts`](../frontend/src/components/workflow-editor/constants.ts) and **`StyledNodeBase`** in [`frontend/src/components/workflow-editor/nodeTypes.tsx`](../frontend/src/components/workflow-editor/nodeTypes.tsx)) so the badge does not cover **`signal_out`** or other output handles.

## Purpose

Workflow nodes emit structured `output` for downstream steps. In the **workflow editor** (Explorer / Last run / Run logs), a raw **JSON tree** alone is hard to scan. **`details.output_explorer`** is a **versioned** summary that drives a **card-style shell** (header, optional capped rows, row actions) while keeping **`NodeRunResult.output`** unchanged.

- **Not** part of the downstream contract: other nodes should rely only on `NodeRunResult.output` / `output.data`.
- **Editor-oriented**: safe to evolve UI without breaking graph semantics.
- **Aligned with at-rest redaction**: persisted run logs redact sensitive keys in `output_data` and `details`. Explorer rows must be built **after** redaction when writing storage so displayed lines do not reveal more than the redacted JSON. Stream/API responses may use unredacted output for the same builders during the session (see [`WorkflowExecutor`](../backend/app/domain/workflow_executor/executor.py)).

### Deprecated: `details.skill_explorer`

Older runs may still have **`details.skill_explorer`** with the **same v1 shape**. The SPA reads **`output_explorer` first**, then falls back to **`skill_explorer`** (`parseEffectiveOutputExplorer` in [`frontend/src/api/types.ts`](../frontend/src/api/types.ts)). New runs only write **`output_explorer`**.

## Schema (version 1)

Top-level object stored at **`details.output_explorer`**:

| Field | Type | Description |
|-------|------|-------------|
| `version` | `1` | Bump only for breaking shape changes. |
| `kind` | string | Discriminator for the frontend (see registry below). |
| `summary` | object | `line` (short headline) and optional `detail_lines` (stats, counts). |
| `items` | array | Row models for the list (capped, see below); may be empty for scalar/generic shells. |
| `overflow_count` | number? | How many list rows exist beyond `items` (optional). |

### Row model (`items[]`)

Use **redaction-safe key names** only. Do **not** use keys such as `subject`, `snippet`, `summary`, `location`, `body`, `organizer`, etc., as **item field names**, because [`redact_prompt_like`](../backend/app/core/run_log_redaction.py) may redact those paths when serializing `details`.

| Field | Type | Description |
|-------|------|-------------|
| `index` | number | Index into the relevant array in `output` (messages, events, list `data`, etc.). |
| `row_state` | `"ok"` \| `"error"` | Gmail fetch errors use `"error"`. |
| `primary_line` | string | Main title line (for **dictionary_primitive**, the **key** name). |
| `secondary_line` | string | Subtitle (e.g. type, time range, from + date). |
| `teaser` | string | Optional short preview (truncated server-side). |
| `badges` | string[] | Small chips (labels, status). |
| `inferred_primitive` | string? | Optional: `string`, `int`, `boolean`, `list`, `dictionary`, `mixed`, `null`, `number` — used for list/dictionary row **Copy** and modal preview. |

Cap **`items`** length (currently **50** in [`output_explorer.py`](../backend/app/domain/workflow_executor/output_explorer.py)); set `overflow_count` when truncating.

### `kind` registry (current)

| `kind` | When |
|--------|------|
| `gmail_list_messages` | Gmail List Messages skill: curated message rows (from **`ListNodeOutput.data`** or legacy dictionary `messages` + `resultSizeEstimate`). |
| `calendar_list_events` | Dictionary skill output with `events` list. |
| `fetch_url` | **Fetch URL** skill: HTTP summary line and one row (URL / status or error type); body preview via **`teaser`** (not a forbidden item key). |
| `capture_url_snapshot` | **URL snapshot** skill: dimensions + final URL; detail line with **`/api/v1/url-snapshot-artifacts/{id}`** resource path; or error type row. |
| `list_primitive` | List node output (`kind: list`, `data` array). |
| `dictionary_primitive` | Plain dictionary node output (not Gmail/Calendar skill shape). |
| `string_primitive` | String node output. |
| `int_primitive` | Int node output. |
| `boolean_primitive` | Boolean node output. |
| `start_outputs` | **Start** node with non-empty `output.outputs` map — one row per output slot (insertion order); header **Copy** = pretty JSON for the whole map. |
| `generic` | Response, structure, stop, conditional, **`audio`** (Text-to-Speech), **Start** with empty `outputs`, and other outputs (summary-only shell). |

## Backend

- **Module**: [`app/domain/workflow_executor/output_explorer.py`](../backend/app/domain/workflow_executor/output_explorer.py) — `try_build_output_explorer`, `build_start_outputs_explorer`, `build_gmail_list_explorer`, `build_calendar_list_explorer`, `build_fetch_url_explorer`, `build_capture_url_snapshot_explorer`, `merge_details_with_output_explorer` (stream/client `details`), `attach_output_explorer_after_redact` (persisted `NodeRunLog.details`). For **`kind: "dictionary"`** payloads, **legacy Gmail** dispatch uses **`messages`** + **`resultSizeEstimate`**; for **`kind: "list"`**, when the array matches the **Gmail curated message** heuristic, the same **`gmail_list_messages`** explorer is used. **Calendar** list dispatch requires **`events`** items that look like **Google Calendar** event objects (e.g. **`summary`**, **`start`**, **`end`**, **`htmlLink`**, **`status`**, …), so a user dict with an unrelated **`events`** array still uses **`dictionary_primitive`**. **Fetch URL** and **`capture_url_snapshot`** are detected before **generic** dictionaries: Fetch uses **`status_code`**, **`fetched_at`**, etc.; URL snapshot uses **`image.artifact_id`**, **`captured_at`**, and **`final_url`** (or an **`error`** object with **`captured_at`**).
- **Executor**: [`WorkflowExecutor`](../backend/app/domain/workflow_executor/executor.py) merges explorer into `NodeRunResult.details` for synchronous and streamed runs, and attaches **post-redaction** explorer when writing **`NodeRunLog`**.
- **Run log API** (`GET .../workflow-definitions/{id}/runs/{run_id}/logs`): [`_serialize_run_logs`](../backend/app/api/v1/workflow_definitions.py) applies [`redact_prompt_like`](../backend/app/core/run_log_redaction.py) to the rest of `details`, then **re-attaches** `output_explorer` and deprecated `skill_explorer` unchanged. Otherwise the nested key **`summary`** inside `output_explorer` would be treated like user-facing “summary” content and replaced with `"[redacted]"`, breaking the v1 schema and the **Explore past runs** Replay output UI (live **Last Run** uses streamed `node_end` payloads and does not hit this serializer).

## Frontend

- **Types / parsers**: [`frontend/src/api/types.ts`](../frontend/src/api/types.ts) — `OutputExplorerV1`, `parseOutputExplorerV1`, `parseEffectiveOutputExplorer`.
- **Clipboard helpers**: [`frontend/src/domain/formatValueForPrimitiveClipboard.ts`](../frontend/src/domain/formatValueForPrimitiveClipboard.ts) — per-row **Copy** (`formatValueForPrimitiveClipboard`); for **list_primitive** / **dictionary_primitive** / **`start_outputs`**, **header Copy** copies the full list/array or object as pretty-printed JSON (`formatListOrDictionaryForClipboard`) for pasting into List / Dictionary inputs. Copy buttons use **`useCopyWithFeedback()`** so users see the app-wide **Copied to clipboard** toast (see [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)).
- **UI**: [`OutputExplorer.tsx`](../frontend/src/components/workflow-editor/OutputExplorer.tsx) — header + optional rows; optional **`headerClipboardText`** for scalars (e.g. per-field **Inputs**). Optional **`expandNoRowsDetail`**: the **header** (title + detail lines) is **clickable** and opens the same [`OutputExplorerDetailModal.tsx`](../frontend/src/components/workflow-editor/OutputExplorerDetailModal.tsx) as row clicks (**Preview** / **View raw**), using the given payload (long string teasers when **`items` is empty**; **Last Run Output** with list rows uses the **full** serialized `nodeOutput` on header click — **row** clicks stay **per-item**). **Gmail** and **Calendar** rows use structured previews (subject, body, when/where, links). **All other** rows (list/dictionary/**start_outputs** values, `generic` objects, scalars) use **Preview** for a **readable summary**: plain text for strings, large type for numbers/booleans, and **pretty-printed JSON** in a scrollable block for arrays/objects. **View raw** is always the **collapsible `JsonTreeView`** navigator (expand/collapse, same raw data). Helpers: [`OutputExplorerPrimitivePreview.tsx`](../frontend/src/components/workflow-editor/OutputExplorerPrimitivePreview.tsx).
- **Integration**: [`WorkflowEditor.tsx`](../frontend/src/components/workflow-editor/WorkflowEditor.tsx) — Last run + Run logs: when `parseEffectiveOutputExplorer(details)` succeeds, render [`OutputExplorer`](../frontend/src/components/workflow-editor/OutputExplorer.tsx) only; the **full** serialized node output is available via row/header **Preview** / **View raw** in [`OutputExplorerDetailModal.tsx`](../frontend/src/components/workflow-editor/OutputExplorerDetailModal.tsx). [`outputExplorerRunRowExtras.ts`](../frontend/src/domain/outputExplorerRunRowExtras.ts) supplies **`expandNoRowsDetail`**: for **empty `items`** it derives payload + optional header **Copy** from **`nodeOutput`** (primitives; **Stop** / **Response** string `text` when present); other **`generic`** shells (**document**, **structure**, **conditional**, etc.) use the **full** serialized `nodeOutput` on header click. When **`items` is non-empty**, header expand also uses the **full** `nodeOutput` so **Output** matches **Inputs**. **Skill diagnostics** order unchanged; see [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md). For **`kind: audio`** (Text-to-Speech), [`WorkflowRunLogsNodeResultsList.tsx`](../frontend/src/components/workflow-editor/WorkflowRunLogsNodeResultsList.tsx) renders an inline **`<audio>`** control and **Download** when **`audio_base64`** is present on the result (typical for the current **run_stream** session); when bytes were redacted in stored history, it shows a short re-run hint instead. For **capture_url_snapshot** success (`output.data.image.artifact_id`), [`WorkflowNodeRunOutputBody.tsx`](../frontend/src/components/workflow-editor/WorkflowNodeRunOutputBody.tsx) also renders [`UrlSnapshotArtifactPreview.tsx`](../frontend/src/components/workflow-editor/UrlSnapshotArtifactPreview.tsx) above the explorer card: it **fetch**es **`GET /api/v1/url-snapshot-artifacts/{id}`** with the session (not a raw `<img src=…>`) so the PNG is visible and **Download PNG** works across dev host/port combinations. **Click** the inline thumbnail to open a larger view in a modal using the same **backdrop / card / close** pattern as [`OutputExplorerDetailModal.tsx`](../frontend/src/components/workflow-editor/OutputExplorerDetailModal.tsx) (**Escape** or backdrop dismisses). Inside the modal, **Zoom** (− / +, **1:1** reset) and **Ctrl+scroll** (⌘+scroll on Mac) scale the image; the viewport scrolls to pan.

### Run inputs (Last Run / Run logs)

There is **no** separate `input_explorer` API field. **Inputs** reuse the merged object from [`lastRunInputsPayload.ts`](../frontend/src/components/workflow-editor/lastRunInputsPayload.ts) (`details.resolved_inputs` plus legacy top-level LLM keys). [`RunInputsExplorer.tsx`](../frontend/src/components/workflow-editor/RunInputsExplorer.tsx) renders **one [`OutputExplorer`](../frontend/src/components/workflow-editor/OutputExplorer.tsx) card per top-level key** (insertion order): each card’s explorer + synthetic `nodeOutput` are built client-side by [`clientOutputExplorerForInputField.ts`](../frontend/src/domain/clientOutputExplorerForInputField.ts) (list/dictionary/string/int/boolean shapes aligned with backend primitive explorers). Scalars use **`headerClipboardText`** for header **Copy** and **`expandNoRowsDetail`** so the card header opens the **Preview** / **View raw** modal for the **full** value (card detail lines may truncate long strings). Nested list/dict fields use the same row + header **Copy** behavior as node **Output**. Full values (including the merged map) are available via **Preview** / **View raw** on each card, consistent with **Output** (no separate raw JSON disclosure).

**Calendar times in the UI:** Event **`start`** / **`end`** in the list and modal **Preview** use **My Profile → Workflow time zone** (resolved IANA; **`system`** follows the browser). **View raw** still shows API-shaped strings on each event object.

## Adding a new `kind`

1. **Python**: Extend `try_build_output_explorer` (or add a dedicated builder and dispatch). Use caps and redaction-safe item keys.
2. **Tests**: Extend [`backend/tests/test_output_explorer.py`](../backend/tests/test_output_explorer.py) (happy path, overflow, redaction alignment).
3. **TypeScript**: Extend `OutputExplorerKind` in `types.ts` if you want strict typing; ensure `parseOutputExplorerV1` accepts the shape.
4. **UI**: Add icon / row behavior / modal preview branch in `OutputExplorer.tsx` and `OutputExplorerDetailModal.tsx` if the default tree preview is insufficient.
5. **Docs**: Register the `kind` in this file and in [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md).
