"""Workflow execution limits: defaults, server ceilings, graph/run overrides resolution."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings


class ExecutionLimitsOverrides(BaseModel):
    """Optional limits from user prefs, graph.execution_limits, or run request."""

    workflow_ttl_seconds: Optional[int] = Field(default=None, ge=1)
    max_node_executions: Optional[int] = Field(default=None, ge=1)
    max_loop_iterations: Optional[int] = Field(default=None, ge=1)
    max_nested_depth: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class ResolvedExecutionLimits(BaseModel):
    """Effective caps for a single run."""

    workflow_ttl_seconds: int = Field(ge=1)
    max_node_executions: int = Field(ge=1)
    max_loop_iterations: int = Field(ge=1)
    max_nested_depth: int = Field(ge=1)


def _validate_layer_against_ceilings(layer: ExecutionLimitsOverrides, s: Settings) -> None:
    if layer.workflow_ttl_seconds is not None and layer.workflow_ttl_seconds > s.WORKFLOW_EXECUTION_CEILING_TTL_SECONDS:
        raise ValueError(
            f"execution_limits.workflow_ttl_seconds exceeds server maximum "
            f"({s.WORKFLOW_EXECUTION_CEILING_TTL_SECONDS})"
        )
    if (
        layer.max_node_executions is not None
        and layer.max_node_executions > s.WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS
    ):
        raise ValueError(
            "execution_limits.max_node_executions exceeds server maximum "
            f"({s.WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS})"
        )
    if (
        layer.max_loop_iterations is not None
        and layer.max_loop_iterations > s.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS
    ):
        raise ValueError(
            "execution_limits.max_loop_iterations exceeds server maximum "
            f"({s.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS})"
        )
    if (
        layer.max_nested_depth is not None and layer.max_nested_depth > s.WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH
    ):
        raise ValueError(
            "execution_limits.max_nested_depth exceeds server maximum "
            f"({s.WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH})"
        )


def parse_execution_limits_from_graph(graph: Mapping[str, Any]) -> ExecutionLimitsOverrides | None:
    raw = graph.get("execution_limits")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("graph.execution_limits must be a JSON object")
    return ExecutionLimitsOverrides.model_validate(raw)


def resolve_execution_limits(
    settings: Settings,
    *,
    graph_limits: ExecutionLimitsOverrides | None,
    run_request_limits: ExecutionLimitsOverrides | None,
    user_limits: ExecutionLimitsOverrides | None = None,
) -> ResolvedExecutionLimits:
    """Merge defaults → user prefs → graph → run (last wins); each overlay layer validated vs ceilings."""

    base = ResolvedExecutionLimits(
        workflow_ttl_seconds=settings.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS,
        max_node_executions=settings.WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS,
        max_loop_iterations=settings.WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS,
        max_nested_depth=settings.WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH,
    )
    merged: dict[str, int] = base.model_dump()
    for layer in (user_limits, graph_limits, run_request_limits):
        if layer is None:
            continue
        _validate_layer_against_ceilings(layer, settings)
        if layer.workflow_ttl_seconds is not None:
            merged["workflow_ttl_seconds"] = layer.workflow_ttl_seconds
        if layer.max_node_executions is not None:
            merged["max_node_executions"] = layer.max_node_executions
        if layer.max_loop_iterations is not None:
            merged["max_loop_iterations"] = layer.max_loop_iterations
        if layer.max_nested_depth is not None:
            merged["max_nested_depth"] = layer.max_nested_depth

    return ResolvedExecutionLimits.model_validate(merged)


def execution_limits_ceiling_snapshot(settings: Settings) -> dict[str, int]:
    """Public ceilings for SPA validation (exact server caps)."""
    return {
        "workflow_ttl_seconds": settings.WORKFLOW_EXECUTION_CEILING_TTL_SECONDS,
        "max_node_executions": settings.WORKFLOW_EXECUTION_CEILING_MAX_NODE_EXECUTIONS,
        "max_loop_iterations": settings.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS,
        "max_nested_depth": settings.WORKFLOW_EXECUTION_CEILING_MAX_NESTED_DEPTH,
        "max_loop_batch_size": settings.WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING,
    }


def execution_limits_default_snapshot(settings: Settings) -> dict[str, int]:
    return {
        "workflow_ttl_seconds": settings.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS,
        "max_node_executions": settings.WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS,
        "max_loop_iterations": settings.WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS,
        "max_nested_depth": settings.WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH,
    }


def resolved_execution_limits_to_json(limit: ResolvedExecutionLimits) -> dict[str, int]:
    return limit.model_dump()


def load_execution_limits_from_run_snapshot(
    settings: Settings,
    *,
    workflow_graph: Mapping[str, Any],
    persisted_effective: Any,
    user_limits: ExecutionLimitsOverrides | None = None,
) -> ResolvedExecutionLimits:
    """Use stored snapshot when present (POST /runs); else resolve from defaults/user/graph."""
    if isinstance(persisted_effective, dict) and persisted_effective:
        return ResolvedExecutionLimits.model_validate(dict(persisted_effective))
    gl = parse_execution_limits_from_graph(workflow_graph)
    return resolve_execution_limits(settings, user_limits=user_limits, graph_limits=gl, run_request_limits=None)
