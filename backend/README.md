# Mind Weave Backend

This is the FastAPI backend for the Mind Weave project.

Architecture and cross-cutting conventions: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). It handles data persistence, workflow execution, persona management, and interacts with local LLM models via an OpenAI-compatible API (e.g., LM Studio).

## Architecture Overview

The backend is structured using Domain-Driven Design principles:

- **`app/api/v1/`** — FastAPI route definitions organized by resource:
  - `auth.py` — Login, register, `/me`, admin user management, Google OAuth association
  - `health.py` — Health check
  - `models.py` — Available LLM models from LM Studio
  - `personas.py` — Persona CRUD
  - `palettes.py` — Workflow palette CRUD + **`POST /validate`** + **`GET /resolve`**
  - `system_palettes.py` — App-wide system theme CRUD (semantic UI tokens)
  - `structures.py` — Structure CRUD
  - `documents.py` — Document CRUD plus `GET /{id}/metadata` (token / character / word / line counts via `tiktoken` `o200k_base`)
  - `workflow_definitions.py` — WorkflowDefinition CRUD, sync `POST /run`, enqueue `POST /runs`, per-run SSE `GET …/workflow-runs/{run_id}/events`, run listings + logs
  - `workflow_execution_limits.py` — `GET /workflow-execution-limits/` defaults + ceilings for editor/run validation
  - `workflow_run_events.py` — `GET …/workflow-runs/{run_id}` snapshot + `GET …/events` SSE replay/tail + live fan-out
  - `workflow_projects.py` — Workflow project folder CRUD (`GET/POST /` `PATCH/DELETE /{id}`); reserved **Shared** folder per user
- **`app/core/`** — Configuration (`config.py`), logging (`logging.py`), security (`security.py`)
- **`app/domain/`** — Pydantic models in **`schemas/`** (import via `from app.domain.schemas import ...`), domain **`services/`**, and workflow execution:
  - `schemas/` — Request/response and workflow graph models (`GraphNode`, outputs, workflow run DTOs, etc.)
  - `persona_service.py` — Persona CRUD, default persona seeding
  - `palette_service.py` — Palette CRUD, built-in palette seeding (`BUILTIN_WORKFLOW_PALETTES`)
  - `system_palette_service.py` — System palette CRUD, built-in theme seeding (`BUILTIN_SYSTEM_PALETTES`)
  - `structure_service.py` — Structure CRUD
  - `document_service.py` — Document CRUD
  - `document_metadata_service.py` — Estimated token / character / word / line counts for Document bodies (`tiktoken` `o200k_base`); surfaced via `GET /api/v1/documents/{id}/metadata` in the SPA's **Manage Documents → Metadata** tab
  - `workflow_definition_service.py` — WorkflowDefinition CRUD (list ordered by `updated_at` desc; `project_id` on create/update)
  - `workflow_project_service.py` — Workflow project folder CRUD; `ensure_shared_project`, `touch_project`
  - `workflow_executor/` — DAG validation and execution (`services/workflow_executor.py` re-exports `WorkflowExecutor`)
  - `palette_defaults.py` — **`DEFAULT_PALETTE_COLORS`** and built-in workflow preset definitions; SPA reads effective colors from **palette API** responses (manifest + parity tests—not a dual handwritten hex SSOT). See **`workflow_palette_resolve.py`** / **`workflow_palette_validate.py`**
  - `system_palette_defaults.py` — Built-in app-wide themes (`light`/`dark` token maps; mirror token keys in frontend `theme/defaults.ts`)
- **`app/persistence/`** — Database engine (`db.py`), table definitions (`tables.py`)
- **`app/providers/`** — LLM provider integrations (e.g. `lmstudio.py`). Chat completion **`usage`** from the OpenAI-compatible API is normalized to a **flat map of integers** (`openai_usage.normalize_openai_usage_for_provider`) so nested fields (e.g. `completion_tokens_details` from some local models) do not break `ProviderResponse` validation.
- **`app/prompting/`** — Default system personas (`personas.py`)

### Dates and timestamps

All persisted and server-generated instants are **UTC** and **timezone-aware**. Use [`utc_now()`](app/persistence/tables.py) (or `datetime.now(timezone.utc)`); do **not** use naive `datetime.utcnow()` or local `datetime.now()`. New DB columns that store a point in time should use `DateTime(timezone=True)`. Full rationale and rules: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#dates-and-timestamps-utc).

## Core Concepts

