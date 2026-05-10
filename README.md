# Mind Weave

Mind Weave is a full-stack application for **building and running visual workflows** (directed graphs) against **local or self-hosted LLMs**—for example via an OpenAI-compatible server such as **LM Studio**. You wire **data and control flow** on a canvas, execute runs with **live streaming** updates, and **persist** results: named documents, run logs, and **replays** you can inspect step by step. The default posture keeps model traffic on infrastructure **you** control.

For a full product tour of the shell (Build, Workspace, Sandbox, Configure), see **[docs/MIND_WEAVE_ONE_PAGE.md](docs/MIND_WEAVE_ONE_PAGE.md)**.

## Hero workflow

One concrete pattern the system supports end to end:

1. **Fetch URL** — Pull HTML (or JSON) from the web through the API’s **`fetch_url`** skill.
2. **Structured parse** — Use **`html_parse_basic`** or dictionary helpers to turn the response into **chunks** or fields you care about (titles, blocks, links).
3. **Local LLM** — Send that text through **Simple LLM Call** (with a **Persona** or inline prompt) attached to LM Studio or another OpenAI-compatible endpoint.
4. **Structured extraction** — Optionally attach a **Structure** (JSON Schema) so the model returns **entities, action items, or tables** as typed JSON instead of freeform prose.
5. **Persist** — Write results with **Upsert Document** (or related utilities) so **Manage Documents** holds the output for later runs or export.
6. **Inspect** — Use **Build → Replays** (or the stream while the run is live) to see **per-node inputs and outputs** and debug wiring.

