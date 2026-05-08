"""Extract ``DecisionIntent`` from a workflow run result."""

from __future__ import annotations

import json
from typing import Any

from app.domain.sandbox.stop_selection import select_best_stop_node_result
from app.domain.schemas.outputs import DictionaryNodeOutput, StopNodeOutput
from app.domain.schemas.sandbox import DecisionIntent
from app.domain.schemas.workflow_run import WorkflowRunResult


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
            "Wire sandbox_decision_intent, sandbox_starter_decision, or sandbox_behavior output to Stop, "
            "not an empty dictionary primitive or an empty string.",
        )
    try:
        return DecisionIntent.model_validate(data), None
    except Exception as exc:
        return None, f"invalid DecisionIntent: {exc}"
