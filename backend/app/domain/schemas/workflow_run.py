"""Workflow run request/response models."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.domain.execution_limits import ExecutionLimitsOverrides

from .outputs import NodeOutputUnion


def _validate_override_value(val: Any, depth: int) -> None:
    if depth > 10:
        raise ValueError("input_overrides nesting too deep")
    if isinstance(val, dict):
        if len(val) > 64:
            raise ValueError("input_overrides dict too large")
        for v in val.values():
            _validate_override_value(v, depth + 1)
    elif isinstance(val, list):
        if len(val) > 512:
            raise ValueError("input_overrides list too long")
        for v in val:
            _validate_override_value(v, depth + 1)
    elif val is not None and not isinstance(val, (str, int, float, bool)):
        raise ValueError("input_overrides invalid value type")


_MAX_EXECUTION_TIME_ZONE_LEN = 120


class WorkflowRunRequest(BaseModel):
    """Optional request body for run and ``POST …/runs``. Overrides null required inputs."""

    input_overrides: Optional[Dict[str, Any]] = None
    output_overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-node forced outputs (node_id -> JSON value). Skips execution for those nodes.",
    )
    execution_time_zone: Optional[str] = Field(
        default=None,
        description=(
            "Resolved IANA time zone from the client when the user's profile uses 'system'; "
            "used for Gmail after:/before: day mapping when workflow_time_zone is system."
        ),
    )
    execution_limits: Optional[ExecutionLimitsOverrides] = Field(
        default=None,
        description=(
            "Optional per-run caps; merged over workflow graph.execution_limits, "
            "then validated against server ceilings."
        ),
    )
    acknowledge_preflight_warnings: bool = Field(
        default=False,
        description=(
            "When true, allows enqueue/sync run despite advisory preflight warnings "
            "(uncertain loop lists or skipped nested-workflow estimates)."
        ),
    )

    @model_validator(mode="after")
    def _validate_run_request(self):
        z = self.execution_time_zone
        if z is not None:
            if not isinstance(z, str):
                raise ValueError("execution_time_zone must be a string or null")
            if len(z) > _MAX_EXECUTION_TIME_ZONE_LEN:
                raise ValueError("execution_time_zone too long")
        o = self.input_overrides
        if o is not None:
            if len(o) > 64:
                raise ValueError("too many input_overrides keys")
            for k in o:
                if not isinstance(k, str) or len(k) > 256:
                    raise ValueError("invalid override key")
            for v in o.values():
                _validate_override_value(v, 0)
        oo = self.output_overrides
        if oo is not None:
            if len(oo) > 64:
                raise ValueError("too many output_overrides keys")
            for k in oo:
                if not isinstance(k, str) or len(k) > 256:
                    raise ValueError("invalid output_overrides key")
            for v in oo.values():
                _validate_override_value(v, 0)
        return self


# ---------------------------------------------------------------------------
# Workflow Run Result
# ---------------------------------------------------------------------------


class NodeRunResult(BaseModel):
    """Execution result for a single graph node (one row per execution; same node_id may repeat)."""

    node_id: str
    status: Literal["ok", "error"]
    output: Optional[NodeOutputUnion] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    step_number: Optional[int] = Field(
        default=None,
        description="1-based monotonic order within this workflow run (legacy runs omit).",
    )


class WorkflowRunResult(BaseModel):
    """Execution result for an entire workflow run."""

    workflow_id: uuid.UUID
    status: Literal["ok", "partial", "error"]
    node_results: List[NodeRunResult]


class MyWorkflowRunRead(BaseModel):
    """One persisted workflow run in the cross-workflow Explore list."""

    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class WorkflowRunEnqueueResponse(BaseModel):
    """Returned immediately by ``POST …/workflow-definitions/{id}/runs``."""

    run_id: uuid.UUID
    workflow_id: uuid.UUID
    status: Literal["queued"]


class WorkflowRunSnapshotRead(BaseModel):
    """Compact poll snapshot for ``GET …/workflow-runs/{run_id}``."""

    run_id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    last_event_seq: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
