# Mind Weave Frontend

This is the React frontend for the Mind Weave project, built with Vite, TypeScript, and Tailwind CSS. It provides a workflow-based interface to create Personas and compose Workflows as visual DAGs that execute against local LLMs.

## Architecture Overview

The frontend is structured into several key areas:

- **`src/components/`** — React UI components:
  - `ManagerModal.tsx` — Shared overlay + panel for manager modals (Personas, Structures, Palettes, admin users, My Settings); closes on the **X** or **clicking the dimmed area outside the panel**; optional **`leadingSlot`** (header content left of the title); optional **full screen** toggle (`enableFullscreen` when `maxWidth` is not `full`) for wide layouts
  - `RunExploreModal.tsx` — Sidebar **Build → Replays** (after **Workflows**): opens **`ManagerModal`** with **`maxWidth="full"`** (viewport-sized panel, no separate fullscreen step). Header includes **Back** (left of the title) plus the usual close control. Lists past streamed workflow runs (yours only); delete one run via row trash (inline **Delete** / **Cancel**) or select several (checkboxes, **Cmd/Ctrl** + click like **DocumentManager**, **All loaded** in the header) and use **Delete selected** / **Delete all**. Read-only graph replay (canvas + Explorer with recorded inputs/outputs per node; handle and edge colors still follow the workflow palette) ([`WorkflowRunReplayView.tsx`](src/components/workflow-editor/WorkflowRunReplayView.tsx))
  - `managerShellStyles.ts` — `MANAGER_INPUT_CLS` / `MANAGER_LABEL_CLS` (and matching layout `mw.*` classes in each manager) so modal **bodies** follow `ThemeContext`, not hardcoded grays
  - `PersonaManager.tsx` — Create, edit, delete Personas (modal)
  - `PaletteManager.tsx` — **Editor** tab: workflow palette CRUD backed by **`GET`/`POST`/`PUT`** responses that include **`entries`**, **`effective_colors`**, and **`warnings`**; JSON import previews **`POST /api/v1/palettes/validate`**. The workflow editor calls **`GET /api/v1/palettes/resolve`** for authoritative canvas palette colors (optional **`workflow_id`**). **System** tab: **system theme** palettes (light/dark UI tokens)—list + editor like the Editor tab, built-ins read-only with **Use as my theme** in the editor or the list-row **apply** control on hover (`AuthClient.updateMe` → `settings.system_palette_id`). Import/export via [`src/domain/systemPaletteImportExport.ts`](src/domain/systemPaletteImportExport.ts). [`ThemeContext`](src/contexts/ThemeContext.tsx) merges **defaults → active system palette → `settings.system_colors`**. **`ApiClient`** exposes `getSystemPalettes`, `getSystemPalette`, `getSystemPaletteBySlug`, and CRUD helpers under `/api/v1/system-palettes/`.
  - `StructureManager.tsx` — Create, edit, delete Structures (modal) for JSON schemas
  - `DocumentManager.tsx` — Create, edit, delete Documents (modal); the body editor exposes **Raw** (exact stored **body** text), **Preview** (runs the Markdown pipeline when content is Markdown — JSON and other text use **Raw** for fidelity), and **Metadata** (estimated token count via the GPT-4o family `o200k_base` tokenizer plus character / word / line counts, document id, and timestamps; lazy-fetched from `GET /api/v1/documents/{id}/metadata`, cached per document, invalidated on save, hides the call entirely for unsaved drafts). Uses [`MarkdownRawPreview.tsx`](src/components/MarkdownRawPreview.tsx) (Tailwind Typography `prose`, `react-markdown`, GFM + footnotes, KaTeX math, fenced Mermaid via [`MermaidBlock.tsx`](src/components/MermaidBlock.tsx)) and [`DocumentMetadataPanel.tsx`](src/components/DocumentMetadataPanel.tsx)
  - `VoiceManager.tsx` — **Configure → Voice Sample Manager**: Voice Design preview (**`POST /api/v1/voice-samples/preview-design`**) and save named reference clips (**WAV** + transcript) for workflow **Text-to-Speech** voice clone (`voice_sample_id`)
  - `workflow-editor/` — Visual DAG editor for WorkflowDefinitions (ReactFlow); `WorkflowEditor.tsx` re-exports for stable imports
  - `UserAvatar.tsx` — Circular avatar (initials or custom image) for user identity
  - `auth/Login.tsx` — Login form
  - `auth/MySettings.tsx` — User profile, **View Settings** (appearance `theme_mode`, system palette, preferred editor palette for new workflows), Google account, API keys, avatar (modal, opened from top-right)
  - `auth/UserManagement.tsx` — Admin only: create/manage users (modal, from Configure section)
  - `auth/AdminControlsContent.tsx` — Shared admin UI (Create User, Manage Users) used by UserManagement