| Concept | Description |
|---------|-------------|
| **User** | Authenticated account. JWT-based auth (access tokens carry `typ: access`; refresh tokens carry `jti`). After a backend upgrade, stale browser sessions may need **sign-in again** if `/me` returns 401. First admin: run `uv run python -m app.cli create-admin --username admin --password '<strong password>'` after migrations, or set `BOOTSTRAP_DEFAULT_ADMIN=true` with `APP_ENV=local` only for a one-time `admin`/`admin` seed. |
| **Persona** | Named interface to a model: system prompt + optional default model. Types: `custom` or `system`. Required by Simple LLM Call and Multimodal LLM nodes. |
| **Palette** | Per-step hex overrides for workflow handles, edges, and node borders (**`colors`** JSON column). **`palette_handle`** keys and **`editor_label`** text are defined on [`shared/workflow_graph_step_kinds.json`](../shared/workflow_graph_step_kinds.json) plus **`palette_extras`**. Responses include **`entries`**, **`effective_colors`** (**override → family → code default → `any`**), and **`warnings`**. Writes validate CSS-like color strings and **reject unknown keys** (`422`). **`POST /api/v1/palettes/validate`** returns the enriched shape without persisting. **Built-in presets** (`user_id` NULL): stable **`slug`**, seeded from [`BUILTIN_WORKFLOW_PALETTES`](app/domain/palette_defaults.py). **`GET /api/v1/palettes/by-slug/{slug}`** fetches one by slug. **`GET /api/v1/palettes/resolve`** (optional **`workflow_id`**) returns the **effective** editor palette: **`palette_id`** on the workflow when set and visible → **`User.settings.preferred_editor_palette_id`** → **default**. |
| **SystemPalette** | App-wide semantic UI colors for light/dark mode. Table `system_palettes`; `colors` JSON has `light` and `dark` maps (tokens aligned with [`system_palette_defaults.py`](app/domain/system_palette_defaults.py) / frontend `theme/defaults.ts`). **Built-in** rows match workflow preset **names/slugs**; user themes are owned rows. Active theme: `User.settings.system_palette_id` (UUID). Optional `User.settings.system_colors` still merges as partial overrides in the SPA. |
| **Structure** | JSON schema for structured LLM outputs. Used by Simple LLM Call and Multimodal LLM when deterministic JSON is required. Stored as `json_schema` (valid JSON). |
| **Document** | Named persisted **body** text (globally unique **`name`**); Markdown, JSON, or other text. CRUD via `/api/v1/documents/`. Used by the **Document** primitive, **Read Document Property**, and runtime **load/upsert** utilities. |
| **WorkflowDefinition** | Named DAG stored as `graph: { nodes, edges }` plus optional **`execution_limits`** (same keys as the run payload’s **`execution_limits`**, merged under server ceilings — see **`GET /api/v1/workflow-execution-limits/`**). Nodes are Start, Stop, Primitives, Skills, Utilities, or Controls. Optional `palette_id` references a Palette for handle/edge colors. Optional `project_id` references a **WorkflowProject** folder (single-level; default **Shared**). Optional **`expose_as_custom_skill`** lists the workflow in the editor **Custom Skills** palette (same nested **`workflow`** graph node). List/get includes rows with `user_id` NULL (legacy); the first save assigns the current user as owner. |
| **WorkflowProject** | Per-user folder for organizing workflows. Unique **`name_lower`** per user; **`Shared`** is reserved and auto-created. Deleting a folder moves its workflows into **Shared**. |
| **Primitives** | Graph nodes that supply static data: String, List, Dictionary, Structure, Document (`DocumentPrimitiveNode`), Boolean (`BooleanPrimitiveNode`), Int (`IntPrimitiveNode`), Sandbox behavior (`SandboxBehaviorPrimitiveNode`), Decision action (`DecisionActionPrimitiveNode` — enum picker → string for `sandbox_decision_intent.action`). |
| **Skills** | **Simple LLM Call** (`SimpleLLMCallSkillNode`): `kind: "skill"`, `skill_type: "simple_llm_call"`. Requires a Persona (system prompt, model, creativity come from Persona). Three input handles: Add context (optional), User Prompt, and Structure (optional). When a Structure is provided (via selector or wired from Structure primitive), the LLM returns deterministic JSON (`DictionaryNodeOutput`); otherwise free-form text (`ResponseNodeOutput`). Run fails with a helpful error if no Persona is selected. Legacy persisted graphs may still use `kind: "utility"` + `utility_type: "simple_llm_call"`; the executor normalizes to the skill model at parse time. **Multimodal LLM** (`MultimodalLLMCallSkillNode`): `skill_type: "multimodal_llm"`. Same Persona/Structure/output shapes as Simple LLM Call, plus required **Images** input (list of `artifact_id` objects, or snapshot-shaped dict). Resolves user-owned `url_snapshot_artifacts` into OpenAI-style image parts; text-only models surface `MODEL_NOT_MULTIMODAL` via LM Studio errors. Optional per-node **`model`** overrides the Persona default. |
| **Utilities** | List to String: converts list input to string representation (JSON) for passing to prompts. String to List: parses JSON array text into a list. Prepend Text: prepends text to a target string; two inputs (target_string, text_to_prepend), optional "Add additional line" checkbox, output_string. **String Trunc** (`string_trunc`): target_string + start_index + end_index → substring (`output_string`); inclusive end, or `end_index == -1` through end. **Message:** one string input (`message`); surfaces text in run `details.user_message` and emits empty `StringNodeOutput` (no data output handle in the editor; signal-only). Len from List, List Item by Index: list utilities. Int to String: one int input → decimal string (`StringNodeOutput`). Dictionary Value by Key: key + dictionary → typed output per `output_value_type`; optional `fallback` wire or `data.fallback_value` when the key is missing or the value is null (wrong type at an existing key still errors; wire overrides static). Read Document Property: document + target_property → typed output per `output_value_type`. **HTML Parse (basic)** (`html_parse_basic`): one string input (`html`) → `DictionaryNodeOutput` with `title`, `text_blocks`, and `links` (structural parse; no main-content heuristics). **Document runtime:** Load Document, **Upsert Document** (persist string or JSON to a named document—e.g. save a full transcript with **`replace`**; append/merge_json for other flows), Parse Document Body, Write Object to Document Body, Append Value to Document, Validate Against Structure. **Int math** (Add, Subtract, Multiply, Divide, Modulo, Min, Max): two int inputs (`input_a`, `input_b`) → `IntNodeOutput`; divide/modulo error if `input_b == 0`. |
| **Controls** | Basic Conditional: condition → True or False branch. Is?: equality on two inputs → True or False branch. **Is Empty?** (`is_empty`): one list or dictionary input → True when `[]` or `{}`, else False. Gt / Lt / Gte / Lte: ordered comparison on two inputs → True or False branch. **Between**: three int inputs (`low`, `value`, `high`) → True when `low <= value <= high` (inclusive), else False; errors if `low > high`. And / Or / Xor: two boolean inputs → single boolean output (for wiring; no branching outputs). **Not**: one boolean input → inverted boolean (no branching). **For Loop** / **For Loop End**: iterate a list (**`iteration_mode`**: sequential, parallel — legacy **`parallel_iterations`**, batched **`batch_size`**) with optional **`continue_on_error`**, **`max_iterations`**, **`summary`** output. **Try / Catch** (`try_catch`): **`try`** and **`catch`** regions with dictionary **`output`/`envelope`** and optional **`value`** binding from inside **`try`**. Only downstream nodes on the active branch execute for branching controls. |
| **Graph nodes** | Start, Stop, StringPrimitive, ListPrimitive, DictionaryPrimitive, StructurePrimitiveNode, DocumentPrimitiveNode, BooleanPrimitiveNode, IntPrimitiveNode, SandboxBehaviorPrimitiveNode, DecisionActionPrimitiveNode, SimpleLLMCallSkillNode, MultimodalLLMCallSkillNode, ListToStringUtilityNode, StringToListUtilityNode, PrependTextUtilityNode, StringTruncUtilityNode, MessageUtilityNode, LenFromListUtilityNode, IntToStringUtilityNode, ListItemByIndexUtilityNode, DictionaryValueByKeyUtilityNode, ReadDocumentPropertyUtilityNode, LoadDocumentUtilityNode, UpsertDocumentUtilityNode, ParseDocumentBodyUtilityNode, HtmlParseBasicUtilityNode, WriteObjectToDocumentBodyUtilityNode, AppendValueToDocumentUtilityNode, ValidateAgainstStructureUtilityNode, AddToListUtilityNode, AddIntsUtilityNode, SubtractIntsUtilityNode, MultiplyIntsUtilityNode, DivideIntsUtilityNode, ModuloIntsUtilityNode, MinIntsUtilityNode, MaxIntsUtilityNode, BasicConditionalControlNode, IsControlNode, IsEmptyControlNode, GtControlNode, LtControlNode, GteControlNode, LteControlNode, AndControlNode, OrControlNode, XorControlNode, NotControlNode, BetweenControlNode, ForLoopControlNode, ForLoopEndControlNode, TryCatchControlNode, WorkflowRefNode. |

### Adding a New Skill

When adding a skill node (external or LLM-backed), follow the same structural steps as a utility, but use **`kind: "skill"`** and **`skill_type`** (e.g. `simple_llm_call`, `multimodal_llm`). Register the row in [`shared/workflow_graph_step_kinds.json`](../shared/workflow_graph_step_kinds.json), extend `_parse_node` and the executor dispatch, add the **Skills** palette entry in the editor (see [frontend README](../frontend/README.md)), and add tests. For persisted graph renames, ship an Alembic data migration on `workflow_definitions.graph`.

### Adding a New Utility

When extending the codebase with a new utility node, follow these steps:

