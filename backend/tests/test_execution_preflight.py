"""Unit tests for static execution preflight (budget upper bounds)."""

from app.core.config import settings
from app.domain.execution_limits import ResolvedExecutionLimits
from app.domain.execution_preflight import evaluate_execution_preflight


def _limits(max_node_executions: int) -> ResolvedExecutionLimits:
    return ResolvedExecutionLimits(
        workflow_ttl_seconds=settings.WORKFLOW_EXECUTION_DEFAULT_TTL_SECONDS,
        max_node_executions=max_node_executions,
        max_loop_iterations=settings.WORKFLOW_EXECUTION_DEFAULT_MAX_LOOP_ITERATIONS,
        max_nested_depth=settings.WORKFLOW_EXECUTION_DEFAULT_MAX_NESTED_DEPTH,
    )


def test_preflight_hard_block_when_certain_estimate_exceeds_cap():
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    s1 = "n_s1"
    s2 = "n_s2"
    stop_id = "n_stop"
    graph = {
        "nodes": [
            {
                "id": start_id,
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": []},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": list_id,
                "kind": "primitive",
                "primitive_type": "list",
                "label": "List",
                "data": [1] * 30,
                "position": {"x": 0, "y": 0},
            },
            {
                "id": fl_id,
                "kind": "control",
                "control_type": "for_loop",
                "label": "Loop",
                "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": s1,
                "kind": "primitive",
                "primitive_type": "string",
                "label": "a",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": s2,
                "kind": "primitive",
                "primitive_type": "string",
                "label": "b",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": stop_id,
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [
            {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
            {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": fl_id, "target": s1, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": fl_id, "target": s1, "source_handle": "item", "target_handle": "input"},
            {"source": s1, "target": s2, "source_handle": "output", "target_handle": "input"},
            {"source": s1, "target": s2, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": s2, "target": stop_id, "source_handle": "output"},
            {"source": s2, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
        ],
    }
    eff = _limits(max_node_executions=40)
    r = evaluate_execution_preflight(graph, eff)
    assert r.hard_block_message is not None
    assert not r.requires_acknowledgement
    assert "exceeds" in (r.hard_block_message or "").lower()


def test_preflight_requires_ack_when_uncertain_and_estimate_high():
    start_id = "n_start"
    list_id = "n_list"
    fl_id = "n_fl"
    s1 = "n_s1"
    stop_id = "n_stop"
    graph = {
        "nodes": [
            {
                "id": start_id,
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": []},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": list_id,
                "kind": "primitive",
                "primitive_type": "list",
                "label": "List",
                "data": [1],
                "position": {"x": 0, "y": 0},
            },
            {
                "id": fl_id,
                "kind": "control",
                "control_type": "for_loop",
                "label": "Loop",
                "data": {"required_inputs": [{"key": "input", "type": "list", "value": None}]},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": s1,
                "kind": "primitive",
                "primitive_type": "string",
                "label": "a",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": stop_id,
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [
            {"source": start_id, "target": list_id, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
            {"source": list_id, "target": fl_id, "source_handle": "output", "target_handle": "input"},
            {"source": list_id, "target": fl_id, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": fl_id, "target": s1, "source_handle": "signal_out", "target_handle": "trigger"},
            {"source": fl_id, "target": s1, "source_handle": "item", "target_handle": "input"},
            {"source": s1, "target": stop_id, "source_handle": "output"},
            {"source": s1, "target": stop_id, "source_handle": "signal_out", "target_handle": "trigger"},
        ],
    }
    eff = _limits(max_node_executions=40)
    r = evaluate_execution_preflight(graph, eff, acknowledge_preflight_warnings=False)
    assert r.hard_block_message is None
    assert r.requires_acknowledgement
    r2 = evaluate_execution_preflight(graph, eff, acknowledge_preflight_warnings=True)
    assert r2.ok_without_ack


def test_preflight_minimal_graph_ok():
    r = evaluate_execution_preflight(
        {
            "nodes": [
                {
                    "id": "n_str",
                    "kind": "primitive",
                    "primitive_type": "string",
                    "label": "S",
                    "data": {"text": "x"},
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "n_stop",
                    "kind": "stop",
                    "label": "Stop",
                    "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                    "position": {"x": 0, "y": 0},
                },
            ],
            "edges": [{"source": "n_str", "target": "n_stop"}],
        },
        _limits(500),
    )
    assert r.ok_without_ack
