---

## last_reviewed: 2026-05-08 (Apache-2.0 LICENSE, SECURITY.md, CONTRIBUTING.md; manifests)
audience: Maintainers preparing a first public GitHub (or similar) push after local-only history
scope: Whole repo: secrets posture, dependency advisories, tests, docs coherence; policy files [LICENSE](../../LICENSE), [SECURITY.md](../../SECURITY.md), [CONTRIBUTING.md](../../CONTRIBUTING.md) are tracked at repo root (2026-05-08).
methodology: Re-run existing audit family ([SECURITY_AUDIT.md](SECURITY_AUDIT.md), [TEST_AUDIT.md](TEST_AUDIT.md), [LIBRARY_USAGE_AUDIT.md](LIBRARY_USAGE_AUDIT.md), [CODE_QUALITY_AND_STYLE_AUDIT.md](CODE_QUALITY_AND_STYLE_AUDIT.md), [MODULAR_DIRECTION_AUDIT.md](MODULAR_DIRECTION_AUDIT.md), [DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md)); record tool output; apply scoped remediations; destructive git rewrite only after tree is clean (see **Git history**).

---

# Public release pass (recorded results)

## Step 1 — Tool results (2026-05-08)

| Check | Command / action | Result |
|--------|------------------|--------|
| Backend tests | `cd backend && uv run pytest -q -W error::ResourceWarning` | **1027 passed**, 2 skipped (optional LM Studio / TTS E2E; no external calls in default suite). |
| Backend deps | `cd backend && uvx pip-audit` | **No known vulnerabilities found.** |
| Frontend tests | `cd frontend && npm run test` (via `vitest run`) | **Pass** (same suite as `npm run test`). |
| Frontend lint / build | `npm run lint`, `npm run build` | **Pass** (tsc + Vite production build). |
| Frontend deps | `cd frontend && npm audit` | **0 vulnerabilities** after `npm audit fix`, **Vite 8.0.11**, and root **`overrides.picomatch`** → **4.0.4** (transitive fix). |
| Frontend coverage report | `npm run test:cov` | **Report only** (~45% lines on full `src/` — large lazy-loaded views and `WorkflowEditor` are intentionally thin in unit tests; see [TEST_AUDIT.md](TEST_AUDIT.md)). |
| STT bridge | `cd services/stt-bridge && uv run pytest -q` | **2 passed.** |
| TTS bridge | `cd services/tts-bridge && uv run pytest -q` | **17 passed.** |
| Ruff | `cd backend && uv run ruff check app tests` | **Pass** (import ordering / unused import fixes applied in this pass). |
| Mypy | `uv run mypy app` | **Not clean** — **78 errors** across 25 files (pre-existing strictness / SQLAlchemy typing noise). Release gate for this repo is **Ruff + pytest**, not mypy-clean; track under [CODE_QUALITY_AND_STYLE_AUDIT.md](CODE_QUALITY_AND_STYLE_AUDIT.md) if tightening typing becomes a goal. |

## Step 2 — Remediations applied in this pass

- **Root `.gitignore`:** Ignore `.env.*` but **keep** tracked `**/.env.example` templates so local override files are not committed by mistake.
- **Frontend supply chain:** Bumped **Vite** to **8.0.11**, added **`@vitest/coverage-v8`**, **`npm run test:cov`**, configured Vitest **coverage** without a global % threshold (aligned with [TEST_AUDIT.md](TEST_AUDIT.md)).
- **`frontend/package.json` `overrides`:** Pinned transitive **picomatch** to **4.0.4** for advisory closure.
- **Backend:** `ValidatedAudioFile` typing in [`executor.py`](../../backend/app/domain/workflow_executor/executor.py); voice sample test unused variable removed.
- **Docs:** Fixed [SANDBOX.md](../SANDBOX.md) link to **TEST_AUDIT** path under `docs/Audits/`; frontend README **Tests** section; [ARCHITECTURE.md](../ARCHITECTURE.md) links this file.

## Coverage percentage note

Some contributors prefer a **100% line-coverage** bar. This codebase instead follows **TEST_AUDIT.md**: behavior is mapped to tests; **optional** `--cov` / `test:cov` reports are for debugging and release review, not a merge gate. Raising global % would require broad UI E2E or large `WorkflowEditor` harness work (called out as manual / future in TEST_AUDIT).

## Secrets and history

- Tracked tree: only **`.env.example`** templates under `backend/`, `frontend/`, `services/stt-bridge/`; no `.pem` / `.db` files found in versioned paths during review.
- **Before** pushing to a public remote, run a dedicated secret scan on **full git history** if anything sensitive was ever committed locally (e.g. `git log -p` / `gitleaks`). This pass ends with a **single new root commit** (see below), which removes prior history from the **pushed** view but does not erase local backup refs unless you delete them.

## Policy checkpoint (license and disclosure)

**Done (2026-05-08):**

- [LICENSE](../../LICENSE) — Apache License 2.0 (`Copyright 2026 Mind Weave contributors` in the Appendix; replace with a single legal entity name if required).
- [SECURITY.md](../../SECURITY.md) — GitHub private vulnerability reporting only (no email in-repo). After the first push, enable **Settings → General → Security → Private vulnerability reporting** on GitHub if it is not already on.
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Local checks, test policy, links to architecture and audits.

## Git history — single initial commit

After the working tree is clean and all tests pass:

```bash
git checkout --orphan new-root
git add -A
git status   # verify only intended files
git commit -m "Initial commit"
git branch -D main
git branch -m main
```

Optional safety: `git bundle create ../mind-weave-backup.bundle --all` **before** deleting `main`.

Then add `origin` and `git push -u origin main` when ready.

## Open follow-ups

- **Mypy:** Clear or narrow `warn_return_any` / SQLModel false positives if strict typing becomes a CI gate.
- **Node engines:** `npm install` may warn **`chevrotain@12`** wants Node **≥ 22** (transitive via **mermaid**); current CI/dev is Node 20 — monitor; upgrade Node or pin mermaid if builds break on publish.
- **E2E:** [TEST_AUDIT.md](TEST_AUDIT.md) still notes manual / future Playwright for the workflow editor.
