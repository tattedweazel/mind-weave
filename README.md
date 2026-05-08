# Mind Weave Application

Mind Weave is a full-stack workflow application that interfaces with local LLMs (e.g. LM Studio). Users create **Personas** (system prompts for reuse) and build **Workflows** as visual DAGs. Workflows execute against the LLM, with Primitives (String, List, Dictionary, Structure, Boolean, Int), **Skills** (Simple LLM Call and future external capabilities), Utilities (List to String, String to List, Prepend Text, Len from List, Int to String, List Item by Index, Dictionary Value by Key), and Controls (Basic Conditional, Is?, numeric comparisons Gt/Lt/Gte/Lte, boolean combinators And/Or/Xor) providing inputs and flow logic. It provides a React-based frontend and a FastAPI backend.

## Architecture at a Glance

- **Users** — Authenticated accounts (short-lived access JWT in HttpOnly cookies plus refresh rotation; the bundled SPA uses cookies only; optional `Authorization: Bearer` for non-browser API clients). Bootstrap admin via CLI or opt-in local flag — see [backend/README.md](backend/README.md#important-notes-on-authentication).
- **Personas** — System prompts + optional default model (custom or system). Used as a prompt library; users can copy prompts into Simple LLM Call nodes.
- **Palettes** — Configurable color mappings for workflow step types. Canonical keys are [`DEFAULT_PALETTE_COLORS`](backend/app/domain/palette_defaults.py) in `palette_defaults.py` (primitives including `boolean`/`int`, utilities, skills, branching controls, comparison keys such as `gt_control`, logic keys `and_control`/`or_control`/`xor_control`, `workflow`, `any`, etc.). Workflows select a Palette to color handles, edges, and node borders by type. The Palette Manager Editor tab can **export** and **import** workflow palette JSON (`schema_version`, `name`, `colors`) for sharing; see [frontend/README.md](frontend/README.md).
- **WorkflowDefinitions** — Named DAGs of graph nodes (Start, Stop, Primitives, Skills, Utilities, Controls).
- **Primitives** — Static inputs: String, List, Dictionary, Structure, Boolean, Int.
- **Skills** — **Simple LLM Call** (`simple_llm_call`), **Multimodal LLM** (`multimodal_llm`; Persona + image artifacts from **`url_snapshot_artifacts`**, OpenAI-style vision messages to LM Studio), **Text-to-Speech** via a local TTS bridge (`text_to_speech`), **Voice input** / speech-to-text via a local STT bridge (`transcribe_audio`; **streamed Run** from the editor), **Fetch URL** (`fetch_url`; HTTP GET/… on the API server, dictionary output, optional per-user response cache), **URL snapshot** (`capture_url_snapshot`; headless Chromium screenshot + stored PNG artifact, optional cache), plus Gmail and Calendar list skills. See [docs/WORKFLOW_TOOL_INVENTORY.md](docs/WORKFLOW_TOOL_INVENTORY.md) and [docs/WORKFLOW_SKILLS.md](docs/WORKFLOW_SKILLS.md).
- **Utilities** — List to String (list → JSON string for prompts), String to List (JSON array string → list), Prepend Text (prepend with optional blank line), Len from List (list → int length), Int to String (int → decimal string), List Item by Index (index + list → item), Dictionary Value by Key (key + dictionary → typed value; optional fallback when the key is missing or the value is null).
- **Controls** — Basic Conditional (condition → True/False branches), Is? (equality on two inputs → True/False branches), Gt/Lt/Gte/Lte? (ordered compare on two inputs → True/False branches), And/Or/Xor (two booleans → single boolean output for downstream wiring).

## Adding a New Skill, Utility, or Control

When adding a new workflow **skill** (e.g. Simple LLM Call — `kind: "skill"` + `skill_type`), **utility** (e.g. List to String), or **control** (e.g. Basic Conditional), follow this checklist:

1. **Backend**: Add domain type, workflow executor handler, palette color (if a new handle semantic), and migration for stored graphs if the persisted shape changes
2. **Frontend**: Add types, node component, palette item, conversions, inspector
3. **Palette**: Add the node's color key to `palette_defaults.py`, `paletteDefaults.ts`, PaletteManager, and migrations as needed
4. **Tests**: Add workflow executor tests (mock external calls) and update API palette tests
5. **Documentation**: Update all READMEs with the new node and palette key

See [backend/README.md](backend/README.md#adding-a-new-utility) and [frontend/README.md](frontend/README.md#adding-a-new-utility) for detailed steps. Skills use `kind: "skill"` and `skill_type`. Controls use `kind: "control"` and `control_type` (e.g. `basic_conditional`).

## Project Structure

The project is divided into two main components:

- **[Backend Architecture & Setup](./backend/README.md)** — Python FastAPI server, database management, workflow execution, LLM provider integration, and setup instructions.
- **[Frontend Architecture & Setup](./frontend/README.md)** — Vite/React application structure, Workflow Editor, authentication flow, and setup instructions.

Please refer to the respective documentation files in their directories for more specific instructions and architecture overviews.

### Python backend and `uv`

The installable Python package lives under **`backend/`** only — there is **no** `pyproject.toml` at the repository root. `uv` looks for that file in the current directory (and parents), so commands like `uv add` run **from the repo root** will fail with “No `pyproject.toml` found” unless you point at the backend project.

Use either:

- **`cd backend`** then `uv sync`, `uv add …`, `uv run …`, or
- From the repo root: **`uv --project backend sync`**, **`uv add --project backend <package>`**, **`uv run --project backend pytest`**, etc. (see `uv --help`).

**Convention — dev server:** from `backend/`, **`uv run python -m fastapi dev app/main.py`**. From the repo root: **`uv run --project backend python -m fastapi dev app/main.py`**. Do not rely on bare `fastapi dev` (wrong interpreter on many setups).

To reach the app from other devices on your LAN (phones, another PC): the API must bind with **`--host 0.0.0.0`** and **`CORS_ORIGINS` / `TRUSTED_HOSTS` / `FRONTEND_URL`** in the backend `.env` must match your LAN address; the SPA needs **`npm run dev:lan`** and **`VITE_API_BASE`** pointing at that same host. Step-by-step walkthrough: **[LAN / same-network devices](frontend/README.md#lan--same-network-devices)** in [frontend/README.md](frontend/README.md); backend summary: [Same-network (LAN) access](backend/README.md#same-network-lan-access) in [backend/README.md](backend/README.md).

**Google OAuth, HTTPS, domain, or tunnel** (when LAN IPs are not enough): **[docs/DEPLOYMENT_AND_NETWORK.md](docs/DEPLOYMENT_AND_NETWORK.md)**.

See [backend/README.md](backend/README.md) for environment variables, migrations, and the dev server.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for layering, DRY boundaries (palette defaults, backend `schemas` package for Pydantic models, executor layout), and HTTP error handling in the UI.

## Testing & regression confidence

Backend pytest suites are extensive. **This project does not use a line-coverage target**; what matters is that important behavior is covered and recorded. **Line coverage is not the same as “core behavior covered.”** See [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md) for the capability → test matrix and how to keep it current when the API changes. For README vs shipped-code drift and the documentation audit process, see [docs/Audits/DOCUMENTATION_AUDIT.md](docs/Audits/DOCUMENTATION_AUDIT.md). For a recorded pre-public checklist (dependency scans, optional coverage reports, git squash recipe), see [docs/Audits/PUBLIC_RELEASE_PASS.md](docs/Audits/PUBLIC_RELEASE_PASS.md).

## Releases & upgrades

See [CHANGELOG.md](CHANGELOG.md) for operator-facing release notes and [docs/OPERATIONS.md](docs/OPERATIONS.md) for deployment runbook detail (JWT upgrades, multi-instance rate limits).
