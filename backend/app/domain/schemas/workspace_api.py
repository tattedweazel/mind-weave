"""API request/response models for Companion and Workspace."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_workflow_id_list(v: object) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (str, bytes, dict)):
        return []
    if not isinstance(v, Iterable):
        return []
    out: List[str] = []
    for x in v:
        out.append(str(UUID(str(x))))
    return out


class CompanionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    name: str
    description: str
    persona_id: Optional[UUID] = None
    identity_profile: Dict[str, Any] = Field(default_factory=dict)
    default_mode: str = "default"
    available_modes: List[str] = Field(default_factory=lambda: ["default"])
    enabled_workflow_ids: List[str] = Field(default_factory=list)
    memory_policy: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("enabled_workflow_ids", mode="before")
    @classmethod
    def _coerce_wf_ids(cls, v: object) -> List[str]:
        return _normalize_workflow_id_list(v)


class CompanionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    persona_id: Optional[UUID] = None
    identity_profile: Optional[Dict[str, Any]] = None
    default_mode: Optional[str] = None
    available_modes: Optional[List[str]] = None
    enabled_workflow_ids: Optional[List[str]] = None
    memory_policy: Optional[Dict[str, Any]] = None

    @field_validator("enabled_workflow_ids", mode="before")
    @classmethod
    def _coerce_wf_ids(cls, v: object) -> Optional[List[str]]:
        if v is None:
            return None
        return _normalize_workflow_id_list(v)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    name: str
    runtime_configuration: Dict[str, Any] = Field(default_factory=dict)
    ui_configuration: Dict[str, Any] = Field(default_factory=dict)
    interaction_configuration: Dict[str, Any] = Field(default_factory=dict)
    enabled_workflow_ids: List[str] = Field(default_factory=list)
    interpretation_model: Optional[str] = None
    default_google_workflow_connection_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("enabled_workflow_ids", mode="before")
    @classmethod
    def _coerce_wf_ids(cls, v: object) -> List[str]:
        return _normalize_workflow_id_list(v)


class WorkspaceCreate(BaseModel):
    name: str = "Companion Chat"
    runtime_configuration: Dict[str, Any] = Field(default_factory=dict)
    ui_configuration: Dict[str, Any] = Field(default_factory=dict)
    interaction_configuration: Dict[str, Any] = Field(default_factory=dict)
    enabled_workflow_ids: List[str] = Field(default_factory=list)
    interpretation_model: Optional[str] = None
    default_google_workflow_connection_id: Optional[UUID] = None

    @field_validator("enabled_workflow_ids", mode="before")
    @classmethod
    def _coerce_wf_ids(cls, v: object) -> List[str]:
        return _normalize_workflow_id_list(v)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    runtime_configuration: Optional[Dict[str, Any]] = None
    ui_configuration: Optional[Dict[str, Any]] = None
    interaction_configuration: Optional[Dict[str, Any]] = None
    enabled_workflow_ids: Optional[List[str]] = None
    interpretation_model: Optional[str] = None
    default_google_workflow_connection_id: Optional[UUID] = None

    @field_validator("enabled_workflow_ids", mode="before")
    @classmethod
    def _coerce_wf_ids(cls, v: object) -> Optional[List[str]]:
        if v is None:
            return None
        return _normalize_workflow_id_list(v)


class WorkspaceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    companion_id: UUID
    title: str
    status: str
    turn_count: int
    transient_state: Dict[str, Any] = Field(default_factory=dict)
    active_summary: str = ""
    last_turn_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceSessionCreate(BaseModel):
    title: str = "Chat"


class WorkspaceTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    turn_index: int
    trace_id: str
    user_input: str
    outcome_type: str
    created_at: datetime


class WorkspaceTurnTracesRead(BaseModel):
    """Redacted stage payloads for Workspace debugging (same rules as replay traces)."""

    interpretation_result: Optional[Dict[str, Any]] = None
    routing_plan: Optional[Dict[str, Any]] = None
    execution_results: Optional[Dict[str, Any]] = None
    process_results: Optional[Dict[str, Any]] = None
    composition_result: Optional[Dict[str, Any]] = None
    delivered_response: Optional[Dict[str, Any]] = None


class WorkspaceTurnDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    turn_index: int
    trace_id: str
    user_input: str
    outcome_type: str
    created_at: datetime
    traces: WorkspaceTurnTracesRead


class TurnSubmitBody(BaseModel):
    """User message for a Workspace turn."""

    message: str = Field(..., min_length=1, max_length=32000)


class TurnConfirmBody(BaseModel):
    """Confirm or cancel a pending capability proposal from the same session."""

    proposal_id: str = Field(..., min_length=1, max_length=128)
    cancel: bool = False


class MemoryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    companion_id: UUID
    memory_type: str
    content: str
    salience: float
    approval_status: str
    created_at: datetime
    updated_at: datetime


class MemoryApproveBody(BaseModel):
    """Approve or reject a proposed memory."""

    decision: Literal["approved", "rejected"]


class WorkspaceBootstrapResponse(BaseModel):
    """Default companion, workspace, and active chat session."""

    companion: CompanionRead
    workspace: WorkspaceRead
    session: WorkspaceSessionRead


class WorkspaceProcessPreviewItem(BaseModel):
    id: str
    kind: str
    enabled: bool
    name: str
    model: Optional[str] = None
    description: str = ""
    max_iterations: int = 3
    questions: List[str] = Field(default_factory=list)


class WorkspacePostComposePreviewItem(BaseModel):
    id: str
    enabled: bool
    name: str
    model: Optional[str] = None
    output_key: str
    replace_streamed_reply: bool
    user_prompt_rendered: str


class WorkspacePipelinePreviewResponse(BaseModel):
    """Resolved pipeline prompts and models for the Workspace Pipeline UI (no LLM calls)."""

    version: int
    models: Dict[str, Optional[str]]
    interpret_system: str
    compose_system: str
    session_summary_system: str
    process: List[WorkspaceProcessPreviewItem] = Field(default_factory=list)
    post_compose: List[WorkspacePostComposePreviewItem]
