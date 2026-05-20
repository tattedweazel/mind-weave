# Test audit — core functionality

Single place to see **what must not break** and **which test demonstrates it**. Update this file when you add API routes, auth flows, or user-visible behavior.

**There is no line-coverage percentage goal** for this project. What matters is that **core behavior** stays mapped to tests (this file). Optional: run `uv run pytest --cov=app` in backend if you want a report for your own debugging—do not treat `%` as a pass/fail bar.

**Test harness libraries** (Vitest, Testing Library, pytest, etc.) are inventoried and vetted in [LIBRARY_USAGE_AUDIT.md](LIBRARY_USAGE_AUDIT.md).

---

## Harness

| Mechanism | Purpose |
|-----------|---------|
| [`backend/tests/conftest.py`](../../backend/tests/conftest.py) | In-memory DB, `get_session` override. Most tests override `get_current_user` for speed. |
| [`test_auth_session.py`](../../backend/tests/test_auth_session.py) | Real cookie + JWT path: login, refresh, logout, register, cookie-only `/me`. |
| [`test_google_oauth.py`](../../backend/tests/test_google_oauth.py) | Google OAuth + session code exchange (HTTP mocked). |

---

## Backend — security & auth

| Capability | Test evidence |
|------------|----------------|
| `SECRET_KEY` / `BOOTSTRAP_DEFAULT_ADMIN` rules | `test_config_security.py` |
| Registration: weak password, closed, duplicate message | `test_registration_security.py` |
| Login: invalid credentials | `test_registration_security.py` |
| Login: Google-only user → `use_google_login` | `test_google_oauth.py::test_login_rejects_user_with_google` |
| Google OAuth flows + errors + cookie exchange (login redirect uses `#google_session=` fragment) | `test_google_oauth.py` |
| Password login / refresh / logout / register → HttpOnly cookies | `test_auth_session.py` |
| Refresh `jti` rotation + revoked cookie rejected (`SE-010`) | `test_auth_session.py::test_refresh_rejects_reused_refresh_after_rotation`, `::test_refresh_rejected_after_logout` |
| Refresh rejects missing `jti` (`SE-031`); access Bearer must be `typ=access` (`SE-032`) | `test_auth_session.py::test_refresh_rejects_token_without_jti`, `::test_me_rejects_bearer_access_token_without_typ`, `::test_me_rejects_refresh_token_as_bearer` |
| Admin: PUT user (username, password, `is_admin`, errors; username conflict generic) | `test_auth_admin.py`, `::test_admin_update_user_username_taken` |
| Admin: cannot demote the last admin (`is_admin` → false) | `test_auth_admin.py::test_admin_cannot_remove_last_admin` |
| Admin: POST `/auth/users`, DELETE `/auth/users/{id}`, no self-delete | `test_auth_admin.py::test_admin_create_user`, `::test_admin_delete_user` |
| Admin: list users, Google metadata | `test_google_oauth.py::test_list_users_includes_google_email` |
| Admin: disassociate Google for another user | `test_google_oauth.py::test_admin_disassociate_google_for_user` |
| Auth endpoint rate limits; invalid `N/minute` spec raises (`SE-033`) | `test_auth_rate_limit.py`, `test_config_security.py::test_settings_rejects_invalid_rate_limit_spec` |
| Workflow `POST .../run` + `.../runs` enqueue combined per-IP rate limit | `test_auth_rate_limit.py::test_workflow_run_middleware_429_and_shared_bucket_per_ip` |
| PUT `/auth/me` settings (allowlisted keys only) | `test_api.py::test_update_me_settings_system_colors`, `::test_update_me_rejects_unknown_settings_key` |
| GET `/auth/me` masks `api_keys`; storage encrypted | `test_api.py::test_get_me_masks_api_keys`, `::test_put_me_api_keys_encrypted_at_rest` |
| Run logs: redact prompt-like keys + `error` URL stripping (`SE-030`) | `test_workflow_run_logs_api.py` |
| Log redaction: `Authorization` | `test_logging_redaction.py` |

---

## Backend — health & models

| Capability | Test evidence |
|------------|----------------|
| `GET /health` | `test_api.py::test_health` |
| `GET /health/ready` auth + DB | `test_api.py` (authed + `client_anonymous` 401) |
| `GET /models/` requires auth | `test_api.py::test_models_without_auth_returns_401` |
| `GET /models/` success (LM Studio mocked) | `test_api.py::test_models_authed_mocks_lmstudio` |

---

## Backend — CRUD & workflows

