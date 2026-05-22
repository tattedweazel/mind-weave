"""Canonical built-in starter sandbox workflow graph + idempotent DB seed."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.persistence.tables import WorkflowDefinition

STARTER_BUILTIN_SLUG = "starter_sandbox_behavior"

STARTER_SANDBOX_WORKFLOW_GRAPH: dict[str, Any] = {
    "nodes": [
        {
            "id": "start",
            "kind": "start",
            "label": "Start",
            "data": {"required_inputs": [{"key": "sandbox_tick", "type": "dictionary", "value": None}]},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "nearby",
            "kind": "utility",
            "utility_type": "sandbox_get_nearby",
            "label": "Get nearby",
            "data": {},
            "position": {"x": 220, "y": 0},
        },
        {
            "id": "forward_cell",
            "kind": "utility",
            "utility_type": "list_item_by_index",
            "label": "Forward cell",
            "data": {
                "required_inputs": [
                    {"key": "index", "type": "int", "value": 0},
                    {"key": "list", "type": "list", "value": None},
                ]
            },
            "position": {"x": 460, "y": 0},
        },
        {
            "id": "forward_kind",
            "kind": "utility",
            "utility_type": "dictionary_value_by_key",
            "label": "Forward kind",
            "data": {
                "output_value_type": "string",
                "required_inputs": [
                    {"key": "dictionary", "type": "dictionary", "value": None},
                    {"key": "key", "type": "string", "value": "kind"},
                ]
            },
            "position": {"x": 700, "y": 0},
        },
        {
            "id": "empty_label",
            "kind": "primitive",
            "primitive_type": "string",
            "label": "empty",
            "data": {"text": "empty"},
            "position": {"x": 700, "y": 120},
        },
        {
            "id": "is_empty",
            "kind": "control",
            "control_type": "is",
            "label": "Is empty?",
            "data": {
                "required_inputs": [
                    {"key": "input_a", "type": "string", "value": None},
                    {"key": "input_b", "type": "string", "value": None},
                ]
            },
            "position": {"x": 940, "y": 0},
        },
        {
            "id": "turn_left",
            "kind": "utility",
            "utility_type": "sandbox_turn_left",
            "label": "Turn left",
            "data": {},
            "position": {"x": 1180, "y": -80},
        },
        {
            "id": "move_forward",
            "kind": "utility",
            "utility_type": "sandbox_move_forward",
            "label": "Move forward",
            "data": {},
            "position": {"x": 1180, "y": 80},
        },
        {
            "id": "stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
            "position": {"x": 1420, "y": 0},
        },
    ],
    "edges": [
        {"source": "start", "target": "nearby", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "start", "target": "nearby", "source_handle": "sandbox_tick", "target_handle": "input"},
        {"source": "nearby", "target": "forward_cell", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "nearby", "target": "forward_cell", "source_handle": "output", "target_handle": "list"},
        {"source": "forward_cell", "target": "forward_kind", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "forward_cell", "target": "forward_kind", "source_handle": "output", "target_handle": "dictionary"},
        {"source": "forward_kind", "target": "is_empty", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "forward_kind", "target": "is_empty", "source_handle": "output", "target_handle": "input_a"},
        {"source": "empty_label", "target": "is_empty", "source_handle": "output", "target_handle": "input_b"},
        {"source": "is_empty", "target": "move_forward", "source_handle": "true", "target_handle": "trigger"},
        {"source": "is_empty", "target": "turn_left", "source_handle": "false", "target_handle": "trigger"},
        {"source": "turn_left", "target": "stop", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "turn_left", "target": "stop", "source_handle": "output", "target_handle": "output"},
        {"source": "move_forward", "target": "stop", "source_handle": "signal_out", "target_handle": "trigger"},
        {"source": "move_forward", "target": "stop", "source_handle": "output", "target_handle": "output"},
    ],
}


def _normalize_value(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_value(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_normalize_value(x) for x in obj]
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def _normalize_edges(edges: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        if "source" not in e or "target" not in e:
            continue
        out.append(
            {
                "source": e["source"],
                "target": e["target"],
                "source_handle": e.get("source_handle"),
                "target_handle": e.get("target_handle"),
            }
        )
    out.sort(
        key=lambda e: (
            e["source"],
            e["target"],
            e["source_handle"] or "",
            e["target_handle"] or "",
        )
    )
    return out


def _normalize_graph_for_compare(graph: dict | None) -> dict[str, Any]:
    if not isinstance(graph, dict):
        return {"edges": [], "nodes": []}
    g = {k: v for k, v in graph.items() if k != "schema_version"}
    nodes = g.get("nodes")
    edges = g.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return {
        "edges": _normalize_edges(edges),
        "nodes": _normalize_value(nodes),
    }


def graphs_equivalent(a: dict | None, b: dict | None) -> bool:
    sa = json.dumps(_normalize_graph_for_compare(a), sort_keys=True, separators=(",", ":"))
    sb = json.dumps(_normalize_graph_for_compare(b), sort_keys=True, separators=(",", ":"))
    return sa == sb


STARTER_SANDBOX_NAME = "Starter Sandbox Navigation"
STARTER_SANDBOX_DESCRIPTION = (
    "Built-in left-hand wall follower: Get nearby → if forward cell is empty, Move forward, "
    "else Turn left (walls, canvas edge, creatures, food)."
)


def ensure_starter_sandbox_workflow(session: Session) -> None:
    """Insert the system starter workflow if missing (dev DBs, tests without Alembic seed, etc.)."""
    canonical = STARTER_SANDBOX_WORKFLOW_GRAPH
    now = datetime.now(timezone.utc)
    existing = session.exec(
        select(WorkflowDefinition).where(WorkflowDefinition.builtin_slug == STARTER_BUILTIN_SLUG)
    ).first()
    if existing is not None:
        if str(existing.id) == str(STARTER_SANDBOX_WORKFLOW_ID):
            stored = existing.graph if isinstance(existing.graph, dict) else {}
            needs_cleanup = isinstance(stored, dict) and "schema_version" in stored
            if not needs_cleanup and graphs_equivalent(stored, canonical):
                return
            existing.graph = copy.deepcopy(canonical)
            existing.name = STARTER_SANDBOX_NAME
            existing.description = STARTER_SANDBOX_DESCRIPTION
            existing.updated_at = now
            session.add(existing)
            session.commit()
            return
        session.delete(existing)
        session.commit()
    session.add(
        WorkflowDefinition(
            id=STARTER_SANDBOX_WORKFLOW_ID,
            user_id=None,
            name=STARTER_SANDBOX_NAME,
            description=STARTER_SANDBOX_DESCRIPTION,
            palette_id=None,
            project_id=None,
            expose_as_custom_skill=False,
            is_system=True,
            builtin_slug=STARTER_BUILTIN_SLUG,
            graph=copy.deepcopy(STARTER_SANDBOX_WORKFLOW_GRAPH),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
