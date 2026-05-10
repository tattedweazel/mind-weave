from typing import List, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.auth_rate_limit import parse_per_minute_limit

_DEV_SECRET_PLACEHOLDER = "your-secret-key-for-dev-only-change-in-prod"


class Settings(BaseSettings):
    APP_ENV: str = "local"
    DATABASE_URL: str = "sqlite:///./mindweave.db"
    MODEL_PROVIDER: str = "lmstudio"
    LMSTUDIO_BASE_URL: str = "http://127.0.0.1:1234/v1"
    # Empty or legacy placeholder is resolved at chat time via GET /v1/models (first id), or set explicitly.
    LMSTUDIO_MODEL: str = ""
    LMSTUDIO_CHAT_TIMEOUT: float = (
        3600.0  # 1 hour for large/slow local models / long structured outputs (override via env)
    )
    # Server-wide LM Studio API key: required for GET /api/v1/models/ (shared picker list). Chat/workflows
    # still prefer User.api_keys lmstudio_api_key when set, else this env. See lmstudio_http.resolve_lmstudio_bearer.
    LMSTUDIO_API_KEY: str = ""
    # Native POST /api/v1/models/load can block for large models.
    LMSTUDIO_MODEL_LOAD_TIMEOUT: float = 300.0
    # After a successful POST /api/v1/models/load, poll native GET /api/v1/models until this model
    # reports loaded_instances (or timeout). POST can return before chat/completions is ready.
    # Set to 0 to skip polling (chat retries still apply).
    LMSTUDIO_MODEL_READY_MAX_WAIT_SECONDS: float = 60.0
    # Total wall-clock budget for transient retries on POST /v1/chat/completions.
    LMSTUDIO_CHAT_RETRY_BUDGET_SECONDS: float = 120.0

    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    CORS_ALLOW_METHODS: List[str] = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]
    CORS_ALLOW_HEADERS: List[str] = [
        "Authorization",
        "Content-Type",
        "Accept",
    ]
    # Host header allowlist (include `testserver` for FastAPI TestClient).
    TRUSTED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]
    # Set True only when the app is served exclusively over HTTPS (reverse proxy TLS).
    SECURITY_ENABLE_HSTS: bool = False
    # When True, trust X-Forwarded-* from nginx (same host). Enables correct scheme/client in ASGI scope.
    BEHIND_REVERSE_PROXY: bool = False

    AUTH_LOGIN_RATE_LIMIT: str = "30/minute"
    AUTH_REGISTER_RATE_LIMIT: str = "15/minute"
    AUTH_REFRESH_RATE_LIMIT: str = "60/minute"
    AUTH_GOOGLE_SESSION_RATE_LIMIT: str = "30/minute"
    # POST workflow run + Build enqueue (/runs) combined, per client IP (SE-029).
    WORKFLOW_RUN_RATE_LIMIT: str = "60/minute"

    BIN_RETENTION_DAYS: int = 30
    PURGE_INTERVAL_HOURS: int = 6
    # Delete workflow runs (and node logs) older than this many days. 0 = disable purge.
    WORKFLOW_RUN_LOG_RETENTION_DAYS: int = 90

    SECRET_KEY: str = _DEV_SECRET_PLACEHOLDER
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # When True and the database has no users, seed admin / admin (local/dev only — avoid in production).
    BOOTSTRAP_DEFAULT_ADMIN: bool = False

    # When False, POST /auth/register returns 403 (SE-008).
    OPEN_REGISTRATION: bool = True

    # Google OAuth (for account association)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Separate OAuth redirect for Gmail/Calendar workflow scopes (add in Google Cloud Console).
    GOOGLE_WORKFLOW_REDIRECT_URI: str = "http://localhost:8000/api/v1/google-workflow/oauth/callback"
    FRONTEND_URL: str = "http://localhost:5173"

    # Sandbox (workflow-driven simulation). When False, sandbox routes return 404.
    SANDBOX_ENABLED: bool = True

    # Companion / Workspace conversational runtime. When False, workspace routes return 404.
    WORKSPACE_ENABLED: bool = True

    # Local TTS bridge (services/tts-bridge). Mind Weave calls it with httpx only.
    TTS_BRIDGE_URL: str = "http://127.0.0.1:8765"
    TTS_BRIDGE_TOKEN: str = ""
    TTS_BRIDGE_PULL_TIMEOUT: float = 3600.0
    TTS_BRIDGE_SYNTH_TIMEOUT: float = 600.0
    TTS_BRIDGE_MAX_AUDIO_BYTES: int = 52_428_800  # 50 MiB — must stay in sync with bridge caps

    # Local STT bridge (services/stt-bridge). Mind Weave calls it with httpx only.
    STT_BRIDGE_URL: str = "http://127.0.0.1:8766"
    STT_BRIDGE_TOKEN: str = ""
    STT_BRIDGE_TIMEOUT: float = 600.0
    STT_AUDIO_WAIT_TIMEOUT: float = 300.0
    """How long execute_scheduled_run waits for the browser to POST recorded audio (seconds)."""
    STT_MAX_AUDIO_UPLOAD_BYTES: int = 78_643_200  # 75 MiB — keep aligned with stt-bridge and frontend

    # Workflow async execution concurrency (SSE / POST runs path + sync /run).
    WORKFLOW_MAX_CONCURRENT_NODES: int = 8
    WORKFLOW_MAX_CONCURRENT_LLM_CALLS: int = 3
    WORKFLOW_MAX_CONCURRENT_BROWSER_TASKS: int = 2
    WORKFLOW_MAX_CONCURRENT_EXTERNAL_SKILL_TASKS: int = 4

    # Workflow execution safety (defaults + hard ceilings; graph/run may request lower values only within ceilings).
    WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS: int = 300
    WORKFLOW_EXECUTION_CEILING_TTL_SECONDS: int = 86_400
    WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS: int = 500
    WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS: int = 500_000
    WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS: int = 50
    WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS: int = 10_000
    WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH: int = 5
    WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH: int = 32
    WORKFLOW_DEFAULT_LOOP_BATCH_SIZE: int = 4
    WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING: int = 128

    # Speech transcription providers (provider-abstracted `transcribe_file` skill).
    # local_whisper wraps the STT bridge; assemblyai is cloud STT (no outbound calls until a run uses it).
    # Operators can set TRANSCRIPTION_PROVIDERS_ENABLED=["local_whisper"] only to hide cloud from the editor.
    TRANSCRIPTION_PROVIDERS_ENABLED: List[str] = ["local_whisper", "assemblyai"]
    TRANSCRIPTION_JOB_POLL_INTERVAL: float = 5.0
    """Lifespan poller cadence for in-flight transcription_jobs (seconds). 0 disables the poller."""

    # AssemblyAI cloud transcription (optional). Server env fallback only — users normally enter
    # a personal key in My Settings → API Settings, encrypted at rest with the standard mechanism.
    ASSEMBLYAI_API_KEY: str = ""
    ASSEMBLYAI_BASE_URL: str = "https://api.assemblyai.com"
    ASSEMBLYAI_UPLOAD_TIMEOUT: float = 300.0
    ASSEMBLYAI_REQUEST_TIMEOUT: float = 60.0
    ASSEMBLYAI_POLL_INTERVAL: float = 3.0
    """Inline poll cadence used by the executor while a stream is attached (seconds)."""
    ASSEMBLYAI_JOB_TIMEOUT: float = 1800.0
    """Total wall-clock budget the executor will wait inline before falling back to the lifespan poller."""
    # AssemblyAI POST /v2/transcript requires a non-empty speech_models list (2025+ API).
    # Allowed ids include universal-3-pro and universal-2; default follows Universal Speech Model docs.
    ASSEMBLYAI_SPEECH_MODELS: List[str] = ["universal-3-pro"]

    # workflow fetch_url skill: httpx to arbitrary URLs (server-side; see docs)
    FETCH_URL_DEFAULT_TIMEOUT_MS: int = 30_000
    FETCH_URL_MAX_BODY_BYTES: int = 2_097_152  # 2 MiB cap per response body (streamed; oversized → structured error)

    # capture_url_snapshot: optional extra url-snapshot (Playwright) + Chromium (see docs/OPERATIONS.md)
    CAPTURE_URL_SNAPSHOT_DEFAULT_TIMEOUT_MS: int = 30_000
    CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH: int = 1280
    CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT: int = 720
    CAPTURE_URL_SNAPSHOT_MAX_PNG_BYTES: int = 25_165_824  # 24 MiB cap per screenshot (oversized → structured error)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validate_security_constraints(self) -> Self:
        if self.BOOTSTRAP_DEFAULT_ADMIN and self.APP_ENV != "local":
            raise ValueError(
                "BOOTSTRAP_DEFAULT_ADMIN is only allowed when APP_ENV=local; "
                "create admins with: python -m app.cli create-admin"
            )
        if self.APP_ENV == "local":
            if len(self.SECRET_KEY) < 16:
                raise ValueError(
                    "SECRET_KEY must be at least 16 characters (generate e.g. "
                    '`python -c "import secrets; print(secrets.token_hex(32))"`)'
                )
        elif self.SECRET_KEY == _DEV_SECRET_PLACEHOLDER or len(self.SECRET_KEY) < 32:
            raise ValueError(
                "For APP_ENV other than 'local', SECRET_KEY must be a strong random value "
                "of at least 32 characters. The development default placeholder is not allowed. "
                "Generate one with: openssl rand -hex 32"
            )
        for field_name in (
            "AUTH_LOGIN_RATE_LIMIT",
            "AUTH_REGISTER_RATE_LIMIT",
            "AUTH_REFRESH_RATE_LIMIT",
            "AUTH_GOOGLE_SESSION_RATE_LIMIT",
            "WORKFLOW_RUN_RATE_LIMIT",
        ):
            spec = getattr(self, field_name)
            try:
                parse_per_minute_limit(spec)
            except ValueError as exc:
                raise ValueError(f"{field_name}: {exc}") from exc

        # Execution limit defaults must not exceed their ceilings (avoid misconfigured env).
        if self.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS > self.WORKFLOW_EXECUTION_CEILING_TTL_SECONDS:
            raise ValueError("WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS must be <= WORKFLOW_EXECUTION_CEILING_TTL_SECONDS")
        if (
            self.WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS
            > self.WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS
        ):
            raise ValueError(
                "WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS must be <= "
                "WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS"
            )
        if (
            self.WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS
            > self.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS
        ):
            raise ValueError(
                "WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS must be <= "
                "WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS"
            )
        if self.WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH > self.WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH:
            raise ValueError(
                "WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH must be <= "
                "WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH"
            )
        if self.WORKFLOW_DEFAULT_LOOP_BATCH_SIZE > self.WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING:
            raise ValueError(
                "WORKFLOW_DEFAULT_LOOP_BATCH_SIZE must be <= WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING"
            )
        return self


settings = Settings()
