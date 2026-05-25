# Mind Weave Design System

The app uses a built-in design system with configurable colors. Colors are controlled via the **Manage Palettes** modal (Palettes in the sidebar). **Appearance** (light / dark / follow device) and default palette choices for the app shell and **new workflows** are in **My Settings → View Settings** ([`frontend/src/components/auth/MySettings.tsx`](../frontend/src/components/auth/MySettings.tsx)).

## Markdown preview

Raw / Preview for **Documents** and other surfaces that use [`MarkdownRawPreview.tsx`](../frontend/src/components/MarkdownRawPreview.tsx) relies on **Tailwind Typography** (`@tailwindcss/typography` registered in [`tailwind.config.js`](../frontend/tailwind.config.js); `prose` / `prose-sm` / `dark:prose-invert` plus `mw.*` token tweaks for headings and links). **Preview** interprets the stored **`body`** as Markdown when you are authoring Markdown (headings, lists, fenced code, math, Mermaid). **Raw** always shows the exact stored text—including JSON or other non-Markdown payloads—without interpretation. **Preview** renders with **react-markdown**, **remark-gfm** (tables, task lists, footnotes), **remark-math** + **rehype-katex**, and KaTeX base CSS imported once from [`main.tsx`](../frontend/src/main.tsx). Fenced **` ```mermaid `** blocks are drawn with dynamically imported **mermaid** in [`MermaidBlock.tsx`](../frontend/src/components/MermaidBlock.tsx); diagram theme follows app dark mode, with horizontal scroll for wide SVGs and an error + source fallback when parsing fails.

**Optional Metadata tab:** [`MarkdownRawPreview`](../frontend/src/components/MarkdownRawPreview.tsx) accepts an optional **`metadataSlot`** (`{ content: ReactNode; isLoading?: boolean }`) and an `onModeChange` callback. When provided, a third **Metadata** button renders next to **Raw** / **Preview** and shows the slot content (or a "Loading metadata…" indicator) when active. **Manage Documents** uses this slot to host [`DocumentMetadataPanel`](../frontend/src/components/DocumentMetadataPanel.tsx) — a definition list of token / character / word / line counts plus document id and timestamps from **`GET /api/v1/documents/{id}/metadata`**, lazy-fetched the first time the tab is opened (cached per-id, invalidated on save). Other consumers (e.g. [`WorkflowNodeRunOutputBody.tsx`](../frontend/src/components/workflow-editor/WorkflowNodeRunOutputBody.tsx)) omit the slot and continue to render only Raw / Preview.

## Tabs

### Editor Tab

Workflow node colors for the visual DAG editor. Each palette maps **specific step colors** (String, List, Dictionary, Workflow, Simple LLM Call under **Skills**, utilities such as List to String, etc.) to hex colors for handles, edges, and node borders. Optionally, **step family** keys apply to every step in that family when no specific color is set: `primitive`, `skill`, `utility`, `control` (same strings as the step `kind` in the shared manifest). Resolution order: specific key → family key → built-in default for that key → `any` (`resolveWorkflowPaletteColor` in [`frontend/src/domain/paletteDefaults.ts`](../frontend/src/domain/paletteDefaults.ts)). In **Manage Palettes → Editor**, per-step **color swatches** use that resolver so previews match the canvas when a palette is **sparse** (family keys only); the **hex text** field shows only **explicit** per-step overrides (empty means inherited). Persisted user palettes still use `normalizeWorkflowPaletteColors` so unchanged keys stay sparse. Workflows select a palette via `palette_id`. Closing **Manage Palettes** triggers a palette refetch in the workflow editor.

**Left sidebar — Workflows:** Collapsible **Workflows** opens a **project** list first (only the **Workflows** header and **New project…** on this screen; folders include a seeded **Shared** row with counts derived from loaded workflows). Clicking a project drills into that folder: **Back**, folder title, **Import** and **New workflow** on the title row (Workflow Editor), **Delete project** (trash icon with inline **Delete** / **Cancel**; **Shared** has no delete control; non-empty folders warn that all workflows—including custom skills in that folder—will be deleted), a **segmented control** (Last updated / Name A–Z; default **Last updated**) for workflow order, then **Filter…** (prefix on names) and the workflow list—same scroll cap **`max-h-[13.5rem]`** (`PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS` in [`workflowEditorPanelLayout.ts`](../frontend/src/components/workflow-editor/workflowEditorPanelLayout.ts))—plus **Move** per row. **Sandbox — Place creature** uses the same project drill-in pattern in the cell action modal ([`SandboxCellActionModal.tsx`](../frontend/src/components/SandboxCellActionModal.tsx)): project list with counts (empty folders hidden), then workflow list with sort and filter; custom skills are excluded from creature-brain selection. Sandbox’s left sidebar is **Boards**, not workflow projects. Canvas edits (layout, wiring) are persisted and bump **`updated_at`** only after **Save** (toolbar) or **Run** (which saves first); until then the left list order under **Last updated** does not change. Implementation: [`WorkflowEditor.tsx`](../frontend/src/components/workflow-editor/WorkflowEditor.tsx), [`WorkflowProjectDeleteControl.tsx`](../frontend/src/components/workflow-editor/WorkflowProjectDeleteControl.tsx), [`workflowListFilter.ts`](../frontend/src/components/workflow-editor/workflowListFilter.ts).

**Left sidebar — step palette:** Collapsible **Primitives**, **Skills**, **Utilities**, and **Controls** each include a **Filter** field (case-insensitive **prefix** match on step labels) and a **scrollable** list capped at **`max-h-[13.5rem]`** (`PALETTE_SECTION_LIST_MAX_HEIGHT_CLASS` in [`workflowEditorPanelLayout.ts`](../frontend/src/components/workflow-editor/workflowEditorPanelLayout.ts)). Implementation: [`WorkflowPaletteStepSections.tsx`](../frontend/src/components/workflow-editor/WorkflowPaletteStepSections.tsx). **Replays** does not duplicate this column; the read-only canvas still uses the workflow’s palette colors on nodes and edges.

**Scrollbars:** Global styling in [`index.css`](../frontend/src/index.css) uses **`--mw-scrollbar-thumb`**, **`--mw-scrollbar-thumb-hover`**, and **`--mw-scrollbar-track`** (set in `:root` and `.dark` alongside other fallbacks). **Firefox:** `scrollbar-width: thin` + `scrollbar-color`. **WebKit** (Chrome, Safari, Edge): `::-webkit-scrollbar` / `track` / `thumb` / `corner` (~8px). On **macOS**, overlay scrollbars may stay hidden until scroll; that is expected.

**Narrow viewports (phones / small tablets):** When the viewport is below Tailwind’s **`lg`** breakpoint (1024px), the workflow editor and Sandbox use **slide-over panels** for the step palette and Explorer instead of fixed side columns, so the **canvas stays full width**. Toolbar buttons **toggle** **Palette** and **Explorer**. The **workflow editor** has **no full-screen dimmed scrim** over the canvas (that would block drag-drop from the palette and graph interaction); users dismiss a panel via the same toolbar control or by clicking the **empty** canvas. **Sandbox** uses a **dimmed scrim** behind open slide-overs (click scrim to dismiss). On the workflow canvas, **scroll wheel** zooms and **drag** pans; React Flow’s built-in **Controls** (+ / − / fit) use larger touch targets via [`index.css`](../frontend/src/index.css) (coarse pointers get slightly bigger buttons). On the **Sandbox** board, **scroll wheel** and **pinch** zoom; **middle-mouse drag** or **left-drag** pans (short left click opens the cell menu); **+ / − / fit** controls sit on the board canvas (same touch-target sizing). The replay graph ([`WorkflowRunReplayView.tsx`](../frontend/src/components/workflow-editor/WorkflowRunReplayView.tsx)) uses the same Explorer overlay pattern on small screens. [`useCompactViewport`](../frontend/src/hooks/useCompactViewport.ts) wraps `matchMedia('(max-width: 1023px)')`. [`index.html`](../frontend/index.html) sets **`viewport-fit=cover`** for edge-to-edge layouts on notched devices.

**Fullscreen (immersive workflow editor):** On the **Workflows** view, **Enter fullscreen** (toolbar) hides the **app sidebar** and **top bar** so the editor uses the full viewport. Palette and Explorer use the **same slide-over behavior** as narrow viewports (`workflowEditorOverlayPanels` in [`workflowEditorPanelLayout.ts`](../frontend/src/components/workflow-editor/workflowEditorPanelLayout.ts), combining [`useCompactViewport`](../frontend/src/hooks/useCompactViewport.ts) with immersive state from [`App.tsx`](../frontend/src/App.tsx)), including **no blocking scrim** over the canvas so **drag-drop** and **selection** stay usable with a panel open. **ArrowLeft** / **ArrowRight** (no modifier keys) toggle **Palette** / **Explorer** the same way as the toolbar buttons; they are ignored in text-entry targets (same guard as graph undo/delete), when any modifier is held, and while the pre-run inputs wizard, workflow import modal, or output-override modal is open. **Narrow vertical strips** along the **left and right edges** of the **canvas** (below the editor toolbar) do the same on **tap** (pointer movement within a small threshold so drags are less likely to toggle); they use the **modal** guard only (`immersivePanelEdgeTapResult` in [`workflowEditorImmersivePanelArrow.ts`](../frontend/src/components/workflow-editor/workflowEditorImmersivePanelArrow.ts)). **Delete** / **Backspace** that opens inline node or edge delete confirmation (or a keyboard validation message in the Explorer) **opens the Explorer slide-over** like the toolbar **Explorer** toggle, not the fixed-column desktop layout. **Exit fullscreen** restores the shell. While immersive, **My Settings** stays available via the **avatar** control in the editor toolbar (not the browser Fullscreen API).

**Built-in presets:** Read-only **system** palettes (badge **System**): **Default**, **Slate**, **Paper**, **Maritime**, **Aurora**, **Meadow**, **Arcade**. Each has a stable **`slug`** (`default`, `slate`, …) and is defined in [`backend/app/domain/palette_defaults.py`](../backend/app/domain/palette_defaults.py); the API **syncs** `name` and `colors` from code on startup (non-default presets use mostly family keys). Scripts may call **`GET /api/v1/palettes/by-slug/{slug}`**. JSON **export** can include `slug` for these rows; **import** ignores `slug` when creating user palettes. UI order: **Default** first (`slug` or name fallback), then other system presets A–Z, then user palettes A–Z.

**Explorer (node inspector):** The right-hand **Explorer** tab groups configuration into consistent bordered wells via [`InspectorSection`](../frontend/src/components/workflow-editor/InspectorSection.tsx) (uppercase title, optional `titleAside` e.g. [`ContextHelpModal`](../frontend/src/components/ContextHelpModal.tsx), optional description, then fields). With **no node or edge selected**, workflow metadata appears first; when the graph has broken edge handles, **Graph issues** follows in an **amber warning well** ([`WorkflowGraphIssuesPanel.tsx`](../frontend/src/components/workflow-editor/WorkflowGraphIssuesPanel.tsx)—same alert palette as import notices) with per-issue **Focus** / **Delete connection** actions. The **Run Logs** tab shows the same **Graph issues** panel at the top when wiring problems exist (amber tab indicator); run execution logs appear below. **General** holds the step type (**Node**), the persisted graph **Node id** (read-only, copy via the same clipboard feedback pattern as elsewhere), and **Label**; each node type adds ordered sections (e.g. **Simple LLM Call** → Model, Prompts; **Gmail List** → About, Connection, **Time & limits** (date + time + profile time-zone hint + info modal; **Unread** / **Max** below), **Inbox categories** (help icon), Search; **Calendar List** → About, Connection, **Time & limits** (date + time + same profile time-zone hint). **Annotation notes** and **regions** include **Stack order** (**Move back** / **Move forward**) at the top of **Note appearance** and **Region appearance**, backed by persisted `z_index` (see **Editor-only annotations** in [ARCHITECTURE.md](ARCHITECTURE.md)); UI is shared via [`AnnotationStackOrderControls.tsx`](../frontend/src/components/workflow-editor/AnnotationStackOrderControls.tsx). **Last Run** uses the same shell class (`INSPECTOR_SURFACE_CLASS`) so it matches those wells. Inside **Last Run**, section order is **Output** (text, dictionary / **Output explorer** when `details.output_explorer` is present, etc.) → **Inputs** (effective values merged via [`lastRunInputsPayload`](../frontend/src/components/workflow-editor/lastRunInputsPayload.ts), shown as **one [`OutputExplorer`](../frontend/src/components/workflow-editor/OutputExplorer.tsx) card per key** via [`RunInputsExplorer`](../frontend/src/components/workflow-editor/RunInputsExplorer.tsx) + [`clientOutputExplorerForInputField`](../frontend/src/domain/clientOutputExplorerForInputField.ts)) → optional **Skill diagnostics**. The **Run logs** tab uses the same **Output** then **Inputs** order for each step.

**Pre-run required inputs:** When **Run** is clicked and the **Start** node still has missing required values, the editor shows a **stepped wizard** over the canvas (dimmed backdrop, centered `mw-card` panel, **Continue** / **Run** / **Back** / **Cancel**)—same overlay feel as other workflow-editor dialogs—collecting **one Start slot per step** in list order before streaming execution. In the **Start** inspector, **list** / **dictionary** fields stay visually **empty** when the stored value is **`null`** (unset → wizard); **`[]` / `{}`** appear only after the user enters JSON. **Boolean** uses **At run time…** for **`null`**. The wizard’s list/dictionary steps use the same empty-vs-JSON behavior. **Normalize JSON** (explicit action, no auto-paste mutation) uses [`normalizeText`](../frontend/src/domain/normalizeText.ts) on List/Dictionary primitives, Start list/dict slots, and wizard list/dict steps to strip markdown fences / `---` lines and extract balanced JSON when needed. Each **Workflow inputs** slot **Key** must be **non-empty** and **unique** among slots (it becomes the right-side data handle id and persisted `source_handle`); **`signal_out`** and **`trigger`** are **reserved** for control-flow handles and are rejected inline ([`startSlotKeyHelpers.ts`](../frontend/src/components/workflow-editor/startSlotKeyHelpers.ts)).

**Broadcast Message modal:** The **Broadcast Message** utility pauses streaming **Run** execution until the user clicks **Continue** ([`BroadcastMessageModal.tsx`](../frontend/src/components/workflow/BroadcastMessageModal.tsx)). The overlay uses a dimmed full-viewport backdrop, centered `mw-card`, and a single primary action. Each segment gets a subtle severity accent (`info` → primary, `notice` → amber top border, `success` → success tokens) without loud alert chrome. Optional **title** per segment; multiple segments in one run appear as numbered sections in one dialog. Body text uses plain `whitespace-pre-wrap` unless Markdown is auto-detected (headings, lists, fences), in which case **react-markdown** + **remark-gfm** render inside `prose-sm dark:prose-invert`. **Sandbox** uses the same component post-tick with optional **source** chips (creature, region trigger, fixture).

**Canvas selection:** The node or edge that is open in the Explorer is also indicated on the graph with a **palette-tinted**, softly **animated glow** (stroke-colored halo), plus a subtle mix of the system **`primary`** token for readability—see [`index.css`](../frontend/src/index.css) (`mw-flow-node-selected`, `mw-flow-edge-selected`). While a run is **in progress**, the **active** node keeps the existing **primary** pulse/highlight and does **not** stack the selection halo so the two states stay distinct. **Output explorer** and **Run inputs explorer** (Last Run / Run logs **Inputs**) use the card row + modal patterns in [`OUTPUT_EXPLORER_UI.md`](OUTPUT_EXPLORER_UI.md).

**Edge Explorer:** Selecting a **connection** uses the same [`InspectorSection`](../frontend/src/components/workflow-editor/InspectorSection.tsx) wells: **Connection** (data type + handle pair), **Source** / **Destination** node summaries, **Last run** (payload inferred from `details.resolved_inputs` on the target’s run row when present, else from the source’s **output** slot), plus **Open full payload view** (modal). Logic lives in [`edgeInspectorUtils.ts`](../frontend/src/components/workflow-editor/edgeInspectorUtils.ts) and [`EdgeInspectorPanel.tsx`](../frontend/src/components/workflow-editor/EdgeInspectorPanel.tsx).

**Control-flow handles (canvas):** Most steps use **trigger** (in) and **`signal_out`** (out) for ordering. **Branching** controls (**Basic Conditional**, **Is?**, **Gt?** / **Lt?** / **Gte?** / **Lte?**, **Between**) also expose **`true`** / **`false`** (or branch) outputs; they include **`signal_out`** so you can chain utilities that should run after the control resolves (in parallel with the active branch). Prefer **branch handles** for branch-only paths; use **`signal_out` → `trigger`** for “always after this step” merges—avoid wiring **both** a branch handle and **`signal_out`** to the **same** downstream **`trigger`** unless you intend the combined `in_degree` semantics. **Stop** is terminal: it has **no** `signal_out` (only **trigger** in and data **inputs**). The executor schedules **`signal_out` → `trigger`** for branching controls in [`executor.py`](../backend/app/domain/workflow_executor/executor.py) (`_decrement_signal_out_triggers`).

**Copy to clipboard (app-wide):** Any control that copies text for the user must **not** call `navigator.clipboard.writeText` directly. Use **`useCopyWithFeedback()`** from [`ClipboardFeedbackContext`](../frontend/src/contexts/ClipboardFeedbackContext.tsx) (wrapped by [`ClipboardFeedbackProvider`](../frontend/src/contexts/ClipboardFeedbackContext.tsx) in [`main.tsx`](../frontend/src/main.tsx)). On success it shows a short **“Copied to clipboard”** toast (bottom center, `role="status"`, `aria-live="polite"`, ~2.5s); on failure **“Could not copy”** (error styling). The actual browser call lives in [`systemClipboard.ts`](../frontend/src/systemClipboard.ts) so tests can `vi.mock` it. Add new Copy icons the same way (e.g. output explorer row/header Copy). For other short status messages (e.g. TTS playback errors), use **`useStatusToast()`** from the same context so styling and timing match. Reserve error styling for **user-visible** failures only—transient media interruptions after playback has started should not alarm the user (see programmatic TTS playback in [`ttsAudioPlayback.ts`](../../frontend/src/domain/ttsAudioPlayback.ts) / workflow docs). Google OAuth toasts in [`App.tsx`](../frontend/src/App.tsx) stay top-right and are separate from this pattern.

### System Tab

**System theme palettes** (API resource `system_palettes`) are named **light + dark** token sets for the whole app—the same **display names and slugs** as workflow presets (**Default**, **Slate**, **Paper**, …). Built-ins are read-only rows (`user_id` null); users can create themes, import/export JSON, and apply one with **Use as my theme** in the editor or the **check (apply) icon** on the left list row when hovering (stores `User.settings.system_palette_id` as a UUID string). **Clear active theme preset** removes that id so only defaults + optional overrides apply.

**Resolution** (see [`frontend/src/contexts/ThemeContext.tsx`](../frontend/src/contexts/ThemeContext.tsx)) for the current light/dark mode:

1. Shipped defaults from [`frontend/src/theme/defaults.ts`](../frontend/src/theme/defaults.ts)
2. The active system palette’s tokens for that mode (if `system_palette_id` is set and the row loads)
3. Optional partial overrides in `User.settings.system_colors` for that mode (legacy fine-grained tweaks on top of a preset)

Definitions for built-ins live in [`backend/app/domain/system_palette_defaults.py`](../backend/app/domain/system_palette_defaults.py); startup sync mirrors workflow palettes (`SystemPaletteService.initialize_builtin_system_palettes`). JSON import/export: [`frontend/src/domain/systemPaletteImportExport.ts`](../frontend/src/domain/systemPaletteImportExport.ts) (`schema_version`, `name`, `colors: { light, dark }`, optional `slug` on export; import ignores `slug` for creates).

`User.settings.system_colors` shape (partials allowed per mode):

```json
{
  "light": {
    "page_bg": "#f9fafb",
    "sidebar_bg": "#ffffff",
    "card_bg": "#ffffff",
    "card_bg_alt": "#f3f4f6",
    "text_primary": "#111827",
    "text_secondary": "#4b5563",
    "border": "#e5e7eb",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_muted": "#eff6ff",
    "success": "#16a34a",
    "success_muted": "#dcfce7",
    "error": "#dc2626",
    "error_muted": "#fee2e2"
  },
  "dark": {
    "page_bg": "#030712",
    "sidebar_bg": "#111827",
    ...
  }
}
```

## System Color Tokens


| Token            | Purpose                 |
| ---------------- | ----------------------- |
| `page_bg`        | Main page background    |
| `sidebar_bg`     | Sidebar background      |
| `card_bg`        | Modals, panels          |
| `card_bg_alt`    | Secondary panels        |
| `text_primary`   | Headings, body text     |
| `text_secondary` | Muted text              |
| `border`         | Dividers, input borders |
| `primary`        | Accent, buttons         |
| `primary_hover`  | Button hover state      |
| `primary_muted`  | Selected nav background |
| `success`        | Success text            |
| `success_muted`  | Success background      |
| `error`          | Error text              |
| `error_muted`    | Error background        |

### Applying tokens in React / Tailwind

[`ThemeContext.tsx`](../frontend/src/contexts/ThemeContext.tsx) pushes resolved hex values to CSS variables `--mw-page-bg`, `--mw-text-primary`, etc., on `<html>`. [`tailwind.config.js`](../frontend/tailwind.config.js) exposes them as `theme.extend.colors.mw.*`, so you can use classes such as `bg-mw-page`, `bg-mw-sidebar`, `bg-mw-card`, `text-mw-text-primary`, `text-mw-text-secondary`, `border-mw-border`, and `text-mw-primary` / `bg-mw-primary-muted` for chrome.

Use these for **app shell, modals, login, workflow editor layout, and neutral node framing**. Shared constants **`MANAGER_INPUT_CLS`** / **`MANAGER_LABEL_CLS`** in [`frontend/src/components/managerShellStyles.ts`](../frontend/src/components/managerShellStyles.ts) keep list+detail modals (Personas, Structures, Palettes, admin users, My Settings, **Replays**) aligned with the active theme. For multi-line inputs that hold arbitrarily long content (e.g. Persona **System Prompt** in [`PersonaManager`](../frontend/src/components/PersonaManager.tsx)), layer **`resize-y`** plus a **`min-h-[…]`** floor on top of `MANAGER_INPUT_CLS` so users can grow the field vertically without shrinking below a sensible default; single-line fields stay **`resize-none`**. The same pattern appears elsewhere (e.g. [`MarkdownRawPreview`](../frontend/src/components/MarkdownRawPreview.tsx), [`WorkflowImportModal`](../frontend/src/components/workflow-editor/WorkflowImportModal.tsx), [`WorkspacePipelinePanel`](../frontend/src/components/WorkspacePipelinePanel.tsx)). [`ManagerModal`](../frontend/src/components/ManagerModal.tsx) supports **`maxWidth="full"`** for a viewport-sized panel, optional **`leadingSlot`** (e.g. **Back** left of the title), or optional **`enableFullscreen`** (header control) when `maxWidth` is not `full`. **Replays** ([`RunExploreModal`](../frontend/src/components/RunExploreModal.tsx)) uses **`maxWidth="full"`** by default so the replay canvas is usable without an extra fullscreen click. Fixed Tailwind palettes like `bg-gray-50` or `text-gray-700` on those surfaces **bypass** the user’s system theme (`settings.system_palette_id`).

**Inline delete confirmation:** For list items with a delete action (Personas, Structures, Documents, **Replays**), use inline **Delete** / **Cancel** buttons instead of `window.confirm`. The first click on the trash icon reveals the buttons in place; **Cancel** dismisses, **Delete** performs the operation. Implementation: `deletingId` (or `deletingRunId` in Replays) state; conditional render of trash icon vs Delete/Cancel buttons.

**List multi-select (Documents and Replays):** Per-row checkboxes; plain row click selects one item and drives the detail pane; **Cmd/Ctrl** + click toggles membership in the selection set while still focusing the clicked row. When more than one row is selected, show a compact action strip (**N selected**, **Delete selected**, then confirm **Delete all** / **Cancel**); hide per-row trash in that mode to avoid mixed destructive affordances. **Replays** additionally exposes **All loaded** in the list header (select every run in the current API page). See [`DocumentManager.tsx`](../frontend/src/components/DocumentManager.tsx) and [`RunExploreModal.tsx`](../frontend/src/components/RunExploreModal.tsx).

**Manager detail-pane hydration:** When a list endpoint omits heavy fields (see [ARCHITECTURE.md](ARCHITECTURE.md) — *Slim list schemas*), managers populate **Name** / **Description** / metadata immediately from the list row but fetch **`GET /<resource>/{id}`** for the heavy field (e.g. **Manage Documents** **Body**) on focus. Use a **focus-token ref** that increments per selection and gates the response so a slow row's body cannot land in the editor after the user has clicked a different row. While the fetch is in flight, surface a subdued inline status (e.g. *Loading body…*) next to the field label rather than blocking the editor — Name and Description are already correct. Pattern: [`DocumentManager.tsx`](../frontend/src/components/DocumentManager.tsx) (`hydrateFocusBody`). Side-band metadata (e.g. **Documents → Metadata** tab token counts) follows the same focus-token + per-id cache pattern via `loadMetadata` against **`GET /documents/{id}/metadata`**, with cache invalidation on save and a "Save the document to see token count" hint while creating an unsaved row.

**System theme vs workflow palette:** The **System** tab (and `system_palette_id`) controls **semantic UI chrome**. The **Editor** tab and `palette_id` on workflows control **step family colors** (handles, edges, colored headers on nodes)—keep that data on the workflow palette; do not replace those accents with `mw-*` or the graph loses its color language.

## Editor Color Tokens

Palette entries are flat string keys → hex colors in `Palette.colors`. They color **handles, edges, and node borders** in the workflow editor. **Default hex values** are the single source of truth in `[backend/app/domain/palette_defaults.py](../backend/app/domain/palette_defaults.py)` (`DEFAULT_PALETTE_COLORS`), mirrored in `[frontend/src/domain/paletteDefaults.ts](../frontend/src/domain/paletteDefaults.ts)` (`WORKFLOW_PALETTE_COLORS`). Resolution: specific key → optional **step-family** key (below) → built-in default for that key → `any` (`resolveWorkflowPaletteColor`).


| Token                | Purpose                                      |
| -------------------- | -------------------------------------------- |
| `string`             | String primitive                             |
| `list`               | List primitive                               |
| `dictionary`         | Dictionary primitive                         |
| `structure`          | Structure primitive                          |
| `boolean`            | Boolean primitive                            |
| `int`                | Int primitive                                |
| `datetime`           | DateTime primitive                           |
| `any`                | Fallback when no more specific color applies |
| `workflow`           | Sub-workflow (Workflow) node                 |
| `simple_llm_call`    | Simple LLM Call skill                        |
| `fetch_url`          | Fetch URL skill                              |
| `capture_url_snapshot` | URL snapshot (Playwright) skill              |
| `html_parse_basic`   | HTML Parse (basic) utility                   |
| `google_docs_parse_document` | Google Docs Parse utility            |
| `list_to_string`     | List to String utility                       |
| `string_to_list`     | String to List utility                       |
| `prepend_text`       | Prepend Text utility                         |
| `string_trunc`       | String Trunc utility                         |
| `len_from_list`      | Len from List utility                        |
| `random_item_from_list` | Random item from list utility             |
| `int_to_string`      | Int to String utility                        |
| `list_item_by_index` | List Item by Index utility                   |
| `dictionary_value_by_key` | Dictionary Value by Key utility          |
| `add_to_list` | Add to List utility (append value to list; carry in For loop body) |
| `add_days` | Add days utility (shift RFC3339 instant by signed whole days) |
| `basic_conditional`  | Basic Conditional control                    |
| `is_control`         | Is? control                                  |
| `gt_control`         | Gt? comparison control                       |
| `lt_control`         | Lt? comparison control                       |
| `gte_control`        | Gte? comparison control                      |
| `lte_control`        | Lte? comparison control                      |
| `and_control`        | And (boolean combinator)                     |
| `or_control`         | Or (boolean combinator)                      |
| `xor_control`        | Xor (boolean combinator)                     |


**Optional step-family keys** (same strings as step `kind` in the manifest). When set on a palette, they apply to every step in that family **unless** a more specific per-step key above is set on the palette: `primitive`, `skill`, `utility`, `control`.

**Editor-only keys** (used for React Flow handle semantics; not required in API palette payloads; defaults in `EDITOR_NODE_PALETTE_EXTRA` in `paletteDefaults.ts`): `start`, `stop`, `trigger`, `signal`.

## Context help (info pop-outs)

For **dense inspector fields** or **syntax users may not know** (API query strings, RFC3339, etc.), use a small **info** control that opens a **compact dialog**—not [`ManagerModal`](../frontend/src/components/ManagerModal.tsx), which is for full-page managers.

**Implementation:** [`ContextHelpModal`](../frontend/src/components/ContextHelpModal.tsx) — `lucide-react` **Info** trigger beside the label, `aria-label` / `aria-haspopup="dialog"`, overlay **`role="dialog"`** with **`aria-modal="true"`** and **`aria-labelledby`** on the title; backdrop and **Esc** close; **`max-w-lg`** and scrollable body so copy stays roughly **one screen**. Body content can live in a sibling module (e.g. [`gmailQueryHelpContent.tsx`](../frontend/src/components/workflow-editor/gmailQueryHelpContent.tsx)) to keep parents thin.

**Content:** Short bullets, **`font-mono`** examples, one warning line if inputs can conflict, and **links** to canonical external docs. Avoid long tutorials—defer to product docs and vendor references.

## External links (new tab / leave site)

**Do not** use a raw `<a href="https://…" target="_blank">` for outbound documentation or vendor pages when the user may not expect to leave Mind Weave.

**Pattern:** [`ExternalLink`](../frontend/src/components/ExternalLink.tsx) — always opens in a **new tab** (`noopener` / `noreferrer`), shows a small **outbound icon** (lucide `ExternalLink`) beside the label, and adds screen-reader text **(opens in new tab)**.

**Confirmation:** For **cross-origin** `http:` / `https:` URLs, the first click opens a compact **“Open external site?”** dialog showing the full URL; **Continue** opens the tab, **Cancel** / backdrop / **Esc** dismiss. Same-origin links behave like normal anchors (no confirmation).

**Override:** Set **`skipLeaveConfirmation`** when an extra click would be needless friction (e.g. a link the user already opted into, or highly repetitive doc hops inside help). Prefer the default (confirm) for first-line outbound links in primers and settings.

## Gmail / Calendar style date boundaries (skills)

For **Gmail List** **After** / **Before** (RFC3339 stored on the node; server maps to Gmail **`after:`** / **`before:`** using the **UTC calendar day** of the instant):

- Use the shared **[`GmailBoundaryDateFields`](../frontend/src/components/workflow-editor/GmailBoundaryDateFields.tsx)** pattern: **`<input type="date">`**, shared **IANA timezone** `<select>` (default **system** via `Intl.DateTimeFormat().resolvedOptions().timeZone`; full list via `Intl.supportedValuesOf('timeZone')` with a static fallback), **read-only preview** of the Gmail `YYYY/MM/DD` clause, and a **collapsed** “Edit raw RFC3339” block.
- Encode **local start-of-day** with **[`gmailRfc3339Date.ts`](../frontend/src/domain/gmailRfc3339Date.ts)** — **Intl + `Date` only** (no date npm package); keep behavior aligned with [`backend/app/integrations/gmail_query.py`](../backend/app/integrations/gmail_query.py).

## Adding New Tokens

1. Add the token to `frontend/src/theme/defaults.ts` (`SystemColorToken` type, `DEFAULT_SYSTEM_COLORS_LIGHT`, `DEFAULT_SYSTEM_COLORS_DARK`, `SYSTEM_COLOR_TOKENS`)
2. Add to `frontend/tailwind.config.js` (`colors.mw`)
3. Add fallbacks in `frontend/src/index.css` (`:root` and `.dark`)
4. Update `ThemeContext` if needed (it reads from defaults automatically)
5. Use in components: `bg-mw-page`, `text-mw-primary`, etc.