| Capability | Test evidence |
|------------|----------------|
| Palettes list/create/update/delete | `test_api.py` |
| Structures list/create + full CRUD smoke | `test_api.py`, `test_resources_crud_smoke.py::test_structure_crud_smoke` |
| Personas list + full CRUD smoke | `test_api.py`, `test_workflow_executor.py` (list), `test_resources_crud_smoke.py::test_persona_crud_smoke` |
| Workflow **execution** (large suite, LLM mocked; patch `app.domain.workflow_executor.executor.LMStudioProvider`) | `test_workflow_executor.py` |
| Simple LLM Call: persona + optional additional context in system; user prompt as user message | `test_workflow_executor.py` (`test_simple_llm_persona_*additional*`) |
| Workflow **REST**: list (`WorkflowDefinitionListItem` — no `graph`), get (full), put, delete, sync `/run`, enqueue `/runs`, `GET …/workflow-runs/…/{events,snapshot}`, `GET /runs`, `GET .../logs` | `test_workflow_definitions_api.py` |
| Persisted graph **`schema_version`** default on create | `test_workflow_definitions_api.py::test_workflow_definitions_crud_run_runs_delete` (asserts `graph.schema_version == 1`) |
| **Slim list schemas** — list endpoints exclude heavy fields (`graph`, `body`, `system_prompt`); single-item GET returns full object | `test_workflow_definitions_api.py`, `test_resources_crud_smoke.py` |
| **Step kind manifest** parity: every `shared/workflow_graph_step_kinds.json` row parses via `_parse_node` | `test_workflow_graph_step_kinds_parity.py` |
| **Google workflow** Gmail/Calendar skills (`ensure_workflow_google_access_token` + API calls mocked); empty connections list | `test_google_workspace_skills.py` |
| **Google Docs** URL parse, parse utility, get skill + curate (mocked `documents.get` / image fetch) | `test_google_docs_url_parser.py`, `test_google_docs_parse.py`, `test_google_docs_skills.py`, `test_google_docs_curate.py`, `test_google_docs_integration_http.py` |
| **Audio File Input** skill and audio artifact API (STT bridge mocked; saved artifact, runtime upload, sync rejection without saved file, upload validation) | `test_workflow_audio_file_input.py` |
| **Transcribe File** skill (provider-abstracted) — `local_whisper` + `assemblyai` adapters with mocked externals (`httpx.MockTransport` for AAI), saved artifact + runtime upload paths, missing API key error, unknown `provider_model_id` validation, `options_json` round-trip via poller `_options_from_row`, client-disconnect leaving job non-terminal, lifespan poller advancement, transient artifact cleanup, reattach stream replay (404 for other users), `transcribe-file-input` route | `test_workflow_transcribe_file.py` |
| `input_overrides` allowlisted per workflow graph (`SE-015`) | `test_workflow_definitions_api.py::test_workflow_run_rejects_unknown_input_override` |
| CLI `create-admin` | `test_cli.py` |
| LM Studio provider helpers | `test_lmstudio.py` |
| **Sandbox** domain engine (no LLM) | `test_sandbox_engine.py` |
| **Sandbox** HTTP: session create + tick + starter id + `last_workflow_run` + `workflow_id` persist on tick; `sandbox_defaults` on workflow graph applied at create; grid resize (paused-only, version, bounds) | `test_sandbox_api.py` |
| **Sandbox** starter workflow seed: `ensure_starter_sandbox_workflow` re-syncs stale stored graph | `test_starter_workflow_seed.py` |
| **Sandbox** pure query helpers (`query.py`: adjacency, first-food ordering, pet stats, nearest-by-type, world grid dimensions) | `test_sandbox_query.py` |
| **`sandbox_*` workflow utilities** (executor HTTP runs; no LLM) | `test_sandbox_workflow_utilities.py` |
| **Companion / Workspace** bootstrap, stream turn (LLM mocked via `WorkspaceRuntimeService` patches), disabled flag, `PUT /companion/` partial + clear persona, `PUT /workspaces/{id}` `enabled_workflow_ids` + 422 on unknown workflow | `test_workspace_api.py` |
| **Workspace default Google connection** injected into **`gmail_list_messages`** / **`calendar_list_events`** graphs (deep copy; no DB mutation) | `test_workspace_google_graph.py` |
| **Workspace Google injection** wired through **`WorkflowExecutor`** nested-schedule path | `test_workflow_executor_nested_google.py` |

**Product note:** `WorkflowRun` rows (and thus `GET .../runs`) are created when enqueueing **`POST .../runs`**, not during synchronous **`POST .../run`**. Lifecycle tests encode that distinction.

---

## Frontend

| Capability | Test evidence |
|------------|----------------|
| App shell, auth UI, theme, avatar, palettes (unit/integration) | `frontend/src/**/*.test.tsx`, `*.test.ts` |
| Baseline CSP meta (tune `connect-src` for prod API) | `frontend/index.html` |
| Workflow editor **step kind manifest** vs `nodeTypes` + `appNodeToFlow` / `flowNodeToApp` | `frontend/src/components/workflow-editor/workflowGraphStepKindsManifest.test.ts` |
| **Manifest-aligned** `getSourceOutputType` default behavior (explicit `any` allowlist incl. Stop / For-loop item) | `workflowGraphStepKindsManifest.test.ts` (`getSourceOutputType vs manifest`) |
| **Workflow editor (ReactFlow) end-to-end** | Not automated — manual QA or future Playwright/Cypress. |
| **Sandbox Phaser adapter** | `frontend/src/sandbox/runtime/phaserSandboxAdapter.test.ts` (resize only on grid dimension change; Phaser mocked) |
| **Sandbox `last_error` hint matching** | `frontend/src/sandbox/sandboxLastErrorHint.test.ts` |
| **Sandbox Phaser view** | Lazy-loaded; no automated E2E — manual QA. |
| **Workspace chat stream parser** | `frontend/src/api/workspaceStream.test.ts` |
| **Companion settings modal** (name save, no-op save closes without PUT) | `frontend/src/components/CompanionSettingsModal.test.tsx` |
| **Workspace settings modal** (capability toggle + save, no-op save closes without PUT) | `frontend/src/components/WorkspaceSettingsModal.test.tsx` |
| **Workspace chat view** | Lazy-loaded; no automated E2E — manual QA. |

---

## When to edit this file

1. You add or change a **route** or **auth rule** → add or adjust a row and the test file that proves it.
2. You add a **test** that encodes a new invariant → link it here.
3. You **remove** or **replace** behavior → delete or update the row so this stays honest.

Optional: run `uv run pytest -q -W error::ResourceWarning` from `backend/` before a release.
