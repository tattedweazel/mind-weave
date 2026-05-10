# Contributing to Mind Weave

Thanks for your interest in improving Mind Weave. This document is a short entry point; deeper detail lives in the linked docs and package READMEs.

## Before you start

- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for layering, single sources of truth, and how HTTP errors flow to the UI.
- Read **[docs/NODE_TAXONOMY.md](docs/NODE_TAXONOMY.md)** when you add palette steps so **Skills vs Utilities vs Controls** land in the right category before you edit executor code.
- For **what behavior must stay covered by tests**, see [docs/Audits/TEST_AUDIT.md](docs/Audits/TEST_AUDIT.md). When you change routes, auth, or user-visible behavior, update that mapping.
- For style and cohesion, see [docs/Audits/CODE_QUALITY_AND_STYLE_AUDIT.md](docs/Audits/CODE_QUALITY_AND_STYLE_AUDIT.md).

## Development setup

- **Recommended — start API + SPA together:** from the repo root run **`make dev`** (`Makefile` invokes **`./startdev.sh`**). Prerequisites: **`uv`** + **`backend/`** synced (`uv sync --extra dev` from `backend/`, or **`uv sync --project backend --extra dev`** from root), **`npm install`** inside **`frontend/`** once so `node_modules` exists. **`Ctrl+C` stops both** processes. Details: **[README.md — Quickstart](README.md#quickstart)** and **[README.md — Troubleshooting](README.md#troubleshooting)**.
- **Backend only:** Python **3.11+**, [`uv`](https://docs.astral.sh/uv/). The installable project is under **`backend/`** only (there is no repo-root `pyproject.toml`). From the repo root you can use `uv --project backend …` or `cd backend` then `uv sync`, `uv run pytest`, etc. See [backend/README.md](backend/README.md) and [README.md](README.md).
- **Frontend only:** Node.js (see [frontend/README.md](frontend/README.md)), `cd frontend && npm install`; **`npm run dev`** vs **`npm run dev:lan`** per package README when not using **`make dev`**.
- **Optional:** [services/stt-bridge/README.md](services/stt-bridge/README.md) and [services/tts-bridge/README.md](services/tts-bridge/README.md) for local speech bridges.

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
