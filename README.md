# Mind Weave Application

## What Mind Weave is

Mind Weave is a full-stack workflow application that interfaces with local LLMs (for example LM Studio). Users create **Personas** (system prompts for reuse) and build **Workflows** as visual DAGs. Execution combines **Primitives**, **Skills**, **Utilities**, and **Controls**, with palettes for canvas semantics and nested **Workflow** steps for reuse. Product overview aimed at builders and operators: [docs/MIND_WEAVE_ONE_PAGE.md](docs/MIND_WEAVE_ONE_PAGE.md).

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

## Architecture at a Glance

- **Users** — Authenticated accounts (short-lived access JWT in HttpOnly cookies plus refresh rotation; the bundled SPA uses cookies only; optional `Authorization: Bearer` for non-browser API clients). Bootstrap admin via CLI or opt-in local flag — see [backend/README.md](backend/README.md#important-notes-on-authentication).
- **Personas** — System prompts + optional default model (custom or system). Used as a prompt library; users can copy prompts into Simple LLM Call nodes.
- **Palettes** — Configurable color mappings for workflow step types. Canonical keys are [`DEFAULT_PALETTE_COLORS`](backend/app/domain/palette_defaults.py) in `palette_defaults.py` (primitives including `boolean`/`int`, utilities, skills, branching controls, comparison keys such as `gt_control`, logic keys `and_control`/`or_control`/`xor_control`, `workflow`, `any`, etc.). **Effective canvas colors** come from **`GET /api/v1/palettes/resolve`** (server precedence: `workflow.palette_id` → preferred editor palette → default). Workflows select a stored `palette_id` from **Configure → Palettes**. The Palette Manager Editor tab can **export** and **import** workflow palette JSON (`schema_version`, `name`, `colors`) for sharing; see [frontend/README.md](frontend/README.md).
- **WorkflowDefinitions** — Named DAGs of graph nodes (Start, Stop, Primitives, Skills, Utilities, Controls).
- **Primitives** — Static inputs: String, List, Dictionary, Structure, Document, Boolean, Int, DateTime, Image, Gmail-shaped payloads, Sandbox-oriented shapes, … (see palettes + [shared/workflow_graph_step_kinds.json](shared/workflow_graph_step_kinds.json)).
- **Skills** — **Simple LLM Call** (`simple_llm_call`), **Multimodal LLM** (`multimodal_llm`; Persona + image artifacts from **`url_snapshot_artifacts`**, OpenAI-style vision messages to LM Studio), **Text-to-Speech** via a local TTS bridge (`text_to_speech`), **Voice input** / speech-to-text via a local STT bridge (`transcribe_audio`; **streamed Run** from the editor), **Fetch URL** (`fetch_url`; HTTP GET/… on the API server, dictionary output, optional per-user response cache), **URL snapshot** (`capture_url_snapshot`; headless Chromium screenshot + stored PNG artifact, optional cache), Gmail and Calendar list skills, transcription providers—see [docs/WORKFLOW_TOOL_INVENTORY.md](docs/WORKFLOW_TOOL_INVENTORY.md) and [docs/WORKFLOW_SKILLS.md](docs/WORKFLOW_SKILLS.md).
- **Utilities** — List ↔ string conversions, truncation, indexing, dictionary access, HTML parse (**`html_parse_basic`**), document field helpers (including persisted **Load / Upsert Document** — still **`kind: "utility"`**; see taxonomy doc), validation against Structures, integer math, **Add to List**, …
- **Controls** — Basic Conditional (**Is**, numeric comparisons **Gt/Lt/Gte/Lte**, **Between**, **Is Empty?**), **Try / Catch**, **For Loop** / **For Loop End**, boolean combinators **And/Or/Xor/** **Not**.

## Node mental model

Mind Weave groups steps into palette families ([docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)): **utilities** reshape data (*grammar*) and **skills** reach outward (*verbs* — LLMs, HTTP, integrations, bridges). Use the **decision guide** there before editing code when you add a node.

## Adding a New Skill, Utility, or Control

1. **[docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)** — Confirm **kind** / category (utilities vs skills vs controls vs primitives).
2. **Backend**: Add domain type, workflow executor handler, palette color (if a new handle semantic), and migration for stored graphs if the persisted shape changes.
3. **Frontend**: Add types, node component, palette item, conversions, inspector.
4. **Palette**: Add the node's color key to `palette_defaults.py`, `paletteDefaults.ts`, PaletteManager, and migrations as needed.
5. **Tests**: Add workflow executor tests (mock external calls) and update API palette tests.
6. **Documentation**: Update package READMEs, this file’s architecture bullets if capability-facing, `[docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)` if taxonomy guidance changes.

See [backend/README.md](backend/README.md#adding-a-new-utility) and [frontend/README.md](frontend/README.md#adding-a-new-utility) for detailed steps. Skills use `kind: "skill"` and `skill_type`. Controls use `kind: "control"` and `control_type` (e.g. `basic_conditional`).

## Manual development commands (advanced)

Run API and SPA in **two terminals** only when debugging one side or customizing env beyond **`make dev`**.

### Project Structure

The project has two runnable packages:

- **[Backend Architecture & Setup](./backend/README.md)** — Python FastAPI server, database management, workflow execution, LLM provider integration.
- **[Frontend Architecture & Setup](./frontend/README.md)** — Vite/React application structure, Workflow Editor, authentication flow.

See [backend/README.md](backend/README.md#setup--running) and [frontend/README.md](frontend/README.md#setup--running).

### Python backend and `uv`

The installable Python package lives under **`backend/`** only — there is **no** `pyproject.toml` at the repository root. `uv` looks for that file in the current directory (and parents), so commands like `uv add` run **from the repo root** fail with “No `pyproject.toml` found” unless you point at the backend project.

Use either:

- **`cd backend`** then `uv sync`, `uv add …`, `uv run …`, or
- From the repo root: **`uv --project backend sync`**, **`uv add --project backend <package>`**, **`uv run --project backend pytest`**, etc. (see `uv --help`).

**Convention — dev server:** from `backend/`, **`uv run python -m fastapi dev app/main.py`**. From the repo root: **`uv run --project backend python -m fastapi dev app/main.py`**. Do not rely on bare `fastapi dev` (wrong interpreter on many setups). Bind **`--host 0.0.0.0`** only on trusted LANs ([backend/README.md — LAN](backend/README.md#same-network-lan-access), [frontend/README.md — LAN](frontend/README.md#lan--same-network-devices)).

For **hands-on LAN env alignment** (`CORS_ORIGINS`, `TRUSTED_HOSTS`, `FRONTEND_URL`, `VITE_API_BASE`) without **`make dev`**, follow **[LAN / same-network devices](frontend/README.md#lan--same-network-devices)** plus **[Same-network (LAN) access](backend/README.md#same-network-lan-access)**.

**Google OAuth, HTTPS, domain, or tunnel** (when LAN IPs are not enough): **[docs/DEPLOYMENT_AND_NETWORK.md](docs/DEPLOYMENT_AND_NETWORK.md)**.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for layering, DRY boundaries (palette defaults, backend `schemas` package for Pydantic models, executor layout), and HTTP error handling in the UI.

## Troubleshooting

Applies to **`make dev`**, **`./startdev.sh`**, and manual FastAPI + Vite setups.

- **Ports already in use** — **`8000` (FastAPI)** or **`5173` (Vite)**: find listeners (`lsof -nP -iTCP:8000 -sTCP:LISTEN` on macOS; see [backend/README.md — Troubleshooting](backend/README.md#troubleshooting)) and stop the stale process—two servers on one port yields confusing 404/CORS shells.
- **Browser shows CORS or “failed to fetch”** — Ensure the browser origin matches an entry echoed under **CORS allowed origins** — use **`http://127.0.0.1:5173` vs `http://localhost:5173`** consistently after login; mismatched **`VITE_API_BASE`** vs **`CORS_ORIGINS`** is common when mixing origins by hand ([frontend/README.md](frontend/README.md#api-base-url)).
- **Phone / LAN cannot load the UI** — Trust the LAN, confirm **`make dev`** printed a LAN IP for the host machine, firewall allows **8000/5173**, and you used the **`http://<LAN>:…`** URLs on the remote device—not `localhost`.
- **`make dev` + Google OAuth** — Google rejects redirect hosts that are bare **private IPs**; use password login over LAN or a path with a public hostname (**[docs/DEPLOYMENT_AND_NETWORK.md](docs/DEPLOYMENT_AND_NETWORK.md)** — Path B).
- **`uv` fails / “No `pyproject.toml`” from repo root** — Use **`uv --project backend …`** or **`cd backend`** ([CONTRIBUTING.md](CONTRIBUTING.md)).
- **Frontend deps missing / `vite` unknown** — Run **`npm install`** in **`frontend/`** once ([frontend/README.md](frontend/README.md#setup--running)).

Maintainability: **`shellcheck startdev.sh`** should stay clean — run after editing the launcher.

## Testing & regression confidence

Backend pytest suites are extensive. **This project does not use a line-coverage target**; what matters is that important behavior is covered and recorded. **Line coverage is not the same as “core behavior covered.”** See [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md) for the capability → test matrix and how to keep it current when the API changes. For README vs shipped-code drift and the documentation audit process, see [docs/Audits/DOCUMENTATION_AUDIT.md](docs/Audits/DOCUMENTATION_AUDIT.md). For a recorded pre-public checklist (dependency scans, optional coverage reports, git squash recipe), see [docs/Audits/PUBLIC_RELEASE_PASS.md](docs/Audits/PUBLIC_RELEASE_PASS.md).

## License, security, and contributing

Mind Weave is licensed under the [Apache License 2.0](LICENSE). To report security vulnerabilities privately, see [SECURITY.md](SECURITY.md) (GitHub **Security** tab — enable private vulnerability reporting on the repo if needed). For development setup and pull-request expectations, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Releases & upgrades

See [CHANGELOG.md](CHANGELOG.md) for operator-facing release notes and [docs/OPERATIONS.md](docs/OPERATIONS.md) for deployment runbook detail (JWT upgrades, multi-instance rate limits).
