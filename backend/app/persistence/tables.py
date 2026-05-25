"""
Persistence Tables
==================
SQLModel table definitions for all persisted entities.

Entity hierarchy:
  User            — authenticated user account
  Companion       — persistent interactive entity (identity, voice, capability enablement)
  Workspace       — interactive runtime environment (typed configuration, capabilities)
  WorkspaceSession — conversation thread within a Workspace
  WorkspaceTurn   — one user/system cycle with staged runtime payloads
  WorkspaceReplay — redacted observability record for a turn
  CompanionMemoryEntry — durable memory proposal/approval lifecycle
  Persona         — named interface to a model (system prompt + optional default model)
  Palette         — workflow step/handle colors for the graph editor
  SystemPalette   — app-wide light/dark semantic tokens (themes)
  Structure       — JSON schema for structured LLM outputs
  Document        — persisted body text (Markdown, JSON, etc.) for workflows and prompts
  WorkflowProject — user folder grouping workflow definitions (reserved name Shared)
  WorkflowDefinition — a named DAG of nodes (Start, Stop, Primitives, Utilities)
  UrlFetchCache — per-user cached JSON payload for workflow fetch_url skill (deterministic key)
  UrlSnapshotArtifact — per-user stored PNG for workflow capture_url_snapshot skill
  UrlSnapshotCache — per-user cache_key → artifact_id for capture_url_snapshot
  AudioFileArtifact — per-user stored audio file for workflow Audio File Input / Transcribe File
  TranscriptionJob — provider-abstracted speech transcription request lifecycle (`transcribe_file` skill)
  TtsModelArtifact — registered TTS weight bundle (metadata + bridge pull status)
  VoiceSample — user-saved reference WAV + transcript for Qwen voice clone (workflow TTS)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import LargeBinary, String, Text, UniqueConstraint
from sqlmodel import JSON, Column, Field, SQLModel


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """An authenticated user account."""

    __tablename__ = "users"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    settings: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    api_keys: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_admin: bool = Field(default=False)
    google_user_id: Optional[str] = Field(default=None, unique=True, index=True)
    google_email: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)


class Companion(SQLModel, table=True):
    """The user's persistent companion: identity, voice, and governed capability use."""

    __tablename__ = "companions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", unique=True, index=True)
    name: str = Field(default="Companion", index=True)
    description: str = Field(default="")
    persona_id: Optional[uuid.UUID] = Field(default=None, foreign_key="personas.id", index=True)
    identity_profile: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    default_mode: str = Field(default="default")
    available_modes: List[str] = Field(default_factory=lambda: ["default"], sa_column=Column(JSON))
    enabled_workflow_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    memory_policy: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Workspace(SQLModel, table=True):
    """Interactive runtime environment: configuration and available capabilities."""

    __tablename__ = "workspaces"  # type: ignore
    __table_args__ = (UniqueConstraint("owner_user_id", "name", name="uq_workspaces_owner_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(index=True)
    runtime_configuration: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ui_configuration: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    interaction_configuration: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    enabled_workflow_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    interpretation_model: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkspaceSession(SQLModel, table=True):
    """A conversation thread inside a Workspace."""

    __tablename__ = "workspace_sessions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    companion_id: uuid.UUID = Field(foreign_key="companions.id", index=True)
    title: str = Field(default="Chat")
    status: str = Field(default="active", index=True)  # active | archived
    turn_count: int = Field(default=0, ge=0)
    transient_state: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    active_summary: str = Field(default="")
    last_turn_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkspaceTurn(SQLModel, table=True):
    """One processed turn with staged payloads for replay and inspection."""

    __tablename__ = "workspace_turns"  # type: ignore
    __table_args__ = (UniqueConstraint("session_id", "turn_index", name="uq_workspace_turns_session_index"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="workspace_sessions.id", index=True)
    turn_index: int = Field(ge=0, index=True)
    trace_id: str = Field(index=True)
    user_input: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    outcome_type: str = Field(default="respond_directly", index=True)
    interpretation_result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    routing_plan: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    execution_results: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    process_results: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    composition_result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    delivered_response: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class WorkspaceReplay(SQLModel, table=True):
    """Redacted observability snapshot for a Workspace turn."""

    __tablename__ = "workspace_replays"  # type: ignore
    __table_args__ = (UniqueConstraint("turn_id", name="uq_workspace_replays_turn_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    turn_id: uuid.UUID = Field(foreign_key="workspace_turns.id", index=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", index=True)
    session_id: uuid.UUID = Field(foreign_key="workspace_sessions.id", index=True)
    interpretation_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    routing_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    execution_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    process_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    composition_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    delivery_trace: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    state_update_summary: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class CompanionMemoryEntry(SQLModel, table=True):
    """Durable memory with explicit approval (V1: no silent persistence)."""

    __tablename__ = "companion_memory_entries"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    companion_id: uuid.UUID = Field(foreign_key="companions.id", index=True)
    memory_type: str = Field(default="fact", index=True)
    content: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    salience: float = Field(default=0.5)
    source_session_id: Optional[uuid.UUID] = Field(default=None, foreign_key="workspace_sessions.id", index=True)
    source_turn_id: Optional[uuid.UUID] = Field(default=None, foreign_key="workspace_turns.id", index=True)
    visibility_policy: str = Field(default="user_only")
    approval_status: str = Field(default="proposed", index=True)  # proposed | approved | rejected | revoked
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Persona(SQLModel, table=True):
    """A named interface to a language model: system prompt + optional default model."""

    __tablename__ = "personas"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(unique=True, index=True)
    type: str = Field(default="custom", index=True)  # "custom" | "system"
    description: str
    system_prompt: str
    default_model: Optional[str] = Field(default=None)  # Optional model override
    is_default: bool = Field(default=False)
    creativity: float = Field(default=0.2)
    suppress_lm_thinking: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Palette(SQLModel, table=True):
    """Mapping of Primitive types (string, list, dictionary, any) to hex colors for handles/edges."""

    __tablename__ = "palettes"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    slug: Optional[str] = Field(default=None, unique=True, index=True)
    colors: Dict[str, str] = Field(
        default_factory=lambda: {
            "string": "#38bdf8",
            "list": "#f472b6",
            "dictionary": "#e879f9",
            "structure": "#a78bfa",
            "document": "#2dd4bf",
            "gmail": "#f97316",
            "read_document_property": "#14b8a6",
            "any": "#ffffff",
            "workflow": "#14b8a6",
            "simple_llm_call": "#8b5cf6",
            "multimodal_llm": "#6366f1",
            "gmail_list_messages": "#ea4335",
            "calendar_list_events": "#4285f4",
            "fetch_url": "#0ea5e9",
        },
        sa_column=Column(JSON),
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SystemPalette(SQLModel, table=True):
    """App-wide UI theme: light/dark semantic color tokens (JSON)."""

    __tablename__ = "system_palettes"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    slug: Optional[str] = Field(default=None, unique=True, index=True)
    colors: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Structure(SQLModel, table=True):
    """JSON schema for structured LLM outputs (LM Studio response_format)."""

    __tablename__ = "structures"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    # Map to schema_json column for DB compatibility (Python attr json_schema avoids shadowing SQLModel.schema)
    json_schema: str = Field(default="{}", sa_column=Column("schema_json", String, nullable=False, server_default="{}"))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Document(SQLModel, table=True):
    """User-editable persisted text (`body`): Markdown, JSON, config, or hybrid—workflows interpret content."""

    __tablename__ = "documents"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(unique=True, index=True)
    description: str = Field(default="")
    body: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowProject(SQLModel, table=True):
    """Single-level folder for organizing workflow definitions per user."""

    __tablename__ = "workflow_projects"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "name_lower", name="uq_workflow_projects_user_name_lower"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(index=True)
    name_lower: str = Field(index=True)
    sort_order: int = Field(default=0, index=True)
    sandbox_enabled: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowDefinition(SQLModel, table=True):
    """A named DAG of nodes (Start, Stop, Primitives, Utilities) stored as embedded JSON."""

    __tablename__ = "workflow_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    palette_id: Optional[uuid.UUID] = Field(default=None, foreign_key="palettes.id", index=True)
    project_id: Optional[uuid.UUID] = Field(default=None, foreign_key="workflow_projects.id", index=True)
    expose_as_custom_skill: bool = Field(default=False, index=True)
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, index=True, unique=True)
    graph: Dict[str, Any] = Field(
        default_factory=lambda: {"nodes": [], "edges": []},
        sa_column=Column(JSON),
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class BoardProject(SQLModel, table=True):
    """Single-level folder for organizing sandbox boards per user."""

    __tablename__ = "board_projects"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "name_lower", name="uq_board_projects_user_name_lower"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(index=True)
    name_lower: str = Field(index=True)
    sort_order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SandboxBoard(SQLModel, table=True):
    """Persisted sandbox board template (grid, items, optional creature placements)."""

    __tablename__ = "sandbox_boards"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    project_id: Optional[uuid.UUID] = Field(default=None, foreign_key="board_projects.id", index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    body: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, index=True, unique=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UrlFetchCache(SQLModel, table=True):
    """Cached successful fetch_url response payload for reuse (default cache policy)."""

    __tablename__ = "url_fetch_caches"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "cache_key", name="uq_url_fetch_caches_user_key"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    cache_key: str = Field(max_length=64, index=True)
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utc_now)


class UrlSnapshotArtifact(SQLModel, table=True):
    """User-owned PNG (or other image) bytes from workflow capture_url_snapshot runs."""

    __tablename__ = "url_snapshot_artifacts"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    image_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    mime_type: str = Field(default="image/png", max_length=64)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    final_url: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UrlSnapshotCache(SQLModel, table=True):
    """Maps deterministic cache key to a url_snapshot_artifacts row (default/refresh policy)."""

    __tablename__ = "url_snapshot_caches"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "cache_key", name="uq_url_snapshot_caches_user_key"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    cache_key: str = Field(max_length=64, index=True)
    artifact_id: uuid.UUID = Field(foreign_key="url_snapshot_artifacts.id", index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class AudioFileArtifact(SQLModel, table=True):
    """User-owned audio bytes selected for Audio File Input workflow transcription.

    The ``transient`` flag distinguishes operator-saved artifacts (persisted via the
    ``/audio-file-artifacts`` API) from runtime uploads spilled to the table for
    restart-resume of long-running cloud transcription. Transient rows are cleaned up
    after their owning ``transcription_jobs`` row reaches a terminal status.
    """

    __tablename__ = "audio_file_artifacts"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    filename: str = Field(index=True, max_length=512)
    mime_type: str = Field(default="application/octet-stream", max_length=128)
    size_bytes: int = Field(ge=1)
    audio_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    transient: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TranscriptionJob(SQLModel, table=True):
    """Persisted record of a provider-abstracted transcription request.

    Created by the executor when a `transcribe_file` skill node runs. Survives client
    disconnects and process restarts: the lifespan poller advances rows in flight, and
    the workflow run resumes from the persisted state on reattach.

    Audio bytes are NOT stored on this row directly — they live in `audio_file_artifacts`
    (operator-saved or transient). `audio_artifact_id` links them so the executor can
    re-submit on retries without re-uploading from the browser.
    """

    __tablename__ = "transcription_jobs"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    run_id: Optional[uuid.UUID] = Field(default=None, foreign_key="workflow_runs.id", index=True)
    node_id: Optional[str] = Field(default=None, max_length=255, index=True)
    for_loop_id: Optional[str] = Field(default=None, max_length=255)
    for_loop_iteration: Optional[int] = Field(default=None)

    provider: str = Field(max_length=64, index=True)
    provider_job_id: Optional[str] = Field(default=None, max_length=255, index=True)
    status: str = Field(max_length=32, index=True)
    """One of: submitting | queued | processing | completed | error | cancelled."""

    audio_artifact_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="audio_file_artifacts.id",
        index=True,
    )
    audio_filename: str = Field(max_length=512)
    audio_mime_type: str = Field(default="application/octet-stream", max_length=128)
    audio_size_bytes: int = Field(ge=0)

    options_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    transcript_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    provider_error: Optional[str] = Field(default=None, sa_column=Column(Text))

    submitted_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    last_polled_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowRun(SQLModel, table=True):
    """A single execution run of a WorkflowDefinition."""

    __tablename__ = "workflow_runs"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workflow_id: uuid.UUID = Field(foreign_key="workflow_definitions.id", index=True)
    started_by_user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    # queued | running | completed | failed | canceled — legacy ok/partial/error migrated to completed/failed
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    last_event_seq: int = Field(default=0, ge=0)
    # Effective execution caps for this run (defaults + graph.execution_limits + request merge).
    execution_limits_effective: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
    )


class OAuthStateRecord(SQLModel, table=True):
    """OAuth CSRF state (login or associate). Replaces in-memory store for multi-worker use."""

    __tablename__ = "oauth_states"  # type: ignore

    state: str = Field(primary_key=True, max_length=128)
    kind: str = Field(index=True)  # "login" | "associate"
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    expires_at: datetime = Field(index=True)


class OAuthSessionCode(SQLModel, table=True):
    """One-time code exchanged via POST after Google redirect (avoids JWT in URL)."""

    __tablename__ = "oauth_session_codes"  # type: ignore

    code: str = Field(primary_key=True, max_length=128)
    username: str = Field(index=True)
    expires_at: datetime = Field(index=True)


class GoogleWorkflowConnection(SQLModel, table=True):
    """Per-user Google OAuth connection for workflow skills (Gmail/Calendar read-only, etc.)."""

    __tablename__ = "google_workflow_connections"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "google_sub", name="uq_gwc_user_google_sub"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    google_sub: str = Field(max_length=255, index=True)
    google_email: Optional[str] = Field(default=None, max_length=320)
    label: Optional[str] = Field(default=None, max_length=128)
    refresh_token_encrypted: str = Field(sa_column=Column(String(4096), nullable=False))
    access_token_encrypted: Optional[str] = Field(default=None, sa_column=Column(String(4096)))
    access_token_expires_at: Optional[datetime] = Field(default=None)
    scopes: str = Field(max_length=1024)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RevokedRefreshToken(SQLModel, table=True):
    """Refresh JWT `jti` revoked after rotation or logout (SE-010)."""

    __tablename__ = "revoked_refresh_tokens"  # type: ignore

    jti: str = Field(primary_key=True, max_length=128)
    expires_at: datetime = Field(index=True)


class NodeRunLog(SQLModel, table=True):
    """A granular log for a specific node during a WorkflowRun."""

    __tablename__ = "node_run_logs"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="workflow_runs.id", index=True)
    node_id: str = Field(index=True)  # The string ID from the workflow graph
    step_number: Optional[int] = Field(default=None, index=True)
    status: str  # "ok", "error"
    output_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = Field(default=None)
    latency_ms: Optional[float] = Field(default=None)
    details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class TtsModelArtifact(SQLModel, table=True):
    """Metadata for a TTS model bundle materialized under TTS_MODEL_ROOT by the bridge (no weights in DB)."""

    __tablename__ = "tts_model_artifacts"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    display_name: str = Field(index=True, max_length=256)
    engine: str = Field(index=True, max_length=64)  # e.g. qwen_torch, qwen_mlx
    source: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    local_key: str = Field(default="", max_length=512)  # relative path/key returned by the bridge after pull
    status: str = Field(default="pending", index=True)  # pending | ready | failed
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ItemDefinition(SQLModel, table=True):
    """Pickable sandbox item template (e.g. food, ball)."""

    __tablename__ = "item_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    label: str = Field(default="")
    default_energy: Optional[int] = Field(default=48)
    default_color: Optional[str] = Field(default=None)
    shape: str = Field(default="circle")
    pickable: bool = Field(default=True)
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TerrainDefinition(SQLModel, table=True):
    """Solid terrain template (e.g. wall)."""

    __tablename__ = "terrain_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    label: str = Field(default="")
    default_color: Optional[str] = Field(default=None)
    shape: str = Field(default="rect")
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FixtureDefinition(SQLModel, table=True):
    """Workflow-powered solid interactable template."""

    __tablename__ = "fixture_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    label: str = Field(default="")
    workflow_id: str = Field(default="")
    color: Optional[str] = Field(default=None)
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CreatureDefinition(SQLModel, table=True):
    """Full creature placement template."""

    __tablename__ = "creature_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    label: str = Field(default="")
    workflow_id: str = Field(default="")
    default_color: str = Field(default="#3B82F6")
    default_facing: str = Field(default="N")
    default_inventory: list = Field(default_factory=list, sa_column=Column(JSON))
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RegionDefinition(SQLModel, table=True):
    """Region underlay template with trigger config."""

    __tablename__ = "region_definitions"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(index=True)
    label: str = Field(default="")
    color: str = Field(default="#3B82F6")
    trigger: dict = Field(default_factory=dict, sa_column=Column(JSON))
    is_system: bool = Field(default=False, index=True)
    builtin_slug: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class VoiceSample(SQLModel, table=True):
    """Reference audio + transcript for Qwen3-TTS Base voice clone; created from Voice Design previews."""

    __tablename__ = "voice_samples"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "name_lower", name="uq_voice_samples_user_name_lower"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(index=True, max_length=256)
    name_lower: str = Field(index=True, max_length=256)
    ref_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    ref_audio: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    language: str = Field(default="English", max_length=64)
    instruct: str = Field(default="", sa_column=Column(Text, nullable=False))
    design_model_id: Optional[uuid.UUID] = Field(default=None, foreign_key="tts_model_artifacts.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
