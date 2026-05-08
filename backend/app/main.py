"""
Mind Weave API — Application Entry Point
==========================================
Starts the FastAPI application, registers all routers, and seeds the database
on startup.

API routes:
  /api/v1/health               — health check
  /api/v1/auth                 — authentication (login / token)
  /api/v1/models               — available LLM models
  /api/v1/personas             — Persona CRUD
  /api/v1/documents            — Document CRUD; `GET /{id}/metadata` for token / character / word / line counts (Manage Documents → Metadata tab)
  /api/v1/voice-samples        — Voice samples (design preview + clone references)
  /api/v1/audio-file-artifacts — User-owned audio files for workflow transcription
  /api/v1/transcription/providers — Speech provider directory for the editor (transcribe_file)
  /api/v1/url-snapshot-artifacts — PNG bytes for capture_url_snapshot (user-owned)
  /api/v1/palettes             — workflow Palette CRUD
  /api/v1/system-palettes      — app-wide system theme CRUD
  /api/v1/me                    — current-user resources (workflow run history list)
  /api/v1/workflow-definitions — WorkflowDefinition CRUD + run
  /api/v1/workflow-projects    — Workflow project folder CRUD
  /api/v1/sandbox              — Sandbox simulation sessions + ticks (see docs/SANDBOX.md)
  /api/v1/companion            — Companion identity, memory approval
  /api/v1/workspaces           — Workspace bootstrap, sessions, streaming turns (see docs/WORKSPACE.md)
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, delete, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1 import (
    audio_file_artifacts,
    auth,
    companion_api,
    documents,
    google_workflow,
    health,
    me,
    models,
    palettes,
    personas,
    sandbox,
    structures,
    stt,
    system_palettes,
    tts_models,
    url_snapshot_artifacts,
    voice_samples,
    workflow_run_audio_file_input,
    workflow_run_reattach_stream,
    workflow_run_transcribe,
    workflow_run_transcribe_file,
    workspaces_api,
)
from app.api.v1 import (
    transcription as transcription_router,
)
from app.api.v1 import workflow_definitions as workflow_definitions_router
from app.api.v1 import workflow_projects as workflow_projects_router
from app.core.auth_rate_limit import (
    AuthEndpointRateLimitMiddleware,
    build_auth_rate_limit_rules,
    build_workflow_run_rate_limit_rules,
    build_workspace_turn_stream_rate_limit_rules,
)
from app.core.config import settings
from app.core.security import get_password_hash
from app.core.security_headers import SecurityHeadersMiddleware
from app.domain.sandbox.starter_workflow_seed import ensure_starter_sandbox_workflow
from app.domain.services.palette_service import PaletteService
from app.domain.services.persona_service import PersonaService
from app.domain.services.system_palette_service import SystemPaletteService
from app.domain.services.transcription_job_poller import transcription_job_poller
from app.persistence.db import engine
from app.persistence.tables import NodeRunLog, User, WorkflowRun, utc_now

_perf_logger = logging.getLogger("mindweave.perf")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and wall-clock duration for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _perf_logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["Server-Timing"] = f"total;dur={elapsed_ms:.1f}"
        return response


def _run_migrations() -> None:
    """Run Alembic migrations on startup so schema stays in sync."""
    import os

    from alembic.config import Config

    from alembic import command

    # Resolve alembic.ini path relative to backend dir (where uvicorn is typically run from)
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    alembic_cfg = Config(alembic_ini)
    command.upgrade(alembic_cfg, "head")


def _purge_old_workflow_runs(session: Session) -> None:
    days = settings.WORKFLOW_RUN_LOG_RETENTION_DAYS
    if days <= 0:
        return
    cutoff = utc_now() - timedelta(days=days)
    old_run_ids = [
        r.id
        for r in session.exec(
            select(WorkflowRun.id).where(WorkflowRun.created_at < cutoff)
        ).all()
    ]
    if not old_run_ids:
        return
    session.exec(delete(NodeRunLog).where(NodeRunLog.run_id.in_(old_run_ids)))  # type: ignore[union-attr]
    session.exec(delete(WorkflowRun).where(WorkflowRun.id.in_(old_run_ids)))  # type: ignore[union-attr]
    session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: run migrations, seed default data, and purge stale runs."""
    t0 = time.perf_counter()
    _run_migrations()

    # Alembic's fileConfig sets the root logger to WARNING.  Restore INFO so
    # our perf-timing messages (and any other app-level INFO logs) are visible.
    logging.getLogger().setLevel(logging.INFO)

    _perf_logger.info("migrations %.0fms", (time.perf_counter() - t0) * 1000)

    t2 = time.perf_counter()
    with Session(engine) as session:
        PersonaService(session).initialize_default_personas()
        PaletteService(session).initialize_default_palette()
        SystemPaletteService(session).initialize_builtin_system_palettes()
        ensure_starter_sandbox_workflow(session)

        if settings.BOOTSTRAP_DEFAULT_ADMIN and settings.APP_ENV == "local" and not session.exec(select(User)).first():
            session.add(
                User(
                    username="admin",
                    password_hash=get_password_hash("admin"),
                    is_admin=True,
                    settings={},
                    api_keys={},
                )
            )
            session.commit()

        _purge_old_workflow_runs(session)
    _perf_logger.info("seed+purge %.0fms", (time.perf_counter() - t2) * 1000)

    # Background poller for in-flight cloud transcription_jobs (provider-abstracted
    # transcribe_file skill). Local Whisper jobs are sync and never enter this loop.
    await transcription_job_poller.start()

    _perf_logger.info("total startup %.0fms", (time.perf_counter() - t0) * 1000)

    try:
        yield
    finally:
        await transcription_job_poller.stop()


