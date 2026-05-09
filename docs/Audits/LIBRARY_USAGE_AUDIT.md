---

## last_reviewed: 2026-05-08 (LU-004–005 remediated — API drops torch/qwen-tts; Playwright is extra `url-snapshot`)

audience: Maintainers choosing or vetting dependencies; periodic stack hygiene
scope: Runtime and dev dependencies in [`backend/pyproject.toml`](../../backend/pyproject.toml) and [`frontend/package.json`](../../frontend/package.json); **satellite** services [`services/tts-bridge/pyproject.toml`](../../services/tts-bridge/pyproject.toml) and [`services/stt-bridge/pyproject.toml`](../../services/stt-bridge/pyproject.toml) are summarized below (deploy narrative: [OPERATIONS.md](../OPERATIONS.md)). Transitive behavior only where it affects trust (e.g. cryptography). **Known vulnerability scanning** and cadence live in [SECURITY_AUDIT.md](SECURITY_AUDIT.md)—use that checklist for `pip-audit` / `npm audit`; this document focuses on *why* a library is here and whether alternatives exist.
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
4. After adding or removing a dependency, skim [ARCHITECTURE.md](../ARCHITECTURE.md) and package READMEs so prose still matches [`package.json`](../../frontend/package.json) / [`pyproject.toml`](../../backend/pyproject.toml). Run security scans per [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

## Executive summary

The stack remains **conventional for a FastAPI + React (Vite) SPA**: **FastAPI** / **SQLModel** / **httpx** on the API; **React 18** with **[@xyflow/react](https://www.npmjs.com/package/@xyflow/react)** for the workflow canvas and **lucide-react** for icons. The SPA has grown a **documented markdown stack**—**react-markdown** with **remark-gfm**, **remark-math**, **rehype-katex**, **katex** (CSS), and dynamic **mermaid** for fenced diagrams—aligned with [ARCHITECTURE.md](../ARCHITECTURE.md) (*Markdown-oriented preview*). **Phaser** powers the **Sandbox** runtime ([`phaserSandboxAdapter.ts`](../../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts)). On the API, **jsonschema** validates structured outputs in the executor; **beautifulsoup4** supports **html_parse_basic**; **tiktoken** supplies document token metadata; **`capture_url_snapshot`** uses **Playwright** when the **`url-snapshot`** optional extra is installed (default **`uv sync --extra dev`** omits it for a slimmer API tree). **PyTorch** and **qwen-tts** are **not** declared on the backend package—**TTS synthesis** lives in **[services/tts-bridge](../../services/tts-bridge/)**; STT uses **[services/stt-bridge](../../services/stt-bridge/)** (**faster-whisper**). Backend pins **`bcrypt==4.0.1`** with **passlib** (passlib 1.7.x / bcrypt API compatibility); **python-jose[cryptography]** covers JWTs and pulls **cryptography** shared with **Fernet** API-key encryption ([`user_api_keys_crypto.py`](../../backend/app/core/user_api_keys_crypto.py)).

**Dependency scans (this pass, 2026-05-08):** **`uvx pip-audit`** (backend) reported **no known vulnerabilities**; **`npm audit`** (frontend) reported **0 vulnerabilities**—consistent with the same-day notes in [SECURITY_AUDIT.md](SECURITY_AUDIT.md) and [PUBLIC_RELEASE_PASS.md](PUBLIC_RELEASE_PASS.md).

## Backend — runtime dependencies


| Dependency                           | Role here                                                                                                                                                          | Without it?                                         | Single narrow use?                                                                                                  | Fit / alternatives                                                                                                                                                                       | Trust & support                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **fastapi[standard]**                | HTTP API, dependency injection, OpenAPI                                                                                                                            | Reimplement routing, validation, and docs by hand   | No—core framework                                                                                                   | Standard for this product class; **Starlette** / **Pydantic v2** underneath                                                                                                              | Very high; large community                                           |
| **uvicorn[standard]**                | ASGI server                                                                                                                                                        | Another ASGI server (hypercorn, etc.)               | Listed explicitly while `fastapi[standard]` also pulls server-related extras—overlap is organizational, not harmful | Uvicorn is the default pairing for FastAPI docs and tutorials                                                                                                                            | High                                                                 |
| **sqlmodel**                         | ORM + table models on **SQLAlchemy**                                                                                                                               | Raw SQL or SQLAlchemy only                          | No—data layer                                                                                                       | Fits FastAPI + Pydantic ecosystem; couples SQLAlchemy version to SQLModel releases                                                                                                       | High (narrower than Django ORM but backed by SQLAlchemy)             |
| **pydantic** / **pydantic-settings** | Request/response models, `Settings`                                                                                                                                | Manual validation                                   | No—pervasive                                                                                                        | Default for FastAPI v2                                                                                                                                                                   | Very high                                                            |
| **httpx**                            | Async HTTP to LM Studio ([`models.py`](../../backend/app/api/v1/models.py)), TTS/STT bridges, provider code                                                         | `urllib` or `requests` in async contexts is awkward | No—LLM and async outbound HTTP                                                                                      | Standard modern async client                                                                                                                                                             | High                                                                 |
| **passlib[bcrypt]**                  | Password hashing ([`security.py`](../../backend/app/core/security.py))                                                                                             | `bcrypt` library directly with careful API use      | Password path only—appropriate                                                                                      | passlib abstracts multiple schemes; **argon2** is an alternative family for greenfield-only apps, not required here                                                                      | Mature; maintenance is slow but usage is massive                     |
| **bcrypt==4.0.1**                    | Backend for passlib’s bcrypt scheme                                                                                                                                | Rely on transitive bcrypt                           | Pin is explicit                                                                                                     | **Rationale:** passlib 1.7.x predates bcrypt 4.1+ API changes; pinning avoids subtle verify/hash breakage during upgrades. Revisit when upgrading passlib or adopting a maintained fork. | bcrypt library is standard                                           |
| **alembic**                          | Migrations                                                                                                                                                         | Hand-written SQL migrations                         | No—expected with SQLAlchemy                                                                                         | Standard                                                                                                                                                                                 | High                                                                 |
| **python-jose[cryptography]**        | JWT create/verify ([`security.py`](../../backend/app/core/security.py), [`deps.py`](../../backend/app/api/deps.py), [`auth.py`](../../backend/app/api/v1/auth.py)) | Manual JWS                                          | Auth only—appropriate                                                                                               | **PyJWT** is a common alternative; switching is a deliberate auth refactor, not a day-one win. Prefer reassessment on a major auth change.                                               | Long-standing; use `[cryptography]` extra (avoid stdlib-less crypto) |
| **python-multipart**                 | **OAuth2PasswordRequestForm** / form bodies ([`auth.py`](../../backend/app/api/v1/auth.py))                                                                          | Would break token login route                       | Supports form encoding—not “random”                                                                                 | Required by FastAPI for form parsing                                                                                                                                                     | Standard small utility                                               |
| **jsonschema**                       | **Draft202012Validator** / `validate_against_structure` in workflow executor ([`executor.py`](../../backend/app/domain/workflow_executor/executor.py))               | Hand-rolled structure checks                        | Executor / structured-output path                                                                                   | Standard JSON Schema 2020-12; fits LLM “structure” steps                                                                                                                                 | High                                                                 |
| **beautifulsoup4**                   | **HTML parse basic** utility ([`html_parse_basic.py`](../../backend/app/domain/workflow_executor/html_parse_basic.py))                                              | Manual parsing or **lxml**                          | Utility / skill path                                                                                                | Common for tolerant HTML; prefer one stack for HTML skills                                                                                                                               | High                                                                 |
| **tiktoken**                         | Token-count metadata for Documents (**GPT-4o** `o200k_base`) ([`document_metadata_service.py`](../../backend/app/domain/services/document_metadata_service.py))      | Omitted counts or approximate heuristics             | Documents metadata path                                                                                              | Matches OpenAI tokenizer assumptions for catalogued models                                                                                                                                 | High (OpenAI-maintained)                                             |


**Transitive note:** `python-jose[cryptography]` brings **cryptography**, which [`user_api_keys_crypto.py`](../../backend/app/core/user_api_keys_crypto.py) uses for **Fernet**—no second crypto library needed.

## Backend — dev / build


| Tool                                           | Role           | Notes                                                    |
| ---------------------------------------------- | -------------- | -------------------------------------------------------- |
| **pytest**, **pytest-asyncio**, **pytest-cov** | Tests          | Standard; coverage config in pyproject                   |
| **ruff**                                       | Lint + format  | Single tool replacing much of flake8/isort for this repo |
| **mypy** + **pydantic.mypy**                   | Static typing  | See [ARCHITECTURE.md](../ARCHITECTURE.md)                |
| **types-passlib**, **types-python-jose**       | Stubs for mypy | Appropriate                                              |
| **types-jsonschema**                           | Stubs for mypy | Pairs with runtime **jsonschema**                        |
| **hatchling**                                  | Wheel build    | Normal for pyproject packaging                           |

## Backend — optional runtime extras

Declared under **`[project.optional-dependencies]`** in [`pyproject.toml`](../../backend/pyproject.toml). Use e.g. **`uv sync --extra dev --extra url-snapshot`** from `backend/` when operators need the skill below; see [backend/README.md](../../backend/README.md) and [OPERATIONS.md](../OPERATIONS.md).


| Extra            | Package(s)        | Role |
| ---------------- | ----------------- | ---- |
| **`url-snapshot`** | **playwright** (`>=1.49.0`) | Headless Chromium for **`capture_url_snapshot`** ([`capture_url_snapshot_runtime.py`](../../backend/app/domain/workflow_executor/capture_url_snapshot_runtime.py)); run **`uv run playwright install chromium`** after install. Without the extra, the skill returns structured **`PLAYWRIGHT_MISSING`**. |

## Satellite services — Python (separate deployables)

These packages are **not** merged into the API wheel but matter for **total** operator footprint and trust. See [OPERATIONS.md](../OPERATIONS.md) and service READMEs.


| Service      | Manifest                                                                     | Notable runtime dependencies |
| ------------ | ---------------------------------------------------------------------------- | ---------------------------- |
| **TTS bridge** | [`services/tts-bridge/pyproject.toml`](../../services/tts-bridge/pyproject.toml) | **fastapi**, **uvicorn**, **httpx**, **huggingface_hub**, **soundfile**, **numpy**, **torch**, **qwen-tts** |
| **STT bridge** | [`services/stt-bridge/pyproject.toml`](../../services/stt-bridge/pyproject.toml) | **fastapi**, **uvicorn**, **python-multipart**, **faster-whisper**, **pydantic-settings** |


## Frontend — runtime dependencies


| Dependency                | Role here                                                                                                    | Without it?                                  | Single narrow use?                                                                            | Fit / alternatives                                                                                                        | Trust & support                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **react** / **react-dom** | UI                                                                                                           | No SPA                                       | No — core                                                                                     | Industry default                                                                                                          | Very high                                   |
| **@xyflow/react**         | Workflow canvas, handles, graph types ([`workflow-editor/`](../../frontend/src/components/workflow-editor/)) | Build a DAG editor from scratch              | Large feature surface in one product-critical dep                                             | **xyflow** is the maintained successor to the older `reactflow` npm naming; docs/readmes may say “ReactFlow” colloquially | Strong OSS community; product depends on it |
| **lucide-react**          | Icons across app shell and editor                                                                            | Inline SVGs, another icon pack               | Many icons from one tree-shaken package                                                       | Replaced removed `@heroicons/react` per code-quality audit; Lucide is comparable                                          | High                                        |
| **react-markdown**        | Markdown rendering ([`MarkdownRawPreview.tsx`](../../frontend/src/components/MarkdownRawPreview.tsx))        | Raw text only                                | Documents / preview surfaces                                                                  | Standard React markdown; pairs with remark/rehype plugins                                                                  | High                                        |
| **remark-gfm**            | GitHub-flavored Markdown ([`MarkdownRawPreview.tsx`](../../frontend/src/components/MarkdownRawPreview.tsx))  | No tables/task lists in preview              | Bundled with markdown preview                                                                  | De-facto GFM for remark                                                                                                    | High                                        |
| **remark-math**           | `$…$` / `$$…$$` math spans for KaTeX                                                                         | No TeX math in markdown                      | Preview surfaces                                                                               | Common remark math bridge                                                                                                  | High                                        |
| **rehype-katex**          | Server-side math rendering to KaTeX HTML                                                                     | Plain text math                              | Preview surfaces                                                                               | Pairs with **katex** CSS                                                                                                   | High                                        |
| **katex**                 | KaTeX stylesheet ([`main.tsx`](../../frontend/src/main.tsx))                                                 | Unstyled equations                           | Preview surfaces                                                                               | Same ecosystem as **rehype-katex**                                                                                        | High                                        |
| **mermaid**               | Diagrams in fenced ` ```mermaid ` blocks ([`MermaidBlock.tsx`](../../frontend/src/components/MermaidBlock.tsx), dynamic `import('mermaid')`) | No diagrams in markdown              | Markdown preview                                                                               | Large transitive tree; **npm** may warn **EBADENGINE** on transitive **chevrotain** (see [SECURITY_AUDIT.md](SECURITY_AUDIT.md)) | High community use; monitor supply chain   |
| **phaser**                | **Sandbox** 2D runtime ([`phaserSandboxAdapter.ts`](../../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts), [`SandboxView.tsx`](../../frontend/src/components/SandboxView.tsx)) | Rewrite sandbox engine              | Sandbox only                                                                                   | Full game framework—heavy but replaces a custom WebGL/canvas stack for this feature                                         | Mature OSS                                  |

**`package.json` overrides:** **`picomatch` → `4.0.4`** — aligns transitive resolution with Vite 8 / esbuild advisory posture; see [SECURITY_AUDIT.md](SECURITY_AUDIT.md) (2026-05-08).

## Frontend — dev tooling


| Tool                                                             | Role                   | Notes                                                                |
| ---------------------------------------------------------------- | ---------------------- | -------------------------------------------------------------------- |
| **vite**, **@vitejs/plugin-react**                               | Build + dev server     | Current major (Vite 8) per security posture                          |
| **typescript**                                                   | Types                  | —                                                                    |
| **tailwindcss**, **postcss**, **autoprefixer**                   | Styling pipeline       | Standard trio                                                        |
| **@tailwindcss/typography**                                        | `prose` / markdown chrome | Wired in [`tailwind.config.js`](../../frontend/tailwind.config.js); see [DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md) |
| **eslint** + **typescript-eslint** + react plugins + **globals** | Lint                   | Flat config in [`eslint.config.js`](../../frontend/eslint.config.js) |
| **vitest**, **jsdom**, **@testing-library/**, **@vitest/coverage-v8** | Unit/integration tests | Standard for Vite projects                                           |


## Open findings

No open LU items.

**Next unused id:** **LU-006**.


## Resolved (history)

| Id | Closed (summary) |
| -- | ---------------- |
| **LU-004** | **2026-05-08** — Removed **`torch`** and **`qwen-tts`** from backend `[project.dependencies]`; they remain only on **tts-bridge**. |
| **LU-005** | **2026-05-08** — **Playwright** moved to optional extra **`url-snapshot`**; [OPERATIONS.md](../OPERATIONS.md) and [backend/README.md](../../backend/README.md) document sync + **`playwright install chromium`**; missing package surfaces **`PLAYWRIGHT_MISSING`** in [`capture_url_snapshot_runtime.py`](../../backend/app/domain/workflow_executor/capture_url_snapshot_runtime.py). |

## Strengths (preserve these)

- **Documented SPA expansion:** Markdown/math/Mermaid and **Tailwind Typography** follow [ARCHITECTURE.md](../ARCHITECTURE.md) and [DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md), not ad hoc one-off stacks.
- **Sandbox isolation:** **Phaser** is scoped to the sandbox adapter and tests ([`phaserSandboxAdapter.ts`](../../frontend/src/sandbox/runtime/phaserSandboxAdapter.ts)), not the whole shell.
- **Speech ML at the bridge:** **faster-whisper** and **torch+qwen-tts** ship in **satellite** services; the API package no longer duplicates them.
- **Slim default API install:** **Playwright** is opt-in via **`url-snapshot`**; core **`uv sync --extra dev`** stays lighter.
- **Explicit ASGI server:** **uvicorn[standard]** stays listed alongside **fastapi[standard]** for clarity and direct version control.
- **Single icon library:** **lucide-react** only.
- **Graph editor:** One maintained product (**@xyflow/react**) for the workflow canvas.
- **Crypto:** One family (**cryptography**) for JWT (via jose extra) and Fernet for at-rest API key blobs.

## Related documents

- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) — advisories, scans, threat-angled dependency notes (including **picomatch** override and **mermaid** toolchain warnings).
- [PUBLIC_RELEASE_PASS.md](PUBLIC_RELEASE_PASS.md) — recorded **`pip-audit` / `npm audit`** outcomes.
- [CODE_QUALITY_AND_STYLE_AUDIT.md](CODE_QUALITY_AND_STYLE_AUDIT.md) — tooling overlap (Ruff, ESLint) at a style/conventions level.
- [TEST_AUDIT.md](TEST_AUDIT.md) — what pytest/Vitest must prove; not a duplicate dependency list.
- [ARCHITECTURE.md](../ARCHITECTURE.md) — stack conventions (workspace, bridges, markdown preview).
- [CHANGELOG.md](../../CHANGELOG.md) — user/operator-visible changes when dependencies drive behavior.

## Review checklist (periodic)

- Bump `last_reviewed` and triage **Open findings**.
- After any new dependency: add a row here or fold into narrative; justify **necessity**, **alternatives**, and **trust**.
- Run **`uvx pip-audit`** (backend) and **`npm audit`** (frontend) per [SECURITY_AUDIT.md](SECURITY_AUDIT.md).
- If JWT or crypto libraries change, update [SECURITY_AUDIT.md](SECURITY_AUDIT.md) and [CHANGELOG.md](../../CHANGELOG.md) as appropriate.

