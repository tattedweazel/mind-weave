"""Tests for sandbox workflow → DecisionIntent extraction."""

import uuid

from app.domain.sandbox.workflow_bridge import (
    decision_intent_from_workflow_result,
    graph_requires_simulation_user_action,
    prompt_user_action_node_id_from_graph,
)
from app.domain.schemas.outputs import DictionaryNodeOutput
from app.domain.schemas.sandbox import DecisionIntent
from app.domain.schemas.workflow_run import NodeRunResult, WorkflowRunResult


def test_decision_intent_from_workflow_rejects_empty_stop_dictionary():
    stop_id = "stop1"
    graph_nodes = [{"id": stop_id, "kind": "stop"}]
    result = WorkflowRunResult(
        workflow_id=uuid.uuid4(),
        status="ok",
        node_results=[
            NodeRunResult(
                node_id=stop_id,
                status="ok",
                output=DictionaryNodeOutput(node_id=stop_id, data={}),
            )
        ],
    )
    dec, err = decision_intent_from_workflow_result(result, graph_nodes)
    assert dec is None
    assert err is not None
    assert "empty object" in (err or "").lower()


def test_decision_intent_from_workflow_accepts_valid_intent_dict():
    stop_id = "stop1"
    graph_nodes = [{"id": stop_id, "kind": "stop"}]
    data = DecisionIntent(action="move_forward", reason=None).model_dump(mode="json")
    result = WorkflowRunResult(
        workflow_id=uuid.uuid4(),
        status="ok",
        node_results=[
            NodeRunResult(
                node_id=stop_id,
                status="ok",
                output=DictionaryNodeOutput(node_id=stop_id, data=data),
            )
        ],
    )
    dec, err = decision_intent_from_workflow_result(result, graph_nodes)
    assert err is None
    assert dec is not None
    assert dec.action == "move_forward"


def test_decision_intent_picks_higher_stop_priority_when_multiple_stops_succeed():
    low = "stop_low"
    high = "stop_high"
    graph_nodes = [
        {
            "id": low,
            "kind": "stop",
            "data": {"stop_priority": 0, "required_outputs": [{"key": "output", "type": "dictionary"}]},
        },
        {
            "id": high,
            "kind": "stop",
            "data": {"stop_priority": 10, "required_outputs": [{"key": "output", "type": "dictionary"}]},
        },
    ]
    low_data = DecisionIntent(action="idle", reason="low").model_dump(mode="json")
    high_data = DecisionIntent(action="turn_left", reason="high").model_dump(mode="json")
    result = WorkflowRunResult(
        workflow_id=uuid.uuid4(),
        status="ok",
        node_results=[
            NodeRunResult(
                node_id=low,
                status="ok",
                output=DictionaryNodeOutput(node_id=low, data=low_data),
                step_number=5,
            ),
            NodeRunResult(
                node_id=high,
                status="ok",
                output=DictionaryNodeOutput(node_id=high, data=high_data),
                step_number=1,
            ),
        ],
    )
    dec, err = decision_intent_from_workflow_result(result, graph_nodes)
    assert err is None
    assert dec is not None
    assert dec.action == "turn_left"
    assert dec.reason == "high"


def test_decision_intent_tie_breaks_equal_priority_by_step_number():
    a = "stop_a"
    b = "stop_b"
    graph_nodes = [
        {"id": a, "kind": "stop", "data": {"stop_priority": 0}},
        {"id": b, "kind": "stop", "data": {"stop_priority": 0}},
    ]
    da = DecisionIntent(action="idle", reason="a").model_dump(mode="json")
    db = DecisionIntent(action="turn_right", reason="b").model_dump(mode="json")
    result = WorkflowRunResult(
        workflow_id=uuid.uuid4(),
        status="ok",
        node_results=[
            NodeRunResult(
                node_id=a,
                status="ok",
                output=DictionaryNodeOutput(node_id=a, data=da),
                step_number=2,
            ),
            NodeRunResult(
                node_id=b,
                status="ok",
                output=DictionaryNodeOutput(node_id=b, data=db),
                step_number=9,
            ),
        ],
    )
    dec, err = decision_intent_from_workflow_result(result, graph_nodes)
    assert err is None
    assert dec is not None
    assert dec.reason == "b"


def test_prompt_user_action_node_detection():
    graph_nodes = [
        {"id": "p1", "kind": "utility", "utility_type": "sandbox_prompt_user_action"},
        {"id": "other", "kind": "utility", "utility_type": "sandbox_idle"},
    ]
    assert prompt_user_action_node_id_from_graph(graph_nodes) == "p1"
    assert graph_requires_simulation_user_action(graph_nodes) is True
    assert prompt_user_action_node_id_from_graph([]) is None
