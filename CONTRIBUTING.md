# Contributing to Mind Weave

Thanks for your interest in improving Mind Weave. This document is a short entry point; deeper detail lives in the linked docs and package READMEs.

## Before you start

- Read [docs/RUNTIME_ARCHITECTURE.md](docs/RUNTIME_ARCHITECTURE.md) for how the SPA, API, executor, SSE, and persistence fit together at runtime.
- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for layering, single sources of truth, and how HTTP errors flow to the UI.
- Read **[docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)** when you add palette steps so **Skills vs Utilities vs Controls** land in the right category before you edit executor code.
- For **what behavior must stay covered by tests**, see [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md). When you change routes, auth, or user-visible behavior, update that mapping.
- For style and cohesion, see [docs/Audits/CODE_QUALITY_AND_STYLE_AUDIT.md](docs/Audits/CODE_QUALITY_AND_STYLE_AUDIT.md).

## Development setup

- **Recommended — start API + SPA together:** from the repo root run **`make dev`** (`Makefile` invokes **`./startdev.sh`**). Prerequisites: **`uv`** + **`backend/`** synced (`uv sync --extra dev` from `backend/`, or **`uv sync --project backend --extra dev`** from root), **`npm install`** inside **`frontend/`** once so `node_modules` exists. **`Ctrl+C` stops both** processes. Details: **[README.md — Quick Start](README.md#quick-start)** and **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** (first-time install and env depth); troubleshooting: **[docs/OPERATIONS.md — Local development troubleshooting](docs/OPERATIONS.md#local-development-troubleshooting)**.
- **Backend only:** Python **3.11+**, [`uv`](https://docs.astral.sh/uv/). The installable project is under **`backend/`** only (there is no repo-root `pyproject.toml`). From the repo root you can use `uv --project backend …` or `cd backend` then `uv sync`, `uv run pytest`, etc. See [backend/README.md](backend/README.md) and [README.md](README.md).
- **Frontend only:** Node.js (see [frontend/README.md](frontend/README.md)), `cd frontend && npm install`; **`npm run dev`** vs **`npm run dev:lan`** per package README when not using **`make dev`**.
- **Windows / non-Bash:** There is no first-class `Makefile`/`startdev.sh` story outside a POSIX shell today. Run **`startdev.sh`** from Git Bash or WSL, or start **backend** and **frontend** in two terminals using the same commands the script runs (`uv run python -m fastapi dev app/main.py` under `backend/`, `npm run dev:lan` under `frontend/`) and set **`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, **`FRONTEND_URL`**, and **`VITE_API_BASE`** yourself—see [README.md — Quick Start](README.md#quick-start), **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**, and [frontend/README.md — LAN](frontend/README.md#lan--same-network-devices).
- **Optional:** [services/stt-bridge/README.md](services/stt-bridge/README.md) and [services/tts-bridge/README.md](services/tts-bridge/README.md) for local speech bridges.

## Manual development (advanced)

Run API and SPA in **two terminals** only when debugging one side or customizing env beyond **`make dev`**.

The project has two runnable packages:

- **[Backend Architecture & Setup](backend/README.md)** — Python FastAPI server, database management, workflow execution, LLM provider integration.
- **[Frontend Architecture & Setup](frontend/README.md)** — Vite/React application structure, Workflow Editor, authentication flow.

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

## Checks to run locally

When you touch **`startdev.sh`**, run **`shellcheck startdev.sh`** (Homebrew **`brew install shellcheck`**).

From **`backend/`**:

- `uv run pytest -q` (or `uv run pytest -q -W error::ResourceWarning` for stricter warnings)
- `uv run ruff check app tests`

From **`frontend/`**:

- `npm run lint`
- `npm run test`
- `npm run build`

Optional coverage report (no global percentage gate in this repo): `npm run test:cov`. See [TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md).

Bridge packages (if you touch them):

- `cd services/stt-bridge && uv run pytest -q`
- `cd services/tts-bridge && uv run pytest -q`

## Tests and external services

**Default tests must not** call real LLMs, Google OAuth APIs, AssemblyAI, LM Studio, or the STT/TTS bridges. Use mocks, `httpx.MockTransport`, patches, and the patterns already used in `backend/tests/`. Optional E2E modules that hit real services are **opt-in** via environment flags (see [TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md)).

## Pull requests

- Keep changes **focused** on the issue or feature; avoid drive-by refactors.
- Update **documentation** when behavior or operator-facing setup changes (READMEs, `docs/`, audits as appropriate).
- Large **workflow editor** or lazy-loaded views may rely on unit tests and manual QA where [TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md) already defers full E2E automation.

## License

By contributing, you agree that your contributions will be licensed under the **Apache License 2.0** ([LICENSE](LICENSE)).
