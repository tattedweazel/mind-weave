"""Extract ``DecisionIntent`` from a workflow run result."""

from __future__ import annotations

import json
from typing import Any

from app.domain.sandbox.stop_selection import select_best_stop_node_result
from app.domain.schemas.outputs import DictionaryNodeOutput, StopNodeOutput
from app.domain.schemas.sandbox import DecisionIntent
from app.domain.schemas.workflow_run import WorkflowRunResult


def prompt_user_action_node_id_from_graph(graph_nodes: list[dict[str, Any]]) -> str | None:
    """Return the id of the first ``sandbox_prompt_user_action`` utility node, if any."""
    for node in graph_nodes:
        if (
            node.get("kind") == "utility"
            and node.get("utility_type") == "sandbox_prompt_user_action"
        ):
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id.strip():
                return node_id.strip()
    return None


def graph_requires_simulation_user_action(graph_nodes: list[dict[str, Any]]) -> bool:
    return prompt_user_action_node_id_from_graph(graph_nodes) is not None


def workflow_graph_node_labels(graph: dict[str, Any] | None) -> dict[str, str]:
    """Map node id to display label for run log rendering."""
    nodes = (graph or {}).get("nodes") or []
    labels: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        label = node.get("label") or (node.get("data") or {}).get("label") or node_id
        labels[node_id] = str(label)
    return labels


def decision_intent_from_workflow_result(
    result: WorkflowRunResult,
    graph_nodes: list[dict[str, Any]],
) -> tuple[DecisionIntent | None, str | None]:
    """Return parsed ``DecisionIntent`` or (None, error_message)."""
    stop_ids = [n["id"] for n in graph_nodes if n.get("kind") == "stop"]
    if not stop_ids:
        return None, "workflow has no Stop node"

    stop_result = select_best_stop_node_result(result.node_results, graph_nodes, stop_ids)
    if stop_result is None or stop_result.output is None:
        return None, "Stop node did not produce output"

    out = stop_result.output
    data: dict[str, Any] | None = None
    if isinstance(out, DictionaryNodeOutput):
        data = dict(out.data)
    elif isinstance(out, StopNodeOutput):
        text = (out.text or "").strip()
        if not text:
            return None, "Stop output empty"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"Stop output not JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "Stop output must be a JSON object"
        data = parsed
    else:
        return None, f"unexpected Stop output type: {type(out).__name__}"

    if data == {}:
        return (
            None,
            "Stop output is not a valid DecisionIntent: empty object {}. "
            "Wire Move forward, Turn left, Turn right, or Idle output to Stop.",
        )
    try:
        return DecisionIntent.model_validate(data), None
    except Exception as exc:
        return None, f"invalid DecisionIntent: {exc}"
