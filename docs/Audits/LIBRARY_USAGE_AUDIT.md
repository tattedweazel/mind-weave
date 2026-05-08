---

## last_reviewed: 2026-03-19 (LU-001–003 closed)

audience: Maintainers choosing or vetting dependencies; periodic stack hygiene
scope: Runtime and dev dependencies declared in `[backend/pyproject.toml](../../backend/pyproject.toml)` and `[frontend/package.json](../../frontend/package.json)`; transitive behavior only where it affects trust (e.g. cryptography). **Known vulnerability scanning** and cadence live in [SECURITY_AUDIT.md](SECURITY_AUDIT.md)—use that checklist for `pip-audit` / `npm audit`; this document focuses on *why* a library is here and whether alternatives exist.
methodology: Inventory from manifest files, spot-check imports under `backend/app/` and `frontend/src/`, compare with docs that name the stack. **This backlog is built incrementally**—new passes add **LU-xxx** rows, update `last_reviewed`, and **remove** rows when remediated (keep ids stable until closed).

**Severity legend**


| Level        | Meaning                                                                                             |
| ------------ | --------------------------------------------------------------------------------------------------- |
| **Critical** | Dependency is unsafe, unmaintained, or fundamentally wrong for the problem; replace urgently.       |
| **High**     | Wrong tool for the job, heavy overlap, or clear standard-library win missing; schedule replacement. |
| **Medium**   | Justified library but notable risk (single narrow use, weak ecosystem, or drift hazard).            |
| **Low**      | Hygiene: unused packages, redundant declarations, missing one-line rationale for pins.              |
| **Info**     | Optional consolidation or long-term reconsideration; no immediate action.                           |


# Mind Weave — Library usage audit

## How to use this document

