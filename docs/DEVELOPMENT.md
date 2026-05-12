# Mind Weave — local development

Hands-on setup for people **building or customizing** Mind Weave. For onboarding and capability framing, start with the root [README.md](../README.md). For **pull-request process** and review expectations, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## First-time setup

From the **repository root** after `git clone`:

```bash
cd mind-weave
```

- **Python / API:** `cd backend && uv sync --extra dev`  
  Add `--extra url-snapshot` if you need **URL snapshot** Playwright installs — see [backend/README.md — Workflow execution model](../backend/README.md#workflow-execution-model).
- **Node / SPA:** `cd frontend && npm install`.

You can also run **`uv sync --project backend --extra dev`** from the repo root; the installable Python project lives only under **`backend/`** (there is no repo-root `pyproject.toml`).

## Daily development: API + SPA together

**Recommended:** from the repo root:

```bash
make dev
```

Equivalent: **`./startdev.sh`** (the Makefile delegates here so orchestration stays in one place).

The script launches FastAPI and Vite together and prints **backend + frontend** URLs. For this session it sets **LAN-aligned** environment variables **`CORS_ORIGINS`**, **`TRUSTED_HOSTS`**, **`FRONTEND_URL`**, and **`VITE_API_BASE`** in the process environment only — it **does not** overwrite **`backend/.env`** or **`frontend/.env`**.

**Why these variables exist:** the browser origin, API host allowlist, and SPA’s API base URL must agree when you use **localhost vs LAN IP**, phones on the same Wi‑Fi, or split hosts. When you **do not** use `make dev`, you must align them yourself.

**`Ctrl+C` stops both** processes.

**Platforms:** Bash-first (**macOS** / **Linux**). **Git Bash** or **WSL** against **`./startdev.sh`** is **best-effort** on Windows.

**Troubleshooting:** [OPERATIONS.md — Local development troubleshooting](OPERATIONS.md#local-development-troubleshooting).

### Going deeper on environment alignment

- **Frontend LAN / `VITE_API_BASE`:** [frontend/README.md — LAN / same-network devices](../frontend/README.md#lan--same-network-devices)
- **Backend `CORS_ORIGINS`, `TRUSTED_HOSTS`, `FRONTEND_URL`:** [backend/README.md — Same-network (LAN) access](../backend/README.md#same-network-lan-access)
- **HTTPS, OAuth, domains, tunnels:** [DEPLOYMENT_AND_NETWORK.md](DEPLOYMENT_AND_NETWORK.md)

## Manual / two-terminal development

Use **two terminals** when debugging one side only or when you need env beyond what `make dev` exports.

- **Backend (from `backend/`):** `uv run python -m fastapi dev app/main.py`  
  From repo root: `uv run --project backend python -m fastapi dev app/main.py`
- **Frontend (from `frontend/`):** `npm run dev` or `npm run dev:lan` depending on whether you need LAN binding (see frontend README).

Do **not** rely on bare `fastapi dev` without the project interpreter. **Bind `--host 0.0.0.0`** only on trusted LANs.

More detail: [CONTRIBUTING.md — Manual development](../CONTRIBUTING.md#manual-development-advanced).

## Checks to run locally

When you touch **`startdev.sh`**, run **`shellcheck startdev.sh`**.

**Backend** (from **`backend/`**):

- `uv run pytest -q` (optional: `-W error::ResourceWarning` for stricter warnings)
- `uv run ruff check app tests`

**Frontend** (from **`frontend/`**):

- `npm run lint`
- `npm run test`
- `npm run build`

**Palette / OpenAPI drift** (when palette or API schema changes): `npm run verify:palette-types` from **`frontend/`**.

Bridge packages (if you touch them):

- `cd services/stt-bridge && uv run pytest -q`
- `cd services/tts-bridge && uv run pytest -q`

Optional coverage (no global percentage gate): `npm run test:cov` in **`frontend/`**. See [Audits/TEST_AUDIT.md](Audits/TEST_AUDIT.md).

**Policy:** default tests must **not** call real LLMs, OAuth providers, AssemblyAI, LM Studio, or STT/TTS bridges. Use mocks and existing patterns in `backend/tests/`.

## Adding a workflow node

1. **[NODE_TAXONOMY.md](NODE_TAXONOMY.md)** — Confirm **kind** and category (utilities vs skills vs controls vs primitives vs nested **Workflow**).
2. **Backend** — Domain type, workflow executor handler, palette color when semantics require it, migrations if persisted graph shape changes.
3. **Frontend** — Types, node component, palette item, converters, inspector.
4. **Palette** — New color keys in `palette_defaults.py`, `paletteDefaults.ts`, Palette Manager, migrations as needed.
5. **Tests** — Executor and API tests with **mocked** external calls; update palette parity tests when manifests change.
6. **Documentation** — Package READMEs, [NODE_TAXONOMY.md](NODE_TAXONOMY.md) when taxonomy guidance changes, [ARCHITECTURE.md](ARCHITECTURE.md) when SSOT contracts change.

Step-by-step references: [backend/README.md — Adding a new utility](../backend/README.md#adding-a-new-utility), [frontend/README.md — Adding a new utility](../frontend/README.md#adding-a-new-utility). Skills use `kind: "skill"` and `skill_type`. Controls use `kind: "control"` and `control_type` (for example `basic_conditional`).

Condensed implementation checklist: [ARCHITECTURE.md — Adding a workflow node type](ARCHITECTURE.md#adding-a-workflow-node-type-condensed).

## Optional bridges

Local speech processing is optional and documented per service:

- [services/stt-bridge/README.md](../services/stt-bridge/README.md)
- [services/tts-bridge/README.md](../services/tts-bridge/README.md)

## Related documentation

| Doc | Use when |
|-----|----------|
| [RUNTIME_ARCHITECTURE.md](RUNTIME_ARCHITECTURE.md) | How execution and streaming fit together |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, SSOT, executor conventions |
| [OPERATIONS.md](OPERATIONS.md) | Runbooks, debugging, retention |
| [DOMAIN_MODEL.md](DOMAIN_MODEL.md) | Terminology and node families (reader-oriented) |