- **`src/api/`** — API client and types:
  - `client.ts` — `ApiClient` static class for all backend HTTP calls
  - `authClient.ts` — Auth-specific client (login, getMe)
  - `http.ts` — Shared `fetch` + FastAPI `detail` parsing used by both clients
  - `types.ts` — Shared API shapes; **`Palette`** and related aliases track OpenAPI (**`npm run codegen:palette-types`**, see [`src/generated/palette-types.ts`](src/generated/palette-types.ts)).
- **`src/contexts/`** — React Contexts:
  - `AuthContext.tsx` — User authentication state, login/logout; session via HttpOnly cookies. `checkAuth({ silent: true })` re-fetches the user without toggling `isLoading`, so the app shell is not replaced by the full-screen loader (keeps modals/tabs mounted after `updateMe`, system theme apply, settings saves, etc.).
  - `ThemeContext.tsx` — Light/dark mode + CSS variables from resolved system colors (`system_palette_id` + optional `system_colors`). Exposes `refreshActiveSystemPalette()` to re-fetch the active preset after edits. Surfaces that should follow a user’s **system theme** use Tailwind `mw.*` classes (`bg-mw-page`, `text-mw-text-primary`, …); raw `gray-*` on chrome ignores those tokens.
  - `ClipboardFeedbackContext.tsx` — **`useCopyWithFeedback()`** for Copy controls (**Copied to clipboard** / **Could not copy**) and **`useStatusToast()`** for arbitrary status toasts (same chrome). Wrapped in `main.tsx` around `App`. Actual `navigator.clipboard` call is [`src/systemClipboard.ts`](src/systemClipboard.ts) (mock that module in tests). See [docs/DESIGN_SYSTEM.md](../docs/DESIGN_SYSTEM.md).

## Linting

- From `frontend/`: `npm run lint` (ESLint 9 flat config in `eslint.config.js`, TypeScript + React Hooks).

## Tests

- From `frontend/`: **`npm run codegen:palette-types`** — Writes [`openapi.palette.json`](openapi.palette.json) from the backend subset script and regenerates **`src/generated/palette-types.ts`**. **`npm run verify:palette-types`** repeats codegen and **`git diff --exit-code`** on those artifacts (run locally before merge to catch drift).
- From `frontend/`: `npm run build` — type-check (`tsc`) plus production bundle.

Project-wide conventions: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Views

| View | Path (when enabled) | Component | Description |
|------|---------------------|-----------|-------------|
| Home | `/` (Workspace off) | — | Landing page with links to Personas and Workflows |
| Workspace | `/`, `/workspace` | `WorkspaceView` | Companion chat (hidden when `VITE_WORKSPACE_ENABLED=false`) |
| Workflows | `/workflows`, `/workflows/{uuid}` | `WorkflowEditor` | Visual DAG editor; optional UUID opens that definition after load |
| Sandbox | `/sandbox` | `SandboxView` | Simulation UI (hidden when `VITE_SANDBOX_ENABLED=false`) |

Path sync is implemented in [`src/appUrlState.ts`](src/appUrlState.ts) and [`src/App.tsx`](src/App.tsx) (see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — SPA shell URL).

## Workflow Editor

The Workflow Editor (`src/components/workflow-editor/`, imported as `WorkflowEditor`) is the main interface for building workflows:

- **Left panel** — Collapsible palettes:
  - **Workflows** — **Project** list first (seeded **Shared**, **New project** only—no filter or import at this level). Open a project for **Import**, **New workflow**, segmented sort (Last updated default, or Name A–Z), **Filter…**, and the workflow list (**Back** to folders). New imports and workflows are created in the open project. **Move** per row. Drag a workflow onto the canvas to add it as a Workflow node. Scrollable lists use `max-h-[13.5rem]` like Primitives.
  - **Primitives** — String, List, Dictionary, Boolean, Int, DateTime, Structure, Document, **Image** (user-uploaded or wired snapshot; stored as a URL-snapshot `artifact_id`). Each of **Primitives** / **Skills** / **Utilities** / **Controls** has a **Filter** field (prefix match on labels, case-insensitive) and a scrollable step list (`max-h-[13.5rem]`, same cap as the Workflows drill-in list). Drag a tile onto the canvas to add a node.
  - **Skills** — Simple LLM Call, Gmail List Messages, Calendar List Events
  - **Utilities** — List to String, String to List, Prepend Text, Len from List, Int to String, List Item by Index, Dictionary Value by Key, Read Document Property, Load Document, Upsert Document, **Save text as Document** (`upsert_document` with **`name`** + **`content`** only), Parse Document Body, HTML Parse (basic) (`html_parse_basic`), Write Object to Document Body, Append Value to Document, Validate Against Structure, int math (Add, Subtract, Multiply, Divide, Modulo, Min, Max)
  - **Controls** — Basic Conditional, Is?, Is Empty?, Gt?, Lt?, Gte?, Lte?, And, Or, Xor, Not, Between, For Loop