1. On each review pass, update `last_reviewed` in the front matter.
2. **Open findings** holds active **LU-xxx** items. When resolved, **delete** the row (or move to a short “Resolved” appendix with date/PR if you want history).
3. New issues get the next free **LU-xxx** id; existing ids stay stable until closed.
4. After adding or removing a dependency, skim [ARCHITECTURE.md](../ARCHITECTURE.md) and package READMEs so prose still matches `[package.json](../../frontend/package.json)` / `[pyproject.toml](../../backend/pyproject.toml)`. Run security scans per [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

## Executive summary

The stack is **conventional for a FastAPI + React (Vite) SPA**: framework and HTTP on the backend, React 18 and **React Flow** (npm package `**[@xyflow/react](https://www.npmjs.com/package/@xyflow/react)`**) on the frontend, with **Lucide** for icons. There is **no sprawl** of single-purpose novelty packages; frontend runtime dependencies are intentionally minimal (**react**, **@xyflow/react**, **lucide-react** only). Backend pins `**bcrypt==4.0.1**` alongside **passlib**—a deliberate compatibility pattern for many codebases (newer bcrypt major lines have historically broken passlib’s assumptions until passlib catches up); the pin is also summarized inline in `[pyproject.toml](../../backend/pyproject.toml)`. JWT handling uses **python-jose** (with the **cryptography** extra), which pulls in `**cryptography`** also used for **Fernet** API-key encryption—both are mature, widely deployed stacks.

## Backend — runtime dependencies


| Dependency                           | Role here                                                                                                                                                          | Without it?                                         | Single narrow use?                                                                                                  | Fit / alternatives                                                                                                                                                                       | Trust & support                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **fastapi[standard]**                | HTTP API, dependency injection, OpenAPI                                                                                                                            | Reimplement routing, validation, and docs by hand   | No—core framework                                                                                                   | Standard for this product class; **Starlette** / **Pydantic v2** underneath                                                                                                              | Very high; large community                                           |
| **uvicorn[standard]**                | ASGI server                                                                                                                                                        | Another ASGI server (hypercorn, etc.)               | Listed explicitly while `fastapi[standard]` also pulls server-related extras—overlap is organizational, not harmful | Uvicorn is the default pairing for FastAPI docs and tutorials                                                                                                                            | High                                                                 |
| **sqlmodel**                         | ORM + table models on **SQLAlchemy**                                                                                                                               | Raw SQL or SQLAlchemy only                          | No—data layer                                                                                                       | Fits FastAPI + Pydantic ecosystem; couples SQLAlchemy version to SQLModel releases                                                                                                       | High (narrower than Django ORM but backed by SQLAlchemy)             |
| **pydantic** / **pydantic-settings** | Request/response models, `Settings`                                                                                                                                | Manual validation                                   | No—pervasive                                                                                                        | Default for FastAPI v2                                                                                                                                                                   | Very high                                                            |
| **httpx**                            | Async HTTP to LM Studio (`[models.py](../../backend/app/api/v1/models.py)`), provider code                                                                         | `urllib` or `requests` in async contexts is awkward | No—LLM and any async outbound HTTP                                                                                  | Standard modern async client                                                                                                                                                             | High                                                                 |
| **passlib[bcrypt]**                  | Password hashing (`[security.py](../../backend/app/core/security.py)`)                                                                                             | `bcrypt` library directly with careful API use      | Password path only—appropriate                                                                                      | passlib abstracts multiple schemes; **argon2** is an alternative family for greenfield-only apps, not required here                                                                      | Mature; maintenance is slow but usage is massive                     |
| **bcrypt==4.0.1**                    | Backend for passlib’s bcrypt scheme                                                                                                                                | Rely on transitive bcrypt                           | Pin is explicit                                                                                                     | **Rationale:** passlib 1.7.x predates bcrypt 4.1+ API changes; pinning avoids subtle verify/hash breakage during upgrades. Revisit when upgrading passlib or adopting a maintained fork. | bcrypt library is standard                                           |
| **alembic**                          | Migrations                                                                                                                                                         | Hand-written SQL migrations                         | No—expected with SQLAlchemy                                                                                         | Standard                                                                                                                                                                                 | High                                                                 |
| **python-jose[cryptography]**        | JWT create/verify (`[security.py](../../backend/app/core/security.py)`, `[deps.py](../../backend/app/api/deps.py)`, `[auth.py](../../backend/app/api/v1/auth.py)`) | Manual JWS                                          | Auth only—appropriate                                                                                               | **PyJWT** is a common alternative; switching is a deliberate auth refactor, not a day-one win. Prefer reassessment on a major auth change.                                               | Long-standing; use `[cryptography]` extra (avoid stdlib-less crypto) |
| **python-multipart**                 | **OAuth2PasswordRequestForm** / form bodies (`[auth.py](../../backend/app/api/v1/auth.py)`)                                                                        | Would break token login route                       | Supports form encoding—not “random”                                                                                 | Required by FastAPI for form parsing                                                                                                                                                     | Standard small utility                                               |


**Transitive note:** `python-jose[cryptography]` brings `**cryptography`**, which `[user_api_keys_crypto.py](../../backend/app/core/user_api_keys_crypto.py)` uses for **Fernet**—no second crypto library needed.

## Backend — dev / build


| Tool                                           | Role           | Notes                                                    |
| ---------------------------------------------- | -------------- | -------------------------------------------------------- |
| **pytest**, **pytest-asyncio**, **pytest-cov** | Tests          | Standard; coverage config in pyproject                   |
| **ruff**                                       | Lint + format  | Single tool replacing much of flake8/isort for this repo |
| **mypy** + **pydantic.mypy**                   | Static typing  | See [ARCHITECTURE.md](../ARCHITECTURE.md)                |
| **types-passlib**, **types-python-jose**       | Stubs for mypy | Appropriate                                              |
| **hatchling**                                  | Wheel build    | Normal for pyproject packaging                           |


## Frontend — runtime dependencies


| Dependency                | Role here                                                                                                    | Without it?                                  | Single narrow use?                                                                            | Fit / alternatives                                                                                                        | Trust & support                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **react** / **react-dom** | UI                                                                                                           | No SPA                                       | No — core                                                                                     | Industry default                                                                                                          | Very high                                   |
| **@xyflow/react**         | Workflow canvas, handles, graph types (`[workflow-editor/](../../frontend/src/components/workflow-editor/)`) | Build a DAG editor from scratch              | Large feature surface in one product-critical dep                                             | **xyflow** is the maintained successor to the older `reactflow` npm naming; docs/readmes may say “ReactFlow” colloquially | Strong OSS community; product depends on it |
| **lucide-react**          | Icons across app shell and editor                                                                            | Inline SVGs, another icon pack               | Many icons from one tree-shaken package                                                       | Replaced removed `@heroicons/react` per code-quality audit; Lucide is comparable                                          | High                                        |


## Frontend — dev tooling


| Tool                                                             | Role                   | Notes                                                                |
| ---------------------------------------------------------------- | ---------------------- | -------------------------------------------------------------------- |
| **vite**, **@vitejs/plugin-react**                               | Build + dev server     | Current major (Vite 8) per security posture                          |
| **typescript**                                                   | Types                  | —                                                                    |
| **tailwindcss**, **postcss**, **autoprefixer**                   | Styling pipeline       | Standard trio                                                        |
| **eslint** + **typescript-eslint** + react plugins + **globals** | Lint                   | Flat config in `[eslint.config.js](../../frontend/eslint.config.js)` |
| **vitest**, **jsdom**, **@testing-library/**                     | Unit/integration tests | Standard for Vite projects                                           |


## Open findings

No open LU items.


## Strengths (preserve these)

- **Minimal runtime surface:** Few npm production dependencies; Python list matches the actual app (ORM, HTTP client, auth, migrations).
- **Explicit ASGI server:** `**uvicorn[standard]**` stays listed in `[pyproject.toml](../../backend/pyproject.toml)` alongside `**fastapi[standard]**` for clarity and direct version control—not redundant by mistake.
- **No redundant icon libraries:** Single icon system (**lucide-react**).
- **Graph editor:** One maintained product (`**@xyflow/react`**) rather than a custom canvas stack plus helpers.
- **Crypto:** One family (**cryptography**) for JWT (via jose extra) and Fernet for at-rest API key blobs.

## Related documents

- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) — advisories, scans, threat-angled dependency notes.
- [CODE_QUALITY_AND_STYLE_AUDIT.md](CODE_QUALITY_AND_STYLE_AUDIT.md) — tooling overlap (Ruff, ESLint) at a style/conventions level.
- [TEST_AUDIT.md](TEST_AUDIT.md) — what pytest/Vitest must prove; not a duplicate dependency list.
- [ARCHITECTURE.md](../ARCHITECTURE.md) — stack conventions.
- [CHANGELOG.md](../../CHANGELOG.md) — user/operator-visible changes when dependencies drive behavior.

## Review checklist (periodic)

- Bump `last_reviewed` and triage **Open findings**.
- After any new dependency: add a row here or fold into narrative; justify **necessity**, **alternatives**, and **trust**.
- Run `**uvx pip-audit`** (backend) and `**npm audit**` (frontend) per [SECURITY_AUDIT.md](SECURITY_AUDIT.md).
- If JWT or crypto libraries change, update [SECURITY_AUDIT.md](SECURITY_AUDIT.md) and [CHANGELOG.md](../../CHANGELOG.md) as appropriate.

