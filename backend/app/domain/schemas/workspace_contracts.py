"""Strict stage contracts for Workspace turn processing (Companion & Workspace spec §22–23)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TurnOutcomeType(str, Enum):
    respond_directly = "respond_directly"
    clarify = "clarify"
    invoke_capabilities = "invoke_capabilities"
    decline_or_block = "decline_or_block"


class StageStatus(str, Enum):
    success = "success"
    needs_clarification = "needs_clarification"
    blocked = "blocked"
    failed = "failed"


class MemoryApprovalStatus(str, Enum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    revoked = "revoked"


class StageEnvelope(BaseModel):
    """Common wrapper for stage outputs (spec §23.2)."""

    stage: str
    status: StageStatus
    workspace_id: UUID
    session_id: UUID
    turn_id: UUID
    created_at: datetime
    trace_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntentPayload(BaseModel):
    key: str = ""
    summary: str = ""


class AmbiguityPayload(BaseModel):
    is_ambiguous: bool = False
    reasons: List[str] = Field(default_factory=list)


class PolicyFlagsPayload(BaseModel):
    blocked: bool = False
    reasons: List[str] = Field(default_factory=list)


class CandidateCapability(BaseModel):
    capability_key: str
    confidence: float = 0.0
    input_bindings: Dict[str, Any] = Field(default_factory=dict)


class InterpretationPayload(BaseModel):
    intent: IntentPayload
    outcome_type: TurnOutcomeType
    confidence: float = 0.0
    ambiguity: AmbiguityPayload = Field(default_factory=AmbiguityPayload)
    policy_flags: PolicyFlagsPayload = Field(default_factory=PolicyFlagsPayload)
    candidate_capabilities: List[CandidateCapability] = Field(default_factory=list)
    normalized_inputs: Dict[str, Any] = Field(default_factory=dict)
    clarification: Optional[str] = None
    preferred_mode_hint: Optional[str] = None
    debug: Dict[str, Any] = Field(default_factory=dict)


class InterpretationResult(BaseModel):
    """Structured interpretation (no direct capability execution)."""

    payload: InterpretationPayload


class SelectedCapability(BaseModel):
    capability_key: str
    input_bindings: Dict[str, Any] = Field(default_factory=dict)
    preferred_mode: Optional[str] = None
    requires_confirmation: bool = False


class PermissionChecksPayload(BaseModel):
    workspace_allows: bool = True
    companion_allows: bool = True
    blocked_reasons: List[str] = Field(default_factory=list)


class PolicyDecisionsPayload(BaseModel):
    confirmation_required: bool = False
    blocked: bool = False
    fallback_allowed: bool = False


class RoutingPayload(BaseModel):
    selected_capabilities: List[SelectedCapability] = Field(default_factory=list)
    execution_order: List[str] = Field(default_factory=list)
    dependency_rules: List[Dict[str, Any]] = Field(default_factory=list)
    permission_checks: PermissionChecksPayload = Field(default_factory=PermissionChecksPayload)
    policy_decisions: PolicyDecisionsPayload = Field(default_factory=PolicyDecisionsPayload)
    composition_strategy: Optional[str] = None
    debug: Dict[str, Any] = Field(default_factory=dict)


class RoutingPlan(BaseModel):
    payload: RoutingPayload


class CapabilityRunResult(BaseModel):
    capability_key: str
    status: Literal["success", "error"]
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    user_visible_candidates: Optional[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPayload(BaseModel):
    capability_results: List[CapabilityRunResult] = Field(default_factory=list)
    execution_summary: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    payload: ExecutionPayload


class ProcessStepResult(BaseModel):
    """Result of a single process pipeline step."""

    step_id: str
    kind: str
    status: Literal["success", "error"] = "success"
    output: str = ""
    iterations_used: int = 1
    approved: Optional[bool] = None
    error: Optional[str] = None


class ProcessPayload(BaseModel):
    """Aggregated results from all process pipeline steps."""

    step_results: List[ProcessStepResult] = Field(default_factory=list)
    debug: Dict[str, Any] = Field(default_factory=dict)


class ProcessResult(BaseModel):
    payload: ProcessPayload


class ResponsePayloadContent(BaseModel):
    response_type: str = "conversational"
    content: str = ""
    structured_blocks: List[Dict[str, Any]] = Field(default_factory=list)


class CompositionPayload(BaseModel):
    response_payload: ResponsePayloadContent = Field(default_factory=ResponsePayloadContent)
    internal_notes: Dict[str, Any] = Field(default_factory=dict)
    memory_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    state_update_proposals: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


class CompositionResult(BaseModel):
    payload: CompositionPayload


class FinalUserResponsePayload(BaseModel):
    rendered_text: str = ""
    render_mode: str = "chat_message"
    visible_capability_indicators: List[str] = Field(default_factory=list)


class DeliveryPayload(BaseModel):
    final_user_response: FinalUserResponsePayload = Field(default_factory=FinalUserResponsePayload)
    applied_companion_mode: Optional[str] = None
    delivery_metadata: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


class DeliveryResult(BaseModel):
    payload: DeliveryPayload


class PostTurnPayload(BaseModel):
    session_updates: Dict[str, Any] = Field(default_factory=dict)
    replay_record: Dict[str, Any] = Field(default_factory=dict)
    memory_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    audit_summary: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


class MemoryProposalCreate(BaseModel):
    """Candidate durable memory before user approval."""

    content: str
    memory_type: str = "fact"
    salience: float = 0.5