- **Canvas** — ReactFlow canvas with custom node types. Drag nodes from palettes, connect with edges. **Multi-select:** Cmd-click (macOS) or Ctrl-click (Windows) adds or removes nodes from the selection; Shift-drag draws a selection rectangle; drag any selected node to move the whole group. With more than one node selected, the Explorer shows a short notice until you reduce the selection to a single node (or until you use keyboard delete—see Explorer). **Delete** / **Backspace** (when focus is not in a text field) opens **inline confirmation** to remove the selected node(s) or, if a connection is selected, to remove that edge; **Start** is never removed; at least one **Stop** must remain. **Escape** cancels a pending delete. **Undo / redo** the graph (nodes, edges, step data—not workflow name, palette, or folder) with **Cmd/Ctrl+Z** and **Cmd/Ctrl+Shift+Z** (Windows also **Ctrl+Y**); up to **10** steps per session, cleared when you open a different workflow. In text fields, the browser’s own undo still applies. Maintainer note: cap is **`WORKFLOW_GRAPH_UNDO_PAST_MAX`** in [`src/components/workflow-editor/workflowGraphHistory.ts`](src/components/workflow-editor/workflowGraphHistory.ts). Palette drops use React Flow’s `screenToFlowPosition` so new nodes land under the pointer at the current pan/zoom. **Switching the active workflow** in the list refits the canvas to the **whole** graph (same as the bottom-left **Controls** fit button), implemented via [`FitViewOnWorkflowCanvasKey`](src/components/workflow-editor/FitViewOnWorkflowCanvas.tsx) by waiting for node measurement so `fitView` bounds include every node. **Adding nodes** (palette drops) does **not** refit, so zoom and pan stay where you left them. **Narrow viewports** (below Tailwind `lg`, 1024px): the palette and Explorer open as **slide-over panels** from toolbar buttons so the canvas stays full width; pinch zoom and pan use React Flow defaults (`zoomOnPinch`, `preventScrolling`, etc.). [`useCompactViewport`](src/hooks/useCompactViewport.ts) drives the split. **Immersive fullscreen** (toolbar **Enter fullscreen**): **ArrowLeft** / **ArrowRight** toggle **Palette** / **Explorer** like those toolbar controls (ignored in text fields, with modifier keys held, or while the pre-run inputs wizard, workflow import, or output-override modal is open). **Left/right edge strips** on the canvas use the same toggles on tap (small movement threshold; same modal guard); see [`workflowEditorImmersivePanelArrow.ts`](src/components/workflow-editor/workflowEditorImmersivePanelArrow.ts). When the canvas **wrapper** changes size (sidebars, overlays), [`FitViewOnWorkflowCanvasResize`](src/components/workflow-editor/FitViewOnWorkflowCanvas.tsx) refits to the graph. Handles, edges, and node borders resolve colors via **`effective_colors`** on the loaded workflow palette payload when present, merged with **`resolveWorkflowPaletteColor`** ([`src/domain/paletteDefaults.ts`](src/domain/paletteDefaults.ts)) for **`EDITOR_NODE_PALETTE_EXTRA`** handles and offline fallbacks: specific palette key → optional step-family (`primitive` / `skill` / `utility` / `control`) → **`WORKFLOW_PALETTE_COLORS`** default map → **`any`**. The node or edge targeted by the Explorer shows a palette-tinted animated glow on the canvas (suppressed on the node currently highlighted as **running**). **Branching** controls (**Basic Conditional**, **Is?**, **Is Empty?**, comparisons, **Between**) expose **`signal_out`** (plus **`true`** / **`false`**) for control-flow; **Stop** has **no** `signal_out`. See [docs/DESIGN_SYSTEM.md](../docs/DESIGN_SYSTEM.md) (Editor tab, control-flow handles). **Save** (or **Run**, which saves first) persists graph changes and updates **`updated_at`** so the Workflows list **Last updated** order reflects edits. If **Save** fails, a banner shows the API message; if the workflow’s **project** id no longer exists (e.g. folder removed), **Save** falls back to **Shared** so the graph can still be persisted.
- **Right panel** — Inspector:
  - **Explorer** — Selected **node** configuration (label, text, metadata, Persona, Structure, prompts, etc.) or selected **edge** (data type, source/destination summaries, last-run payload with optional full-view modal). With **multiple nodes** selected on the canvas, the Explorer shows a short notice until exactly one node is selected; you can still **Remove** via **Delete** / **Backspace** (confirmation lists every node to be removed). After that shortcut, the Explorer **scrolls** so the inline delete confirmation is visible (long step forms such as **Simple LLM Call** no longer hide it below the fold). **Last Run** / **Run logs** **Output** uses **`details.output_explorer`** when present ([`docs/OUTPUT_EXPLORER_UI.md`](../docs/OUTPUT_EXPLORER_UI.md)): typed shell + optional row list; full serialized output is available via **Preview** / **View raw** in the output explorer modal.
  - **Run Logs** — Per-node execution results after running a workflow