1. **Domain schemas** (`app/domain/schemas/`): Define `XxxUtilityNode` with `kind: "utility"`, `utility_type: "xxx"`, add to `GraphNode` union in `graph_nodes.py` and export from `schemas/__init__.py`
2. **Workflow executor** (`app/domain/workflow_executor/`): Parse in `parsing.py` `_parse_node()`, dispatch in `executor.py` `_execute_node()`, implement `_resolve_xxx_node()`. Use `inputs.py` `_resolve_inputs_by_target_handle()` for multi-input utilities (Upsert Document alone passes **`implicit_null_target_wire_string_keys`** so legacy **`target_handle`**-null wires still populate **`name`** / **`content`**)
3. **Palette**: Add **`palette_handle`** / **`editor_label`** to [`shared/workflow_graph_step_kinds.json`](../shared/workflow_graph_step_kinds.json) (or **`palette_extras`**), add default hex to [`app/domain/palette_defaults.py`](app/domain/palette_defaults.py) (`DEFAULT_PALETTE_COLORS`); SPA picks up **`effective_colors`** via the API — extend [`frontend/src/domain/paletteDefaults.ts`](../frontend/src/domain/paletteDefaults.ts) only for new **family** routing or offline stubs; regenerate palette OpenAPI subset types from **`frontend/`** with **`npm run codegen:palette-types`**. Optionally Alembic to backfill the new key into existing DB rows if presets must ship it non-sparse on disk.
4. **Tests**: Add executor tests in `test_workflow_executor.py` (mock LLM/external calls); update `test_api.py` palette payloads
5. **Documentation**: Update Utilities row, Graph nodes table, Palette types in this README

### Adding a New Control

When extending the codebase with a new control node (e.g. Basic Conditional), follow the same steps as Adding a New Utility, but use `kind: "control"` and `control_type` (e.g. `basic_conditional`). Control nodes that branch require executor changes: in `_build_in_degree_and_adjacency`, cap in_degree for merge nodes (nodes with incoming edges from both branches); in the run loop, only activate successors on the matching branch when a conditional completes.

### Start Node Required Inputs

The Start node defines **required inputs** (configurable in the Workflow Editor). The default is **no required inputs** (`required_inputs: []`); add inputs via the inspector when you need user-provided values. Each input has a `key` (handle ID for wiring), `type` (`string`, `list`, `dictionary`, `boolean`, or `int`), and nullable `value`. If `value` is null when the workflow runs, the caller must supply it via `input_overrides` in the run request body, or the run will fail. Edges from Start use `source_handle` to select which output slot connects to downstream nodes. When there are no required inputs, a single output handle `output` emits an empty string. Legacy Start nodes with `data.text` (and no `required_inputs`) are supported; they are treated as a single string input (key `user_input`).

### Stop Node Required Output

The Stop node defines exactly one **required output** (`data.required_outputs`) — the expected type the workflow returns. Default: `[{ key: "output", type: "string" }]`. Edit the output key and type via the inspector. The input handle is colored by the assigned type. Workflow nodes that reference this workflow use this output to render their output handles and edge colors.

### Workflow Node

A **Workflow** node (`kind: "workflow"`) executes a referenced sub-workflow. It has `data.workflow_id` (UUID of the sub-workflow). Inputs are passed via parent edges: `target_handle` maps to the sub-workflow's Start node inputs (e.g. `user_input`). Output handles are derived from the sub-workflow's Stop node `required_outputs` — one handle per output with the correct key and type-based coloring. Edges from the Workflow node use `source_handle` to select which output slot connects. Self-reference and cycles (A→B→A) are rejected at run time.

## Workflow Execution Model

The `WorkflowExecutor` runs a WorkflowDefinition DAG:

1. **Validate** — Detect cycles (Kahn's algorithm) on the **scheduling DAG**. Edges whose **target** is **`TryCatchControlNode`** with **`target_handle: value`** are omitted from that pass so producer → **`value`** feedback does not falsely report a cycle (`executor.py`: `_edges_for_global_cycle_detection`).
2. **Topologically sort** — Determine execution order.
3. **Execute nodes in level-based batches** — Nodes whose dependencies are satisfied run concurrently via `asyncio.gather`. Primitives and non-LLM utilities resolve immediately (no LLM call). **Simple LLM Call** skill nodes require a Persona; they call the LLM with system prompt from Persona + optional additional context (from inspector or upstream), and user prompt (from required_inputs, upstream edges, or input_overrides). When a Structure is provided (via `structure_id` or wired from Structure primitive), the request includes LM Studio's `response_format` and the response is returned as `DictionaryNodeOutput`; otherwise as `ResponseNodeOutput`.
4. **Parallel siblings** — Nodes sharing the same source (e.g., three LLM calls fanning out from one upstream node) execute simultaneously. This enables concurrent LLM requests to LM Studio, which supports multiple simultaneous requests when configured (e.g., 4 threads). A failing sibling is recorded but does not halt its peers.

**Session concurrency** — `WorkflowExecutor` uses one `Session` per HTTP request. Parallel node tasks must not access that session unsynchronized; LM Studio token and `User.api_keys` reads for **Simple LLM Call** run under an internal async lock (see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — *Workflow executor Session concurrency*). If the in-app LLM path misbehaves while the [`inspect_user_lmstudio_key.py`](scripts/inspect_user_lmstudio_key.py) probe succeeds, suspect this layer rather than encryption.

**Offline loop wiring check** — From `backend/`, `uv run python scripts/analyze_workflow_definition.py --workflow-id <uuid>` loads the persisted graph and runs the same **For Loop** / **For Loop End** validators as the executor. **`--edges`** lists persisted handles per edge. See [docs/OPERATIONS.md](../docs/OPERATIONS.md#debugging-workflows-graphs-and-runs).

**URL snapshot skill (`capture_url_snapshot`) — Playwright** — The skill runs **headless Chromium inside the API process** via **Playwright**. The Python package is an **optional extra**: from `backend/`, run **`uv sync --extra url-snapshot`** (alongside **`--extra dev`** if you use pytest/mypy) so **`playwright`** is installed, then **`uv run playwright install chromium`** once per machine or container image. Without the extra, runs that reach this node return a structured **`PLAYWRIGHT_MISSING`** error with install hints. Full timeouts, PNG size caps, and operator notes: [docs/OPERATIONS.md](../docs/OPERATIONS.md#capture_url_snapshot--playwright).

**Stream a run locally (no HTTP)** — `cd backend && uv run python scripts/run_workflow_stream.py --workflow-id <uuid>` executes **`WorkflowExecutor.execute_scheduled_run`** against a persisted **`WorkflowRun`** row and prints **legacy-compatible NDJSON lines** (stdout) analogous to [`workflow_sse_ndjson_compat.py`](app/domain/workflow_sse_ndjson_compat.py). **`chdir`** to `backend/` before loading **`app`** so **`.env`** / SQLite match **`uvicorn`**. Logs **`LMSTUDIO_BASE_URL`** + **`DATABASE_URL`** to stderr. Optional **`--input-json`** for **`input_overrides`** / **`output_overrides`**.

**books.toscrape.com sample (`fetch_url` + `html_parse_basic`)** — `cd backend && uv run python scripts/run_books_toscrape_fetch_parse_sample.py` runs that graph once with a real fetch and prints the parse result (see [docs/OPERATIONS.md](../docs/OPERATIONS.md)). **`--cleanup`** drops the created rows after the run.

**`multimodal_llm` sample (seeded PNG + mocked LM by default)** — `cd backend && uv run python scripts/run_multimodal_llm_sample.py` inserts a tiny **`url_snapshot_artifacts`** row and a **List + String → Multimodal LLM → Stop** graph, then runs **`WorkflowExecutor`** once. Default path **mocks** `LMStudioProvider` (no LM HTTP). **`--real-llm`** uses your **`LMSTUDIO_BASE_URL`** with a vision-capable model; **`--cleanup`** deletes the temporary user, artifact, and workflow. See [docs/OPERATIONS.md](../docs/OPERATIONS.md).

**Upsert Document HTTP e2e (synthetic graphs + persisted `document.body`)** — `cd backend && uv run python scripts/run_upsert_document_http_e2e.py` boots a temporary **uvicorn**, **`POST …/workflow-definitions/`** + **`POST …/run`** (**`target_handle: "name"`** mis-wire + explicit **`content`** + alias **`output`**), **`GET …/documents/{id}`** assert **`body`**. No LM; see [docs/OPERATIONS.md](../docs/OPERATIONS.md).

**SPA parity — persisted workflow + Build SSE** — `cd backend && uv run python scripts/run_persisted_workflow_stream_http_e2e.py --workflow-id <uuid>` **GET**s the definition, **POST**s **`/runs`**, then consumes **`GET /api/v1/workflow-runs/{run_id}/events`** (SSE mapped back to NDJSON-era event dicts inside the helper). Optional **`--assert-upsert-body-non-empty`**. Pair with **`uv run python scripts/analyze_workflow_definition.py --workflow-id <same-uuid> --summarize`**.

**Image primitive (optional real LM Studio)** — `RUN_IMAGE_E2E=1 uv run pytest tests/test_image_primitive_workflow_e2e_optional.py` exercises **Image** → **Multimodal LLM** without mocking the provider (skips unless env and LM are up). See [docs/OPERATIONS.md](../docs/OPERATIONS.md).

**HTTP Build SSE timing** — `POST …/runs` returns immediately while execution continues on an asyncio task. `GET …/workflow-runs/{run_id}/events` streams SSE from an in-memory fan-out registry plus DB replay for disconnects (`workflow_run_events.py`). Keep nginx **`proxy_buffering off`** (`X-Accel-Buffering: no` already set) so comment keepalive and JSON chunks reach browsers promptly.

**Voice input (transcribe) in-process, no browser** — `cd backend && uv run python scripts/run_voice_input_workflow_e2e.py` inserts a **Start → Voice input → Stop** workflow, runs **`execute_scheduled_run`**, and calls **`complete_transcribe_wait`** (same handshake as **`POST .../transcribe-audio`** during a persisted Build/SSE run). Defaults **mock** STT and use a placeholder WAV; pass **`--real-stt`** (often with **`--audio tts`**) for full bridge coverage. Docstring pointers: [docs/WORKFLOW_SKILLS.md](../docs/WORKFLOW_SKILLS.md#voice-input-transcribe--skill-transcribe_audio).

**Transcribe File (provider-abstracted) in-process, no browser** — `cd backend && uv run python scripts/run_transcribe_file_workflow_e2e.py` exercises both providers (`local_whisper` + `assemblyai`) and both source modes (saved artifact + runtime upload via `complete_transcribe_wait`). Defaults mock STT and AssemblyAI so no external calls fire. Pass `--real-stt --audio-file …` or `--real-assemblyai --assemblyai-key … --audio-file …` for live bridges. The HTTP twin `scripts/run_transcribe_file_workflow_http_e2e.py` boots a local FastAPI instance, walks both providers via **`POST /runs`** + **`GET /api/v1/workflow-runs/{run_id}/events`**, and asserts **`GET …/events`** replay after intentionally dropping the first reader. Docstrings + [docs/WORKFLOW_SKILLS.md](../docs/WORKFLOW_SKILLS.md#transcribe-file-provider-abstracted--skill-transcribe_file).

**Inspect decrypted LM Studio key (debug)** — `cd backend && uv run python scripts/inspect_user_lmstudio_key.py --username <name>` prints **`decrypt_api_keys_store`** output for **`lmstudio_api_key`** and **`resolve_lmstudio_bearer()`** (per-user + env, same as **chat**). Optional **`--compare-to '<token>'`** exits **1** on mismatch; **`--probe-lm-studio`** **`GET`**s **`{LMSTUDIO_BASE_URL}/models`** with that resolved Bearer (not the same token as **`GET /api/v1/models/`**, which uses **`LMSTUDIO_API_KEY`** only). **Never** use in production or commit tokens. For in-process chat logging of the token, set **`MW_DEBUG_LOG_LM_BEARER=1`** (dev only; logs the raw Bearer secret).

**Public site / nginx upstream checklist** — On the machine that terminates TLS, run [`scripts/diagnose_edge_connectivity.sh`](scripts/diagnose_edge_connectivity.sh) from `backend/` (optional env: `PUBLIC_APP_URL`, `APP_HOST`, `API_HOST`). It prints listening ports, local hits to **8000** / **5173**, optional SNI curls, and pointers to nginx error logs. Use it when browsers time out on `https://app…` to separate “nothing on :443” from “nginx waiting on upstream.”

## API Reference

| Method | Endpoint | Description |
|--------|----------|--------------|
| GET | `/api/v1/health` | Public liveness check |
| GET | `/api/v1/health/ready` | Readiness (requires auth; verifies DB connectivity) |
| POST | `/api/v1/auth/login` | Login (form: username, password); sets HttpOnly auth cookies |
| POST | `/api/v1/auth/register` | Register (disabled when `OPEN_REGISTRATION=false`); sets cookies |
| POST | `/api/v1/auth/refresh` | Rotate access + refresh cookies from refresh cookie |
| POST | `/api/v1/auth/logout` | Clear auth cookies |
| GET | `/api/v1/auth/me` | Current user (requires auth; `api_keys` values are masked as `[stored]`) |
| PUT | `/api/v1/auth/me` | Update current user (requires auth). Body: `{ "settings": {...}, "api_keys": {...} }`. Allow-listed `settings` keys include `avatar_url`, `system_colors`, **`system_palette_id`**, **`theme_mode`** (`light` / `dark` / `system`), **`preferred_editor_palette_id`** (UUID or `null`), **`workflow_execution_limits_prefs`** (optional sparse object `{ workflow_ttl_seconds?, max_node_executions?, max_loop_iterations?, max_nested_depth? }` — each **`>= 1`**, capped by **`WORKFLOW_EXECUTION_*_CEILING_*`** env; empty object clears), and **`max_concurrent_lm_studio_calls`**. Full object replaces stored `settings` for that PUT. |
| GET | `/api/v1/auth/google/login` | Start Google OAuth login flow, redirects to Google (no auth) |
| POST | `/api/v1/auth/google/authorize` | Start Google OAuth association flow, returns redirect_url (requires auth) |
| GET | `/api/v1/auth/google/callback` | Google OAuth callback: login redirects to frontend with `#google_session=` one-time code (fragment); association uses query params only |
| POST | `/api/v1/auth/google/session` | Exchange `google_session` code for auth cookies (after login callback) |
| POST | `/api/v1/auth/google/disassociate` | Remove Google account association for current user (requires auth) |
| POST | `/api/v1/auth/users/{user_id}/google/disassociate` | Remove Google association for a user (admin only) |
| GET | `/api/v1/auth/users` | List users (admin only) |
| POST | `/api/v1/auth/users` | Create user (admin only) |
| PUT | `/api/v1/auth/users/{user_id}` | Update user (admin only): `username`, `password`, `is_admin`. Cannot remove admin from the last remaining admin (400). |
| DELETE | `/api/v1/auth/users/{user_id}` | Delete user (admin only) |
| GET | `/api/v1/models/` | LM Studio model ids for pickers (requires auth; uses **`LMSTUDIO_API_KEY`** only; response may include **`lm_studio_list_error`**) |
| GET | `/api/v1/personas/` | List personas |
| POST | `/api/v1/personas/` | Create persona |
| GET | `/api/v1/personas/{id}` | Get persona |
| PUT | `/api/v1/personas/{id}` | Update persona |
| DELETE | `/api/v1/personas/{id}` | Delete persona |
| GET | `/api/v1/palettes/` | List palettes |
| GET | `/api/v1/palettes/resolve` | Effective editor palette (**`workflow_id`** optional query) |
| POST | `/api/v1/palettes/` | Create palette |
| POST | `/api/v1/palettes/validate` | Validate **`name`** + **`colors`** (returns **`entries`** / **`warnings`** without persisting) |
| GET | `/api/v1/palettes/by-slug/{slug}` | Get built-in workflow palette by slug |
| GET | `/api/v1/palettes/{id}` | Get palette |
| PUT | `/api/v1/palettes/{id}` | Update palette |
| DELETE | `/api/v1/palettes/{id}` | Delete palette |
| GET | `/api/v1/system-palettes/` | List system themes (built-in + yours) |
| POST | `/api/v1/system-palettes/` | Create user-owned system theme |
| GET | `/api/v1/system-palettes/by-slug/{slug}` | Get built-in system theme by slug |
| GET | `/api/v1/system-palettes/{id}` | Get system theme |
| PUT | `/api/v1/system-palettes/{id}` | Update user-owned system theme |
| DELETE | `/api/v1/system-palettes/{id}` | Delete user-owned system theme |
| GET | `/api/v1/structures/` | List structures |
| POST | `/api/v1/structures/` | Create structure |
| GET | `/api/v1/structures/{id}` | Get structure |
| PUT | `/api/v1/structures/{id}` | Update structure |
| DELETE | `/api/v1/structures/{id}` | Delete structure |
| GET | `/api/v1/workflow-execution-limits/` | Effective **workflow execution limits**: **defaults**, **ceilings**, and **`max_loop_batch_size`** for editor validation (`config.py`). |
| POST | `/api/v1/documents/` | Create document |
| GET | `/api/v1/documents/{id}` | Get document |
| PUT | `/api/v1/documents/{id}` | Update document |
| DELETE | `/api/v1/documents/{id}` | Delete document |
| GET | `/api/v1/workflow-definitions/` | List workflows |
| POST | `/api/v1/workflow-definitions/` | Create workflow |
| GET | `/api/v1/workflow-definitions/{id}` | Get workflow |
| PUT | `/api/v1/workflow-definitions/{id}` | Update workflow |
| DELETE | `/api/v1/workflow-definitions/{id}` | Delete workflow |
| POST | `/api/v1/workflow-definitions/{id}/run` | Execute workflow (returns result). Optional body keys: **`input_overrides`** (required inputs that are null); **`output_overrides`** (force per-node outputs); **`execution_time_zone`** (IANA); **`execution_limits`** (**`workflow_ttl_seconds`**, **`max_node_executions`**, **`max_loop_iterations`**, **`max_nested_depth`**) constrained to deployment ceilings — **422** when above ceiling). **`acknowledge_preflight_warnings`** (**bool**) opts into runs that passed advisory static budget checks (see preflight below). |
| POST | `/api/v1/workflow-definitions/{id}/runs` | Enqueue persisted Build run (**`queued`** immediately). Same optional **`WorkflowRunRequest`** fields as **`/run`**. Consume lifecycle on **`GET /api/v1/workflow-runs/{run_id}/events`**. **Preflight** — Before enqueue/execute, the server estimates a conservative upper bound on node-step count (For Loops, list primitives, **`max_loop_iterations`**). **422** with **`error: preflight_blocked`** when the bound **clearly** exceeds **`max_node_executions`** with no ambiguous inputs. **422** with **`error: preflight_warnings`** when the bound may exceed limits but list sizes or nested workflows were uncertain; retry with **`acknowledge_preflight_warnings: true`** after user confirmation. |
| GET | `/api/v1/workflow-runs/{run_id}` | Poll snapshot (**`status`**, timestamps, **`last_event_seq`**). |
| GET | `/api/v1/workflow-runs/{run_id}/events` | Server-Sent Events (SSE): replay + tail for `workflow.*`, `node.*`, `input_required`, **`transcription_job_status`**, keepalive comments. |
| POST | `/api/v1/workflow-runs/{run_id}/cancel` | Request cancellation of an in-flight run (**204**). Emits **`workflow.canceled`** on SSE and persists **`canceled`**. |
| GET | `/api/v1/me/workflow-runs` | List workflow runs **you started** on **your** workflows (Explore UI) |
| GET | `/api/v1/workflow-definitions/{id}/runs` | List runs for a workflow (only runs **you started**) |
| GET | `/api/v1/workflow-definitions/{id}/runs/{run_id}/logs` | Get node run logs for a run (prompt-like fields in JSON redacted; only if **you started** the run) |
| DELETE | `/api/v1/workflow-definitions/{id}/runs/{run_id}` | Delete a run and its node logs (only if **you started** the run) |

## One-command local dev (`make dev`)

From the repository root **`make dev`** runs **`./startdev.sh`,** which launches **FastAPI** (`--host 0.0.0.0 --port 8000`) and **`npm run dev:lan`** together. It exports **`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, **`FRONTEND_URL`**, and **`VITE_API_BASE`** for that session **without overwriting** **`backend/.env`**. Prerequisites: synced **`backend/.venv`** and **`frontend/node_modules`**. Troubleshooting matches **[docs/OPERATIONS.md — Local development troubleshooting](../docs/OPERATIONS.md#local-development-troubleshooting)**; Google OAuth nuances on LAN stay in **[docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md)**.

Use **Setup & Running** below when you **only** need this API process (custom ports, debuggers).

## Setup & Running

If you prefer to stay at the **repository root**, use `uv --project backend …` (e.g. `uv sync --project backend --extra dev` or `uv sync --project backend --extra dev --extra url-snapshot`) instead of `cd backend` — there is no `pyproject.toml` at the repo root.

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Install or sync dependencies (the project uses `uv`):
   ```bash
   uv sync --extra dev
   ```
   Use **`--extra url-snapshot`** as well if you run workflows that include the **URL snapshot** skill (`capture_url_snapshot`); see **URL snapshot skill** under [Workflow execution model](#workflow-execution-model). Default **`uv sync --extra dev`** omits Playwright so API installs stay lighter.
3. **Convention — local dev server:** always start the API with **`uv` invoking this project’s Python**, then **`python -m fastapi`** (so dependencies come from **`backend/.venv`**, not another tool on your `PATH`):

   ```bash
   uv run python -m fastapi dev app/main.py
   ```

   Same interpreter, without `uv run` (after `uv sync` created `.venv`):

   ```bash
   ./.venv/bin/python -m fastapi dev app/main.py
   ```

   **Avoid** `fastapi dev app/main.py` alone — your shell may resolve `fastapi` to a **different** Python (pipx, another repo) → `ModuleNotFoundError` for packages installed only here.

   **Avoid** `uv run fastapi dev …` — on machines with several uv projects, `uv` may run the **FastAPI CLI** from another environment. **`uv run python -m fastapi …`** ties the CLI to **this** `pyproject.toml`.

   **Alternative** (ASGI only, no FastAPI CLI features):
   ```bash
   uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Same-network (LAN) access

**Automated LAN alignment:** Prefer **`make dev`** from repo root (**[One-command local dev (`make dev`)](#one-command-local-dev-make-dev)**) unless you intentionally split processes or tweak `.env` by hand—it injects **`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, and **`FRONTEND_URL`** for localhost **and** detected LAN IPs.

**Manual LAN:** Listen on **`--host 0.0.0.0`** and align **`backend/.env`** (**`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, **`FRONTEND_URL`** with **JSON list** syntax for host allowlists — see [`.env.example`](.env.example) and [Environment Variables](#environment-variables)).

Full step-by-step order (find your IP, set backend and frontend env, start API and Vite): **[frontend/README.md — LAN / same-network devices](../frontend/README.md#lan--same-network-devices)**.

**Google OAuth from phones or non-localhost browsers** requires a **public HTTPS hostname** (or a tunnel)—not a LAN IP. See **[docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md)**.

### Tests

For a **capability matrix** (core behavior → tests), see [docs/Audits/TEST_AUDIT.md](../docs/Audits/TEST_AUDIT.md).

**Palette OpenAPI subset (drift check)** — Palette response models feed [`backend/scripts/dump_openapi_palette_subset.py`](scripts/dump_openapi_palette_subset.py). From repo root → **`frontend/`**: run **`npm run codegen:palette-types`** (writes **`openapi.palette.json`** + **`src/generated/palette-types.ts`**). **`npm run verify:palette-types`** fails if regenerated files drift from HEAD.

Install dev tools (includes `pytest-cov`) and run the suite:

```bash
uv sync --extra dev
uv run pytest
```

**Lint / format (Ruff):** import order, unused imports, Pyflakes, and selected pycodestyle rules (`E501` line length ignored for now).

```bash
uv sync --extra dev
uv run ruff check app tests
uv run ruff format app tests
```

**Types (mypy):** static checking for `app/` with the Pydantic plugin. Tests are not type-checked by default (`tests.*` has `ignore_errors` in `pyproject.toml`).

```bash
uv sync --extra dev
uv run mypy app
```

Optional **coverage** for `app/` (summary only; nothing fails the run—we do **not** treat coverage % as a quality gate):

```bash
uv run pytest --cov=app --cov-report=term-missing:skip-covered
```

Settings live in `pyproject.toml` under `[tool.coverage.*]`. Prefer the [test audit](../docs/Audits/TEST_AUDIT.md) for “what must not break”; only add `--cov-fail-under` in an automated pipeline if you explicitly want to enforce a minimum later.

### Important Notes on Authentication

There is **no** default administrator account unless you explicitly opt in for local development:

1. **Recommended:** After the first server start (migrations applied), create an admin:
   ```bash
   uv run python -m app.cli create-admin --username admin --password 'your-secure-password'
   ```
2. **Optional (local only):** Set `BOOTSTRAP_DEFAULT_ADMIN=true` with `APP_ENV=local` to auto-create `admin` / `admin` when the user table is empty. Never enable this in production.

**`SECRET_KEY`:** In `APP_ENV=local`, use at least 16 characters. For any other `APP_ENV`, use a random value of at least 32 characters; the development placeholder string is rejected outside `local`.

**Upgrades:** JWT claim rules and what to do when users or Bearer clients see 401 after a deploy are documented in [`docs/OPERATIONS.md`](../docs/OPERATIONS.md); release bullets live in [`CHANGELOG.md`](../CHANGELOG.md).

## Troubleshooting

### `GET /api/v1/auth/google/login` returns 404 while `/api/v1/health` returns 200

The running process is almost always **stale code**: an old **`uvicorn`** (or another tool) was left on port **8000** after pulling changes that added Google OAuth routes, so the live app’s OpenAPI omits `/api/v1/auth/google/*` even though health still works.

**Fix:** Stop whatever listens on **8000** (see `lsof -nP -iTCP:8000 -sTCP:LISTEN`), then start the API again from **`backend/`** with **`uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`** (or **`uv run python -m fastapi dev app/main.py`** per [Setup & Running](#setup--running)). Avoid running **two** servers bound to the same port without stopping the first.

**Verify:** After restart, `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/auth/google/login` should be **302** or **307** (redirect), not **404**. With `APP_ENV=local`, `GET /openapi.json` should list paths containing `google` under `/api/v1/auth/`.

Reverse-proxy misconfiguration (nginx `proxy_pass` stripping `/api/v1`) is a separate issue—see [docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md).

### “Invalid host header” (browser or `login.txt` on `/api/v1/auth/google/login`)

**TrustedHostMiddleware** only allows `Host` values listed in **`TRUSTED_HOSTS`**. When nginx proxies **`https://api.yourdomain.tld`** to uvicorn, the **`Host`** header is **`api.yourdomain.tld`** (not `127.0.0.1`). If that hostname is missing from **`TRUSTED_HOSTS`**, Starlette responds with **400** and the plain text **`Invalid host header`** — browsers may offer to save it as **`login.txt`** because the path ends in `login`.

**Fix:** In **`backend/.env`**, add the **API** hostname to the JSON list, e.g. `TRUSTED_HOSTS=["localhost","127.0.0.1","testserver","api.yourdomain.tld"]`. Restart the API. See [docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md) and [docs/examples/env/domain.env.example](../docs/examples/env/domain.env.example).

### **502 Bad Gateway** from nginx on `https://api.…` (e.g. Google login)

[docs/examples/nginx/mind-weave.conf.example](../docs/examples/nginx/mind-weave.conf.example) proxies to **`http://127.0.0.1:8000`**. The API **must** accept connections on that address. If you start uvicorn / FastAPI with **`--host 10.x.x.x`** (LAN IP only), nothing listens on **`127.0.0.1:8000`**, nginx cannot connect → **502**.

**Fix:** Start the API with **`--host 127.0.0.1`** (matches nginx) or **`--host 0.0.0.0`** (listens on all interfaces, including loopback). Example:

```bash
cd backend && uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Verify:** `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/health` → **200** before testing HTTPS.

## Security notes (operational)

- **Living audit**: Open security findings only (no historical “fixed” list) live in [`docs/Audits/SECURITY_AUDIT.md`](../docs/Audits/SECURITY_AUDIT.md) (repo root).
- **TLS**: For production, terminate TLS at a reverse proxy (nginx, Traefik, Caddy, etc.) in front of the API; set `SECURITY_ENABLE_HSTS=true` only when all traffic is HTTPS.
- **Cookies**: Access/refresh tokens are HttpOnly cookies (`SameSite=lax`). The frontend must call the API with `credentials: include` and list the API origin under `CORS_ORIGINS`.
- **Secrets**: Use a strong `SECRET_KEY`; never commit real `.env` files. Run dependency checks periodically, e.g. `uv run pip install pip-audit && pip-audit` (or GitHub Dependabot).
- **SQLite**: Default SQLite is fine for single-tenant/local use; for multi-user production prefer PostgreSQL, filesystem permissions on the DB file, and backups.
- **Prompt injection**: Simple LLM Call sends Persona + optional additional context in **system**, plus one short fixed sentence about workflow-sourced user text; **user** is the resolved user prompt only. Treat model output as untrusted. See `app/domain/workflow_executor/executor.py` (`_run_simple_llm_call_node`).
- **Provider API keys (`api_keys` on User)**: Values are masked on `/auth/me` (`[stored]`). Non-empty string values are **encrypted at rest** (Fernet, key derived from `SECRET_KEY`). Anyone with the DB file **and** `SECRET_KEY` can decrypt; protect both like secret material.
- **Refresh tokens**: Each refresh JWT includes a `jti`; rotation and logout record revoked `jti` rows so stale refresh cookies cannot be replayed (see `revoked_refresh_tokens` table).
- **Workflow run retention**: Startup purges `WorkflowRun` / `NodeRunLog` rows older than `WORKFLOW_RUN_LOG_RETENTION_DAYS` (0 disables). Node logs are stored **redacted** for prompt-like fields. Each run records **`started_by_user_id`**; list/get/delete APIs scope by that user.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `local` | `local` vs production-like envs. Non-`local` requires a strong `SECRET_KEY` (32+ chars, not the dev placeholder). OpenAPI `/docs` is served only when `APP_ENV=local`. |
| `DATABASE_URL` | `sqlite:///./mindweave.db` | Database connection URL. Override via `.env` to change DB path. |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | URL to your local LLM provider (e.g. LM Studio). Server config only. |
| `LMSTUDIO_MODEL` | *(empty)* | Default OpenAI-compat chat model id (must appear on **`GET …/v1/models`**). If empty or the legacy placeholder **`local-model`**, the backend uses the **first** model returned by that list. Override per Persona (**`default_model`**) or workflow step. |
| `LMSTUDIO_API_KEY` | *(empty)* | **Required** for **`GET /api/v1/models/`** (shared Persona/workspace picker list). For **chat and workflow LLM** calls, per-user **`lmstudio_api_key`** in My Settings is preferred; this env is the fallback when no user key is set. |
| `LMSTUDIO_CHAT_TIMEOUT` | `3600.0` | Timeout in seconds for LM Studio chat completion requests (default **1 hour**). Lower for faster failure on stuck calls; raise if needed. |
| `LMSTUDIO_MODEL_LOAD_TIMEOUT` | `300.0` | Seconds for native **`POST /api/v1/models/load`** (blocking load). |
| `LMSTUDIO_MODEL_READY_MAX_WAIT_SECONDS` | `60.0` | After a successful native load, poll **`GET /api/v1/models`** until the model reports **`loaded_instances`** (or stop after this many seconds). **`0`** disables polling. Reduces failed parallel **Simple LLM Call** steps while weights finish loading. |
| `LMSTUDIO_CHAT_RETRY_BUDGET_SECONDS` | `120.0` | Total wall-clock budget for retrying transient LM Studio **`POST …/v1/chat/completions`** errors (**429** / **500** / **502** / **503** / **504**; not **401**) from **workflow runs** (OpenAI-compat route name; not a separate “chat” product). LM Studio may return **500** briefly while the model is still initializing. |
| `TTS_BRIDGE_URL` | `http://127.0.0.1:8765` | Base URL of the local **TTS bridge** (`services/tts-bridge/`). Mind Weave calls **`POST /v1/tts`** and **`POST /v1/models/pull`** here via **httpx** only—no PyTorch or vendor SDKs in the API process. |
| `TTS_BRIDGE_TOKEN` | *(empty)* | Optional **`X-TTS-Bridge-Token`** header sent to the bridge when set (bind the bridge to **127.0.0.1** in production). |
| `TTS_BRIDGE_PULL_TIMEOUT` | `3600.0` | Seconds for **`POST /v1/models/pull`** (large HF snapshots). |
| `TTS_BRIDGE_SYNTH_TIMEOUT` | `600.0` | Seconds for **`POST /v1/tts`** synthesis. |
| `TTS_BRIDGE_MAX_AUDIO_BYTES` | `52428800` | Max accepted WAV payload size from the bridge (**50 MiB**); keep aligned with bridge caps. |
| `STT_BRIDGE_URL` | `http://127.0.0.1:8766` | Base URL of the local **STT bridge** ([`services/stt-bridge/`](../services/stt-bridge/)). The API calls **`POST /v1/transcribe`** via **httpx** after a **`transcribe_audio`** step receives uploaded audio. |
| `STT_BRIDGE_TOKEN` | *(empty)* | Optional **`X-STT-Bridge-Token`** sent to the bridge when set. |
| `STT_BRIDGE_TIMEOUT` | `600.0` | Seconds for **`POST /v1/transcribe`**. |
| `STT_AUDIO_WAIT_TIMEOUT` | `300.0` | Max seconds a **`transcribe_audio`** step blocks inside **`execute_scheduled_run`** waiting for **`POST .../transcribe-audio`** from the editor during a Build SSE run. |
| `STT_MAX_AUDIO_UPLOAD_BYTES` | `78643200` | Max bytes for workflow STT multipart uploads (**75 MiB**); keep aligned with [`services/stt-bridge`](../services/stt-bridge/README.md), frontend **`VITE_STT_MAX_AUDIO_UPLOAD_BYTES`**, and proxy **`client_max_body_size`**. |
| `TRANSCRIPTION_PROVIDERS_ENABLED` | `["local_whisper","assemblyai"]` | Allow-list of provider ids exposed for the **`transcribe_file`** skill via **`GET /api/v1/transcription/providers`**. Set to `["local_whisper"]` only to hide cloud providers from the editor. |
| `TRANSCRIPTION_JOB_POLL_INTERVAL` | `5.0` | Lifespan poller cadence (seconds) for in-flight **`transcription_jobs`** rows. **0** disables the poller. |
| `ASSEMBLYAI_API_KEY` | *(empty)* | Server-wide fallback for AssemblyAI; consulted only when the running user has no per-user `assemblyai` key in **My Settings → API Settings**. |
| `ASSEMBLYAI_BASE_URL` | `https://api.assemblyai.com` | AssemblyAI v2 base URL. Override for self-hosted or staging mirrors. |
| `ASSEMBLYAI_UPLOAD_TIMEOUT` | `300.0` | Seconds for the multipart `POST /v2/upload`. |
| `ASSEMBLYAI_REQUEST_TIMEOUT` | `60.0` | Seconds for `POST /v2/transcript` and `GET /v2/transcript/{id}`. |
| `ASSEMBLYAI_POLL_INTERVAL` | `3.0` | Seconds between inline polls while a stream is attached. |
| `ASSEMBLYAI_JOB_TIMEOUT` | `1800.0` | Total wall-clock budget the executor will wait inline before falling back to the lifespan poller. |
| `ASSEMBLYAI_SPEECH_MODELS` | `["universal-3-pro"]` | Non-empty list of AssemblyAI speech model ids sent as **`speech_models`** on **`POST /v2/transcript`** (Universal 3 tier: **`universal-3-pro`**; **`universal-2`** also supported). |
| `FETCH_URL_DEFAULT_TIMEOUT_MS` | `30000` | Default HTTP timeout for workflow **`fetch_url`** when the node omits **`timeout_ms`**. |
| `FETCH_URL_MAX_BODY_BYTES` | `2097152` | Max response **body** bytes read for **`fetch_url`** (**2 MiB**); larger responses return a structured error on the success path. |
| `CAPTURE_URL_SNAPSHOT_DEFAULT_TIMEOUT_MS` | `30000` | Default navigation timeout for **`capture_url_snapshot`** when the node omits **`timeout_ms`**. |
| `CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH` | `1280` | Default viewport width when **`viewport_width`** is omitted. |
| `CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT` | `720` | Default viewport height when **`viewport_height`** is omitted. |
| `CAPTURE_URL_SNAPSHOT_MAX_PNG_BYTES` | `25165824` | Max **PNG** bytes for **`capture_url_snapshot`** (**~24 MiB**); larger screenshots return a structured error on the success path. |
| `SECRET_KEY` | *(dev placeholder)* | JWT signing key. Min 16 chars in `local`; min 32 and non-placeholder otherwise. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access JWT lifetime (cookie max-age). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh cookie lifetime. |
| `WORKFLOW_RUN_LOG_RETENTION_DAYS` | `90` | Delete workflow runs and node logs older than this many days on startup (`0` = disable). |
| `OPEN_REGISTRATION` | `true` | When `false`, `POST /auth/register` returns 403. |
| `BOOTSTRAP_DEFAULT_ADMIN` | `false` | If `true` and `APP_ENV=local` and no users exist, creates `admin`/`admin`. |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Allowed CORS origins for the frontend. |
| `CORS_ALLOW_METHODS` / `CORS_ALLOW_HEADERS` | *(see `config.py`)* | Narrow CORS allowance (no `*` with credentials). |
| `TRUSTED_HOSTS` | `localhost`, `127.0.0.1`, `testserver` | Allowed `Host` header values (`*` not used). For Path C, include your **API** hostname (e.g. `api.example.com`) — nginx forwards it unchanged. |
| `SECURITY_ENABLE_HSTS` | `false` | Send `Strict-Transport-Security` when behind HTTPS only. |
| `BEHIND_REVERSE_PROXY` | `false` | When `true`, trust `X-Forwarded-Proto` / `X-Forwarded-For` from nginx on `127.0.0.1` / `::1` (see [DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md) Path C). |
| `AUTH_*_RATE_LIMIT` | *(see `config.py`)* | In-process per-IP limits on auth POST routes (one worker; use a proxy for multi-worker). Each value must be `N/minute` (e.g. `30/minute`); malformed values fail at startup. |
| `WORKFLOW_RUN_RATE_LIMIT` | `60/minute` | In-process per-IP limit on **`POST …/workflow-definitions/{id}/run`** plus **`POST …/workflow-definitions/{id}/runs`** (shared bucket, SE-029). Same **`N/minute`** format. |
| `WORKSPACE_ENABLED` | `true` | When `false`, Companion and Workspace API routes return **404**. |
| `SANDBOX_ENABLED` | `true` | When `false`, Sandbox API routes return **404**. |
| `GOOGLE_CLIENT_ID` | *(empty)* | Google OAuth 2.0 client ID. Required for Google account association. |
| `GOOGLE_CLIENT_SECRET` | *(empty)* | Google OAuth 2.0 client secret. Required for Google account association. |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/api/v1/auth/google/callback` | OAuth redirect URI for **sign-in / account linking**. Must match Google Cloud Console. |
| `GOOGLE_WORKFLOW_REDIRECT_URI` | `http://localhost:8000/api/v1/google-workflow/oauth/callback` | OAuth redirect for **workflow Gmail/Calendar/Google Docs** (readonly scopes). Add as a second authorized redirect URI in the same OAuth client. |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for post-OAuth redirects. |

### LM Studio `401 Unauthorized`

- **Token mismatch** — In LM Studio (**Developer → Server**), enable **Require authentication** if you use tokens; create or copy a token from **Manage tokens** and paste **the token only** into **My Settings → LM Studio API Key** and set **`LMSTUDIO_API_KEY`** on the backend to a valid token (can match one user’s key) so **`GET /api/v1/models/`** can list models for every account. If you paste the literal prefix **`Bearer `** (from curl or docs), requests become **`Authorization: Bearer Bearer …`** and LM Studio returns **401**; the app strips that prefix on save and at resolve time.
- **`SECRET_KEY` rotation** — Per-user API keys are encrypted at rest with Fernet derived from **`SECRET_KEY`**. After changing **`SECRET_KEY`**, existing rows cannot decrypt; **re-save** keys in **My Settings** or rely on **`LMSTUDIO_API_KEY`** until you do. The backend logs a warning and **omits** undecryptable entries instead of sending ciphertext to LM Studio (which would also yield **401**).

### Google OAuth Setup

To enable Google account association (linking a Google account to an existing user):

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Create or select a project.
3. Configure the **OAuth consent screen** (User type: External for testing, or Internal for Workspace).
4. Create **OAuth 2.0 Client ID** credentials (Application type: Web application).
5. Add **Authorized redirect URI**: `http://localhost:8000/api/v1/auth/google/callback` (or your HTTPS API origin in production—must match **`GOOGLE_REDIRECT_URI`** exactly). Non-localhost deployments: **[docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md)**.
6. Copy the Client ID and Client Secret into your `.env` file:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```
7. Restart the backend. Users can then associate their Google account from My Settings (top-right avatar) in the frontend.

**Workflow skills (Gmail / Calendar / Google Docs readonly)** use a **separate** consent and callback:

- Add **Authorized redirect URI**: your `GOOGLE_WORKFLOW_REDIRECT_URI` (default above).
- Enable **Google Docs API** and **Google Drive API** on the same Google Cloud project.
- Ensure the OAuth client allows scopes: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/documents.readonly`, `https://www.googleapis.com/auth/drive.readonly` (see `app/core/google_workflow_oauth.py`).
- Users connect from **My Settings → Google Account → Google for workflows**. One Google account per user is stored in `google_workflow_connections` (encrypted refresh token). All Gmail, Calendar, and Google Docs workflow skills use that account; re-connect after scope updates without editing workflows.

## Database Migrations

The project uses Alembic for migrations. **Migrations run automatically on app startup**, so the schema stays in sync without manual steps. To run migrations manually (e.g. before starting the app in a scripted deployment):

```bash
alembic upgrade head
```

Alembic uses the same `DATABASE_URL` as the app (from `config.py` / `.env`), so migrations and the application always target the same database.
