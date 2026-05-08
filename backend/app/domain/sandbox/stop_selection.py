"""Deterministic selection among multiple successful Stop nodes (sandbox + tooling)."""

from __future__ import annotations

from typing import Any

from app.domain.schemas.workflow_run import NodeRunResult


def stop_priority_from_graph_node(graph_nodes: list[dict[str, Any]], node_id: str) -> int:
    """Return ``data.stop_priority`` for a Stop node id, or 0."""
    for n in graph_nodes:
        if n.get("id") != node_id or n.get("kind") != "stop":
            continue
        data = n.get("data")
        if not isinstance(data, dict):
            return 0
        p = data.get("stop_priority")
        if isinstance(p, bool):
            return int(p)
        if isinstance(p, int):
            return p
        if isinstance(p, float) and p.is_integer():
            return int(p)
        if isinstance(p, str) and p.strip():
            try:
                return int(p.strip(), 10)
            except ValueError:
                return 0
        return 0
    return 0


def select_best_stop_node_result(
    node_results: list[NodeRunResult],
    graph_nodes: list[dict[str, Any]],
    stop_ids: list[str],
) -> NodeRunResult | None:
    """Pick one successful Stop result: highest ``stop_priority``, then highest ``step_number``, then ``node_id``."""
    sid_set = frozenset(stop_ids)
    candidates: list[tuple[NodeRunResult, int, int, str]] = []
    for nr in node_results:
        if nr.node_id not in sid_set or nr.status != "ok" or nr.output is None:
            continue
        pri = stop_priority_from_graph_node(graph_nodes, nr.node_id)
        step = nr.step_number if nr.step_number is not None else -1
        candidates.append((nr, pri, step, nr.node_id))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[1], -t[2], t[3]))
    return candidates[0][0]