- **Import / export** — Toolbar **Export** downloads workflow JSON; the adjacent **Copy** control copies the same JSON (versioned wrapper in [`src/domain/workflowImportExport.ts`](src/domain/workflowImportExport.ts)). Use for backups, sharing with support, or attaching to bug reports; each node includes **`label`** and **`id`** in the file.
- **Run** — Toolbar **Run** saves the workflow, then starts execution. If the **Start** node has required inputs with no value set in the inspector (empty string for strings; **`null`** for list/dictionary/int/boolean/datetime; note that an explicit **`[]` / `{}`** in JSON is a real value, not “unset”), a **stepped modal** asks for **one slot per step** in Start list order, then sends them as `input_overrides`. Use **Continue** between steps, **Run** on the last step, **Back** to edit a previous answer, **Cancel** to close without running.
- **Normalize JSON** — List and dictionary JSON fields (List/Dictionary primitives, Start list/dict slots, pre-run wizard) expose an explicit **Normalize JSON** control. It runs [`src/domain/normalizeText.ts`](src/domain/normalizeText.ts) (`normalizeText` / `normalizeTextAsList` / `normalizeTextAsDictionary`) to strip common noise (markdown code fences, standalone `---` lines) and extract a balanced array or object. **Timing** is **explicit** (button) for these types so partial JSON while typing is not rewritten automatically; future primitive kinds can use **`on_input`** via the same module’s `NormalizationTiming` pattern.

## Graph Node Types