A related **fetch → parse** sample ships in the backend scripts—see **[docs/OPERATIONS.md](docs/OPERATIONS.md#debugging-workflows-graphs-and-runs)** (`run_books_toscrape_fetch_parse_sample.py`; no LLM in that script, but you can extend the graph in the editor).

## System architecture (runtime)

At a high level:

- **React + Vite SPA** — Workflow editor, SSE client, replay UI, workspace/sandbox surfaces; talks to the API over HTTP.
- **FastAPI backend** — REST API, auth, validation, persistence.
- **Workflow execution runtime** — Async **DAG** scheduler (**waves**, loops, branching, try/catch), **concurrency limits**, integration with LLM and optional **TTS/STT bridges**.
- **Server-Sent Events** — Build runs stream **node lifecycle** to the browser on **`GET /api/v1/workflow-runs/{run_id}/events`**.
- **Persistence** — Workflow definitions, runs, node logs, documents, palettes, settings (default **SQLite**).

**Diagrams and deeper breakdown:** **[docs/RUNTIME_ARCHITECTURE.md](docs/RUNTIME_ARCHITECTURE.md)**.

## Execution flow (summary)

When you click **Run** on a workflow (streamed Build run):

1. The client **submits** an execution request; the API **validates** the graph and limits.
2. The executor **resolves dependency waves** and schedules ready nodes.
3. **Async steps** run with safe parallelism and **per-category concurrency** caps.
4. **SSE** carries **state updates** to the SPA.
5. The **canvas and explorer** update from the stream.
6. **Logs and status** are **persisted** for **Replays** and support.

Full sequence and component context: **[docs/RUNTIME_ARCHITECTURE.md](docs/RUNTIME_ARCHITECTURE.md#execution-flow-from-run-to-replay)**.

## Quickstart

From the **repository root**:

```bash
git clone https://github.com/tattedweazel/mind-weave.git
cd mind-weave
```

**First-time setup** — install backends for each package:

- **Python / API:** `cd backend && uv sync --extra dev` (`--extra url-snapshot` optional for **URL snapshot** Playwright installs — see [backend/README.md](backend/README.md#workflow-execution-model)).
- **Node / SPA:** `cd frontend && npm install`.

**Daily dev** — one command prints backend + SPA URLs with **LAN-aligned** **`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, **`FRONTEND_URL`**, and **`VITE_API_BASE`** (process-local only — your **`backend/.env`** / **`frontend/.env`** files are never overwritten):

```bash
make dev
```

Equivalent: **`./startdev.sh`** (the Makefile delegates here so orchestration stays in one place).

Open the **frontend URL** echoed by the script (often `http://<LAN-ip>:5173` when your host has a non-loopback LAN address, alongside localhost). **`Ctrl+C` stops both** API and Vite.

**Platforms:** Bash-first (**macOS** / **Linux**). **GNU make** ships on macOS; **Git Bash** or **WSL** against **`./startdev.sh`** often works but is **best-effort** — report gaps if Windows-native shells need first-class support.

**Problems starting the stack?** See **[docs/OPERATIONS.md](docs/OPERATIONS.md#local-development-troubleshooting)**. **Advanced setup** (two terminals, `uv --project backend`, LAN env by hand): **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Core concepts (domain model)

These are the **building blocks** of workflows on the canvas—read this **after** the sections above so names have context.

- **Users** — Authenticated accounts (short-lived access JWT in HttpOnly cookies plus refresh rotation; the bundled SPA uses cookies only; optional `Authorization: Bearer` for non-browser API clients). Bootstrap admin via CLI or opt-in local flag — see [backend/README.md](backend/README.md#important-notes-on-authentication).
- **Personas** — System prompts + optional default model (custom or system). Used as a prompt library; users can copy prompts into Simple LLM Call nodes.
- **Palettes** — Configurable color mappings for workflow step types. Canonical keys are [`DEFAULT_PALETTE_COLORS`](backend/app/domain/palette_defaults.py) in `palette_defaults.py` (primitives including `boolean`/`int`, utilities, skills, branching controls, comparison keys such as `gt_control`, logic keys `and_control`/`or_control`/`xor_control`, `workflow`, `any`, etc.). **Effective canvas colors** come from **`GET /api/v1/palettes/resolve`** (server precedence: `workflow.palette_id` → preferred editor palette → default). Workflows select a stored `palette_id` from **Configure → Palettes**. The Palette Manager Editor tab can **export** and **import** workflow palette JSON (`schema_version`, `name`, `colors`) for sharing; see [frontend/README.md](frontend/README.md).
- **WorkflowDefinitions** — Named DAGs of graph nodes (Start, Stop, Primitives, Skills, Utilities, Controls).
- **Primitives** — Static inputs: String, List, Dictionary, Structure, Document, Boolean, Int, DateTime, Image, Gmail-shaped payloads, Sandbox-oriented shapes, … (see palettes + [shared/workflow_graph_step_kinds.json](shared/workflow_graph_step_kinds.json)).
- **Skills** — **Simple LLM Call** (`simple_llm_call`), **Multimodal LLM** (`multimodal_llm`; Persona + image artifacts from **`url_snapshot_artifacts`**, OpenAI-style vision messages to LM Studio), **Text-to-Speech** via a local TTS bridge (`text_to_speech`), **Voice input** / speech-to-text via a local STT bridge (`transcribe_audio`; **streamed Run** from the editor), **Fetch URL** (`fetch_url`; HTTP GET/… on the API server, dictionary output, optional per-user response cache), **URL snapshot** (`capture_url_snapshot`; headless Chromium screenshot + stored PNG artifact, optional cache), Gmail and Calendar list skills, transcription providers—see [docs/WORKFLOW_TOOL_INVENTORY.md](docs/WORKFLOW_TOOL_INVENTORY.md) and [docs/WORKFLOW_SKILLS.md](docs/WORKFLOW_SKILLS.md).
- **Utilities** — List ↔ string conversions, truncation, indexing, dictionary access, HTML parse (**`html_parse_basic`**), document field helpers (including persisted **Load / Upsert Document** — still **`kind: "utility"`**; see taxonomy doc), validation against Structures, integer math, **Add to List**, …
- **Controls** — Basic Conditional (**Is**, numeric comparisons **Gt/Lt/Gte/Lte**, **Between**, **Is Empty?**), **Try / Catch**, **For Loop** / **For Loop End**, boolean combinators **And/Or/Xor/** **Not**.

**Workspace** (Companion chat, staged workflow capabilities) is a related surface using the same executor for confirmed runs—see **[docs/WORKSPACE.md](docs/WORKSPACE.md)**.

### Node mental model

Mind Weave groups steps into palette families ([docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)): **utilities** reshape data (*grammar*) and **skills** reach outward (*verbs* — LLMs, HTTP, integrations, bridges). Use the **decision guide** there before editing code when you add a node.

## What can I build?

- **AI automation** — Multi-step prompts, chaining LLM outputs into tools and conditions ([docs/WORKFLOW_SKILLS.md](docs/WORKFLOW_SKILLS.md)).
- **Multimodal analysis** — Images + text via **Multimodal LLM** and optional **URL snapshot** artifacts ([docs/WORKFLOW_TOOL_INVENTORY.md](docs/WORKFLOW_TOOL_INVENTORY.md)).
- **Local orchestration** — DAGs that run entirely against **LM Studio** and skills that stay on your network ([docs/RUNTIME_ARCHITECTURE.md](docs/RUNTIME_ARCHITECTURE.md)).
- **Structured extraction** — **Structures** and JSON-shaped LLM outputs ([docs/WORKFLOW_EXPORT_FROM_PROMPT.md](docs/WORKFLOW_EXPORT_FROM_PROMPT.md)).
- **Audio pipelines** — **TTS** / **STT** via optional bridges ([services/tts-bridge/README.md](services/tts-bridge/README.md), [services/stt-bridge/README.md](services/stt-bridge/README.md)).
- **Browser-style capture** — **URL snapshot** (Playwright in the API process when installed) ([docs/OPERATIONS.md](docs/OPERATIONS.md#capture_url_snapshot--playwright)).
- **Chained and nested graphs** — **Workflow** nodes and **Custom Skills** ([docs/MIND_WEAVE_ONE_PAGE.md](docs/MIND_WEAVE_ONE_PAGE.md)).

## Adding a new skill, utility, or control

1. **[docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)** — Confirm **kind** / category (utilities vs skills vs controls vs primitives).
2. **Backend**: Add domain type, workflow executor handler, palette color (if a new handle semantic), and migration for stored graphs if the persisted shape changes.
3. **Frontend**: Add types, node component, palette item, conversions, inspector.
4. **Palette**: Add the node's color key to `palette_defaults.py`, `paletteDefaults.ts`, PaletteManager, and migrations as needed.
5. **Tests**: Add workflow executor tests (mock external calls) and update API palette tests.
6. **Documentation**: Update package READMEs, this file’s core-concept bullets if capability-facing, [`docs/NODE_TAXONOMY.md`](docs/NODE_TAXONOMY.md) if taxonomy guidance changes.

See [backend/README.md](backend/README.md#adding-a-new-utility) and [frontend/README.md](frontend/README.md#adding-a-new-utility) for detailed steps. Skills use `kind: "skill"` and `skill_type`. Controls use `kind: "control"` and `control_type` (e.g. `basic_conditional`).

## Documentation map

| Doc | Purpose |
|-----|---------|
| [docs/MIND_WEAVE_ONE_PAGE.md](docs/MIND_WEAVE_ONE_PAGE.md) | Product narrative and UI walkthrough |
| [docs/RUNTIME_ARCHITECTURE.md](docs/RUNTIME_ARCHITECTURE.md) | Runtime topology, execution flow, diagrams |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Engineering SSOT: layers, executor, palette contracts |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Runbook, debugging, local dev troubleshooting |
| [docs/DEPLOYMENT_AND_NETWORK.md](docs/DEPLOYMENT_AND_NETWORK.md) | HTTPS, OAuth, LAN, nginx, tunnels |
| [backend/README.md](backend/README.md) | API, env, setup |
| [frontend/README.md](frontend/README.md) | SPA, Vite, LAN dev |

**Audits and quality:** [docs/Audits/DOCUMENTATION_AUDIT.md](docs/Audits/DOCUMENTATION_AUDIT.md), [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md), [docs/Audits/PUBLIC_RELEASE_PASS.md](docs/Audits/PUBLIC_RELEASE_PASS.md), and sibling files under `docs/Audits/`.

## Testing and regression confidence

Backend pytest suites are extensive. **This project does not use a line-coverage target**; what matters is that important behavior is covered and recorded. **Line coverage is not the same as “core behavior covered.”** See [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md) for the capability → test matrix and how to keep it current when the API changes. For README vs shipped-code drift and the documentation audit process, see [docs/Audits/DOCUMENTATION_AUDIT.md](docs/Audits/DOCUMENTATION_AUDIT.md).

## License, security, and contributing

Mind Weave is licensed under the [Apache License 2.0](LICENSE). To report security vulnerabilities privately, see [SECURITY.md](SECURITY.md) (GitHub **Security** tab — enable private vulnerability reporting on the repo if needed). For development setup and pull-request expectations, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Releases and upgrades

See [CHANGELOG.md](CHANGELOG.md) for operator-facing release notes and [docs/OPERATIONS.md](docs/OPERATIONS.md) for deployment runbook detail (JWT upgrades, multi-instance rate limits).
