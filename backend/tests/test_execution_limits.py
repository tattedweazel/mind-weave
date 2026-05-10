"""Unit tests for workflow execution limit resolution (no HTTP, no LLM)."""

import pytest

from app.core.config import Settings
from app.domain.execution_limits import (
    ExecutionLimitsOverrides,
    parse_execution_limits_from_graph,
    resolve_execution_limits,
)


def _minimal_settings() -> Settings:
    return Settings()


def test_resolve_execution_defaults_only():
    s = _minimal_settings()
    r = resolve_execution_limits(s, graph_limits=None, run_request_limits=None)
    assert r.workflow_ttl_seconds == s.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS
    assert r.max_node_executions == s.WORKFLOW_EXECUTION_DEFAULT_MAX_NODE_EXECUTIONS
    assert r.max_loop_iterations == s.WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS
    assert r.max_nested_depth == s.WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH


def test_resolve_execution_graph_overlays_defaults_run_wins_over_graph():
    s = _minimal_settings()
    graph_layer = ExecutionLimitsOverrides(max_loop_iterations=42)
    run_layer = ExecutionLimitsOverrides(max_loop_iterations=99)
    r = resolve_execution_limits(s, graph_limits=graph_layer, run_request_limits=run_layer)
    assert r.max_loop_iterations == 99


def test_resolve_user_prefs_between_defaults_and_graph_and_run_wins():
    """Merge order: defaults → user → graph → run (run highest precedence)."""
    s = _minimal_settings()
    user_layer = ExecutionLimitsOverrides(max_loop_iterations=80, max_nested_depth=3)
    graph_layer = ExecutionLimitsOverrides(max_loop_iterations=90)
    run_layer = ExecutionLimitsOverrides(max_loop_iterations=91)
    r = resolve_execution_limits(
        s,
        user_limits=user_layer,
        graph_limits=graph_layer,
        run_request_limits=run_layer,
    )
    assert r.max_loop_iterations == 91
    assert r.max_nested_depth == 3
    only_user = resolve_execution_limits(s, user_limits=user_layer, graph_limits=None, run_request_limits=None)
    assert only_user.max_loop_iterations == 80
    assert only_user.max_nested_depth == 3
    assert only_user.workflow_ttl_seconds == s.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS


def test_parse_execution_limits_from_graph_returns_none_when_absent():
    assert parse_execution_limits_from_graph({"nodes": [], "edges": []}) is None


def test_resolve_user_prefs_rejected_above_ceiling():
    s = _minimal_settings()
    bad_user = ExecutionLimitsOverrides(
        max_loop_iterations=s.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS + 1,
    )
    with pytest.raises(ValueError, match="exceeds server maximum"):
        resolve_execution_limits(s, user_limits=bad_user, graph_limits=None, run_request_limits=None)


def test_parse_execution_limits_invalid_type_raises():
    with pytest.raises(ValueError, match="must be a JSON object"):
        parse_execution_limits_from_graph({"execution_limits": "nope"})


def test_resolve_rejects_above_ceiling():
    s = _minimal_settings()
    bad = ExecutionLimitsOverrides(workflow_ttl_seconds=s.WORKFLOW_EXECUTION_CEILING_TTL_SECONDS + 1)
    with pytest.raises(ValueError, match="exceeds server maximum"):
        resolve_execution_limits(s, graph_limits=bad, run_request_limits=None)