| Type | Kind | Description |
|------|------|--------------|
| Simple LLM Call | `skill` (simple_llm_call) | Requires a Persona. Three input handles: Add context, User Prompt, and Structure (optional). Structure can be selected in the inspector or wired from a Structure primitive. When Structure is provided, the LLM returns deterministic JSON; otherwise free-form text. Shows Persona selector, Structure selector, Additional System Prompt Context, and User Prompt. Handle dots change color when satisfied. Run fails if no Persona is selected. |
| Multimodal LLM | `skill` (multimodal_llm) | Same Persona/Structure/output behavior as Simple LLM Call, plus required **Images** (list) input for `artifact_id` references (e.g. **Image** primitive or **URL snapshot**). Optional **model** override in the inspector. Non-vision models fail with a structured `MODEL_NOT_MULTIMODAL` error from the runtime. |
| Voice input | `skill` (transcribe_audio) | Records from the **microphone** only during **Run** (stream) when the run asks for audio (**Talk** / **Stop** in a canvas banner). Wires like other steps: connect **trigger** from upstream (e.g. **Start**), **text** out to LLM, TTS, or **Stop**. Requires the [STT bridge](../services/stt-bridge/README.md) and [backend STT settings](../backend/README.md#environment-variables). |
| List to String | `utility` (list_to_string) | Converts a **list** to one **string**. Default in the editor is **joined text** (`data.use_text_join: true`): items are concatenated with newlines or spaces via **Add line breaks between items** (`data.add_line_breaks_between_items`, default true). For **String to List** round-trips, enable **Output as JSON array** (`use_text_join: false`) to emit pretty-printed JSON (legacy/API-only graphs with empty `data` behave the same). One **list** input and one **string** output. |
| String to List | `utility` (string_to_list) | Parses a JSON **array** string into a list. One input handle (string) and one output handle (list). Wire from String, LLM output, or Start string slot; pairs with **List to String** when that node uses **JSON array** output. |
| Len from List | `utility` (len_from_list) | Returns the length of a list. One input handle (list) and one output handle (int). Wire from List primitive or Start list slot. |
| Int to String | `utility` (int_to_string) | Converts an integer to its decimal string. One input handle (int) and one output handle (string). Wire from Int primitive, int math, Len from List, or Start int slot; string-shaped inputs must parse as a single integer (same rules as other int slots). |
| List Item by Index | `utility` (list_item_by_index) | Returns the item at a given index in a list. Two input handles (index, list) and one output (any). Wire index from Int primitive or Len from List; wire list from List primitive or Start. Out-of-bounds indices raise an error. |
| Dictionary Value by Key | `utility` (dictionary_value_by_key) | Reads a value by key from a dictionary. Inputs: **key**, **dictionary**, optional **fallback** (wire) or optional static JSON in the inspector. Output typed per **Output type** (string, list, dictionary, boolean, int, datetime). If the key is missing or the value is null, a configured fallback is used (wire wins over static). Wrong JSON type at an existing key still errors. |
| Dictionary Set Value by Key | `utility` (dictionary_set_value_by_key) | Shallow-copies a dictionary and assigns one top-level key. Three inputs (**dictionary**, **key**, **value**); output is always a **dictionary**. Adds or overwrites the key; wire **value** from lists or other steps (e.g. after a For loop). |
| Read Document Property | `utility` (read_document_property) | Reads a named field from a **Document** output. Inputs: **document**, **target_property** (e.g. `body` for stored text). Output type selector matches Dictionary Value by Key (including **datetime** for RFC3339 strings). |
| Prepend Text | `utility` (prepend_text) | Prepends text to a target string. Two input handles (target_string, text_to_prepend) and one output (output_string). Optional "Add additional line" checkbox inserts a blank line between prepended text and target. |
| String Trunc | `utility` (string_trunc) | Substring by 0-based indices: inputs **target_string**, **start_index** (≥ 0), **end_index** (inclusive, or **-1** for “through end of string”). Output handle **output_string**. |
| Add / Subtract / Multiply / Divide / Modulo / Min / Max | `utility` (`add_ints`, …, `max_ints`) | Binary integer math on **`input_a`** and **`input_b`** → int output. Divide truncates toward zero. Divide and Modulo error if divisor is zero. |
| Basic Conditional | `control` (basic_conditional) | Evaluates a condition (from UI or wired input). One input handle (condition) and two outputs (true, false). Only the matching branch executes. Condition values: true/yes/1 → true; false/no/0/empty → false; non-empty → true. |
| Is? | `control` (is) | Compares two inputs (input_a, input_b) for equality. Two input handles (A, B) and two outputs (true, false). Accepts any type (string, list, dictionary, or wired from upstream). Only the matching branch executes. |
| Gt? | `control` (gt) | True if input_a &gt; input_b, else False. Two inputs (A, B) and True/False branch outputs. |
| Lt? | `control` (lt) | True if input_a &lt; input_b, else False. Two inputs and True/False branch outputs. |
| Gte? | `control` (gte) | True if input_a &gt;= input_b, else False. Two inputs and True/False branch outputs. |
| Lte? | `control` (lte) | True if input_a &lt;= input_b, else False. Two inputs and True/False branch outputs. |
| And | `control` (and) | Boolean AND of two inputs (A, B). Single boolean output. |
| Or | `control` (or) | Boolean OR of two inputs (A, B). Single boolean output. |
| Xor | `control` (xor) | Boolean XOR of two inputs (A, B). Single boolean output. |
| Not | `control` (not) | Boolean NOT of one **`input`**. Single boolean output (no True/False branches). |
| Between | `control` (between) | Range test: **`low`**, **`value`**, **`high`** (ints). True branch when `low <= value <= high` inclusive; **`low > high`** is invalid. True/False outputs; only the matching branch executes. |
| String | `primitive` (string) | Static text input |
| List | `primitive` (list) | Static list (JSON array). Inspector keeps local text while editing; **Normalize JSON** formats pasted or noisy output. |
| Dictionary | `primitive` (dictionary) | Static object (JSON object). Same **Normalize JSON** behavior as List. |
| Structure | `primitive` (structure) | References a Structure (JSON schema). Connect to Simple LLM Call or Multimodal LLM **Structure** handle for deterministic JSON output. Select a Structure in the inspector. |
| Document | `primitive` (document) | References a saved **Document** (flexible **body** text + metadata; wire field **`markdown`** in outputs). Emits a **document**-typed output for utilities. Create documents under **Configure → Documents** first; the workflow Explorer lists existing documents only (no inline create in v1). |
| Image | `primitive` (image) | Normalized snapshot artifact: **`artifact_id`**, `mime_type`, `width`, `height` (dictionary output for **Multimodal LLM** `images` or other steps). **Choose image** uploads via `POST /api/v1/url-snapshot-artifacts` (multipart `file`); or wire **`image`** from **URL snapshot** (or another Image node). |
| Gmail | `primitive` (gmail) | One curated **Gmail message** object (JSON in the inspector and/or wired **`gmail`** input). Emits **`gmail`**-typed output (same object shape as items from **Gmail List Messages**). |
| Boolean | `primitive` (boolean) | Static boolean input (inspector toggle). |
| Int | `primitive` (int) | Static integer input. |
| DateTime | `primitive` (datetime) | Static RFC3339 instant (date + time in **My Profile → Workflow time zone**, or raw RFC3339). Same wire shape as Gmail/Calendar time fields. |
| Start | `start` | Entry point; defaults to no required inputs. Add inputs (`string`, `list`, `dictionary`, `document`, `gmail`, `boolean`, `int`, `datetime`, …) via the inspector when needed. Each input has its own output handle for wiring. When empty, a single `output` handle emits an empty string. **Unset** means `null` in the graph (empty list/dictionary fields in the UI—do not pre-fill `[]`/`{}`); type **Boolean** uses **At run time…** for `null`, or **True**/**False**. Explicit **`[]` / `{}`** after entering JSON counts as a provided value. Unset slots are collected in the stepped **Provide required inputs** dialog when you **Run**; otherwise use API `input_overrides`. |
| Stop | `stop` | Exit point; gathers final upstream output. Define one **Required Output** (key + type) in the inspector to set the expected output type for the workflow. The input handle is colored by the assigned type. Default: `output` (string). |
| Workflow | `workflow` | Executes a referenced sub-workflow. Drag from the Workflows list onto the canvas. Input handles are derived from the sub-workflow's Start node required inputs (key + type). Output handles are derived from the sub-workflow's Stop node required outputs (key + type). Handles and edges use palette colors by type. |

## Adding a New Skill

When adding a skill node (e.g. **Simple LLM Call**, **Multimodal LLM** `multimodal_llm`, **Fetch URL** `fetch_url`, **URL snapshot** `capture_url_snapshot`, Gmail/Calendar, …), follow the same steps as a utility, but use **`kind: "skill"`** and **`skill_type`**. Add a manifest row in `shared/workflow_graph_step_kinds.json`; extend `stepKindRegistry.ts` for `skill:*` keys; add the **Skills** palette section row in `WorkflowEditor.tsx`; wire `appNodeToFlow` / `flowNodeToApp` like other discriminated nodes.

## Adding a New Utility

When extending the codebase with a new utility node, follow these steps:

1. **Types** (`src/api/types.ts`): Add `XxxUtilityNode` interface and to `GraphNode` union
2. **WorkflowEditor** (`src/components/workflow-editor/`): Add **`palette_handle`** / **`editor_label`** plus default hex (`palette_defaults.py` / manifest)—SPA picks **`effective_colors`** from the palette API for canvas chrome. Create `XxxNodeComp` using `StyledNodeBase`; register in `nodeTypes`; add to **Utilities** palette array; handle in `onDrop`, `appNodeToFlow`, `flowNodeToApp`; enrich in `nodesForFlow`; add to `getSourceOutputType`; update `appEdgeToFlow` target/source handle defaults; add inspector block
3. **PaletteManager** (`src/components/PaletteManager.tsx`): **`PALETTE_ENTITIES`** labels feed the “Specific step colors” grid; **`effective_colors`** / **`entries`** from the previewed palette wins over static defaults when rendering swatches (`WORKFLOW_PALETTE_COLORS`).
4. **Documentation**: Update Utilities palette list, Graph Node Types table in this README

Design pattern notes: Use `StyledNodeBase` with `inputs`/`outputs` as `NodeSlot[]`. For multi-input utilities, store `required_inputs` in `data`; use `_resolve_inputs_by_target_handle` on backend. Optional options (e.g. checkboxes) go in `data`. Every new utility needs a unique palette color key.

## Adding a New Control

When extending the codebase with a new control node (e.g. Basic Conditional), follow the same steps as Adding a New Utility, but use `kind: "control"` and `control_type` (e.g. `basic_conditional`). Add to the Controls palette section. Control nodes that branch (True/False) require executor changes to only activate downstream nodes on the matching branch.

## Navigation Structure

The left sidebar has three sections:

1. **Unlabeled** — Home
2. **Build** — Workflows, Replays
3. **Configure** — Personas, Structures, Documents, Palettes, User Management (admin only), Light/Dark mode

The top-right header shows the user avatar (initials or custom image). Clicking it opens **My Settings** (profile, View Settings, Google account and workflow connections, default **Gmail workflow filters** (`category:` / `-category:` defaults for Gmail List nodes), API keys, avatar upload).

## Authentication Flow

The application requires authentication. The **primary** session is **HttpOnly cookies** (`mw_access_token`, `mw_refresh_token`) set by the backend on login, register, refresh, and Google session completion. All API calls use `credentials: 'include'` so the browser sends those cookies to the API origin.

1. On load, `AuthContext` calls `AuthClient.getMe()` with **cookies only** (`credentials: 'include'`). The SPA does not store access tokens in `localStorage`.
2. If the session is invalid, the user sees the `Login` component (or Google OAuth error query params are surfaced).
3. After a successful password login or Google flow (one-time `google_session` URL fragment exchanged via `POST /auth/google/session`), cookies hold the session and `getMe` runs again.
4. The main `App` layout renders: sidebar (Home; Build: Workflows, Replays; Configure: Personas, Structures, Documents, Palettes, User Management for admins; Light/Dark in My Settings), top-right avatar opening My Settings. Workflows can select a Palette in the toolbar; handle, edge, and node border colors follow the Palette's type mapping.

**Non-browser clients:** The API still accepts `Authorization: Bearer` for access tokens when integrating outside this SPA; the bundled React app does not use that path.

**Deployment:** The frontend origin must be listed in the backend `CORS_ORIGINS`, and you must use the same cookie-capable setup (API origin + `VITE_API_BASE`) as described in the backend README. `index.html` includes a **baseline Content-Security-Policy** (`connect-src` allows local dev hosts and scheme-wide `http:` / `ws:` for LAN API origins; see **LAN / same-network devices** below). Browsers do not enforce `frame-ancestors` from a **meta** tag (it must be an HTTP response header), so the meta policy omits it; if you need to restrict embedding, set `Content-Security-Policy: frame-ancestors …` or `X-Frame-Options` on responses that serve the static app. **`media-src`** explicitly allows **`blob:`** and **`data:`** so workflow **Text-to-Speech** inline `<audio>` (object URLs from base64) is not blocked—without it, `media-src` falls back to `default-src 'self'`, which blocks blob media while **Download** still works. For production, narrow `connect-src` to your real API origin (or set CSP via reverse proxy and remove/override the meta tag); if you replace the policy, keep the same **`media-src`** allowance for TTS playback.

## One-command startup with the backend (`make dev`)

Prefer repo-root **`make dev`** when you want the SPA **and** API together (**`npm run dev:lan`** exports **`VITE_API_BASE`** for the spawned session). Prerequisites and troubleshooting: root [README.md](../README.md#quickstart); common failures also [README Troubleshooting](../README.md#troubleshooting).

## Setup & Running

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```

By default, the Vite dev server runs on `http://localhost:5173`. The API origin defaults to `http://localhost:8000` (see `src/api/baseUrl.ts`). For everyday work, keep the dev servers bound to localhost. Only bind to all interfaces (below) on **trusted** networks; do not expose the Vite or FastAPI dev servers to untrusted Wi‑Fi or public networks.

### LAN / same-network devices

Use this when you want the app in a **browser on another phone or PC** on the same Wi‑Fi or home network. One machine (the **host**) runs the backend and Vite; that machine’s **`localhost` is not visible** to other devices, so everyone else opens the UI using the host’s **LAN IP address** (e.g. `192.168.1.42`). Only do this on **networks you trust**; binding dev servers to all interfaces exposes them to that network.

**What has to line up**

These three ideas are the whole story:

1. **URL in the browser** — The page users open, e.g. `http://192.168.1.42:5173` (same host you put in `FRONTEND_URL`).
2. **`VITE_API_BASE` in `frontend/.env`** — The API **origin** on that same host, e.g. `http://192.168.1.42:8000` (no `/api/v1`; see [API Base URL](#api-base-url) below).
3. **Backend allowlists** — `CORS_ORIGINS` must include that browser origin; `TRUSTED_HOSTS` must include the **hostname only** (e.g. `192.168.1.42`, no port); `FRONTEND_URL` must match the SPA URL for server redirects. Details: [Environment Variables](../backend/README.md#environment-variables) in the backend README.

**Walkthrough** (do these in order)

1. **Find the host machine’s LAN IP** (the address other devices use to reach it). Examples: macOS `ipconfig getifaddr en0` (or check **System Settings → Network**); Windows `ipconfig` (look for IPv4 under your active adapter); Linux `hostname -I`. Below, replace `192.168.1.42` with your real address everywhere.

2. **Configure the backend** — In `backend/.env`, set JSON list values as in [`backend/.env.example`](../backend/.env.example) (lists use JSON in `.env`). Example for LAN plus localhost (so you can still use the app on the host via `localhost`):

   ```env
   CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://192.168.1.42:5173"]
   TRUSTED_HOSTS=["localhost","127.0.0.1","testserver","192.168.1.42"]
   FRONTEND_URL=http://192.168.1.42:5173
   ```

   Restart the backend after changing `.env`.

3. **Start the API listening on the LAN** — From `backend/`:

   ```bash
   uv run python -m fastapi dev --host 0.0.0.0 app/main.py
   ```

   Or, without the FastAPI CLI (ASGI only; default port 8000):

   ```bash
   uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   From the repository root (without `cd backend`): `uv run --project backend python -m fastapi dev --host 0.0.0.0 app/main.py` (see [backend README](../backend/README.md#setup--running)).

4. **Point the frontend at the LAN API** — In `frontend/.env`, set:

   ```env
   VITE_API_BASE=http://192.168.1.42:8000
   ```

   Restart Vite after any `.env` change.

5. **Start Vite on the LAN** — From `frontend/`:

   ```bash
   npm run dev:lan
   ```

   Equivalent: `npm run dev -- --host`. In the terminal, use the **Network** line (e.g. `http://192.168.1.42:5173`) as the link on phones and other PCs.

6. **Quick check** — From another device, open `http://192.168.1.42:8000/api/v1/health`. If it loads, the API is reachable and the firewall allowed the port; then open the Vite **Network** URL for the UI.

**LM Studio / local LLM** — `LMSTUDIO_BASE_URL` stays on the **host** (usually `http://127.0.0.1:1234/v1`). Phones and other PCs do not need to reach LM Studio; only the backend on the host talks to it.

#### Google sign-in on LAN

**Google Cloud Console does not allow** OAuth redirect URIs whose host is a **private LAN IP** (`10.x`, `192.168.x`, etc.). You cannot register `http://192.168.…:8000/…` for Web OAuth clients—use **password login** on LAN, or deploy behind a **public HTTPS hostname** (your domain or a tunnel). Redirect URIs must match **`GOOGLE_REDIRECT_URI`** and **`GOOGLE_WORKFLOW_REDIRECT_URI`** exactly.

Full matrix (localhost vs LAN vs domain vs tunnel): **[docs/DEPLOYMENT_AND_NETWORK.md](../docs/DEPLOYMENT_AND_NETWORK.md)**.

**HTTPS nginx (Path C):** If you reverse-proxy the Vite dev server behind `https://app…`, set **`DEV_ALLOWED_HOSTS`** (and usually **`DEV_HMR_HOST`** to the same app hostname) in `frontend/.env` so Vite accepts the **`Host`** header and HMR uses **wss** (see [`.env.example`](.env.example) and Path C in the deployment doc).

#### Firewall and security

The OS may show a firewall prompt the first time something listens on `0.0.0.0`. Allow access only on networks you trust.

#### If something breaks

- **Browser console mentions CORS** — Add the exact origin you use in the address bar (scheme + host + port) to `CORS_ORIGINS`.
- **400 / “Invalid host” / API unreachable by hostname** — Ensure `TRUSTED_HOSTS` includes the **host** part of the URL only (no `http://`, no port).
- **LM Studio errors from another device** — Run workflows from the LAN UI; the backend still calls LM Studio on the host. Do not point `LMSTUDIO_BASE_URL` at the phone’s IP unless you intentionally run the model server elsewhere.

## API Base URL

Set `VITE_API_BASE` in `.env` (see [`.env.example`](.env.example)) to the **API origin only** (e.g. `http://localhost:8000` or `http://192.168.x.x:8000` on LAN), not `…/api/v1`. The client appends `/api/v1` itself; including `/api/v1` in the env value used to duplicate the path and break OAuth (404 JSON from the API).