docs_url = "/docs" if settings.APP_ENV == "local" else None
redoc_url = "/redoc" if settings.APP_ENV == "local" else None
openapi_url = "/openapi.json" if settings.APP_ENV == "local" else None

app = FastAPI(
    title="Mind Weave API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)
_rate_limit_rules = [
    *build_auth_rate_limit_rules(
        settings.AUTH_LOGIN_RATE_LIMIT,
        settings.AUTH_REGISTER_RATE_LIMIT,
        settings.AUTH_REFRESH_RATE_LIMIT,
        settings.AUTH_GOOGLE_SESSION_RATE_LIMIT,
    ),
    *build_workflow_run_rate_limit_rules(settings.WORKFLOW_RUN_RATE_LIMIT),
    *build_workspace_turn_stream_rate_limit_rules(settings.WORKFLOW_RUN_RATE_LIMIT),
]
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(AuthEndpointRateLimitMiddleware, rules=_rate_limit_rules)
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=settings.SECURITY_ENABLE_HSTS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
if settings.BEHIND_REVERSE_PROXY:
    # Outermost: nginx on localhost sets X-Forwarded-Proto / -For for HTTPS and client IP.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])

api_v1 = "/api/v1"
app.include_router(health.router, prefix=api_v1, tags=["health"])
app.include_router(auth.router, prefix=f"{api_v1}/auth", tags=["auth"])
app.include_router(me.router, prefix=f"{api_v1}/me", tags=["me"])
app.include_router(
    google_workflow.router,
    prefix=f"{api_v1}/google-workflow",
    tags=["google-workflow"],
)
app.include_router(models.router, prefix=f"{api_v1}/models", tags=["models"])
app.include_router(personas.router, prefix=f"{api_v1}/personas", tags=["personas"])
app.include_router(palettes.router, prefix=f"{api_v1}/palettes", tags=["palettes"])
app.include_router(system_palettes.router, prefix=f"{api_v1}/system-palettes", tags=["system-palettes"])
app.include_router(structures.router, prefix=f"{api_v1}/structures", tags=["structures"])
app.include_router(tts_models.router, prefix=api_v1, tags=["tts-models"])
app.include_router(documents.router, prefix=f"{api_v1}/documents", tags=["documents"])
app.include_router(audio_file_artifacts.router, prefix=f"{api_v1}/audio-file-artifacts", tags=["audio-file-artifacts"])
app.include_router(
    url_snapshot_artifacts.router, prefix=f"{api_v1}", tags=["url-snapshot-artifacts"]
)
app.include_router(voice_samples.router, prefix=f"{api_v1}/voice-samples", tags=["voice-samples"])
app.include_router(sandbox.router, prefix=f"{api_v1}", tags=["sandbox"])
app.include_router(companion_api.router, prefix=api_v1)
app.include_router(workspaces_api.router, prefix=api_v1)
app.include_router(
    workflow_definitions_router.router, prefix=f"{api_v1}/workflow-definitions", tags=["workflow-definitions"]
)
app.include_router(
    workflow_run_transcribe.router, prefix=f"{api_v1}", tags=["workflow-runs"]
)
app.include_router(
    workflow_run_audio_file_input.router, prefix=f"{api_v1}", tags=["workflow-runs"]
)
app.include_router(
    workflow_run_transcribe_file.router, prefix=f"{api_v1}", tags=["workflow-runs"]
)
app.include_router(
    workflow_run_reattach_stream.router, prefix=f"{api_v1}", tags=["workflow-runs"]
)
app.include_router(transcription_router.router, prefix=f"{api_v1}", tags=["transcription"])
app.include_router(stt.router, prefix=f"{api_v1}", tags=["stt"])
app.include_router(workflow_projects_router.router, prefix=f"{api_v1}/workflow-projects", tags=["workflow-projects"])
