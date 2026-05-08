"""Migrate Simple LLM Call graph nodes from utility to skill kind.

Revision ID: s0t1u2v3w4x5
Revises: r7s8t9u0v1w2
Create Date: 2026-03-19

Summary:
  - For each workflow_definitions.graph node with kind=utility and utility_type=simple_llm_call:
    set kind=skill, skill_type=simple_llm_call, remove utility_type.
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "s0t1u2v3w4x5"
down_revision: Union[str, Sequence[str], None] = "r7s8t9u0v1w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT id, graph FROM workflow_definitions"))
    rows = result.fetchall()

    for (wf_id, graph_json) in rows:
        if not graph_json:
            continue
        graph = json.loads(graph_json) if isinstance(graph_json, str) else graph_json
        nodes = graph.get("nodes", [])
        changed = False
        new_nodes = []
        for n in nodes:
            if n.get("kind") == "utility" and n.get("utility_type") == "simple_llm_call":
                nd = dict(n)
                nd["kind"] = "skill"
                nd["skill_type"] = "simple_llm_call"
                nd.pop("utility_type", None)
                new_nodes.append(nd)
                changed = True
            else:
                new_nodes.append(n)
        if changed:
            graph["nodes"] = new_nodes
            conn.execute(
                text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
                {"graph": json.dumps(graph), "id": str(wf_id)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT id, graph FROM workflow_definitions"))
    rows = result.fetchall()

    for (wf_id, graph_json) in rows:
        if not graph_json:
            continue
        graph = json.loads(graph_json) if isinstance(graph_json, str) else graph_json
        nodes = graph.get("nodes", [])
        changed = False
        new_nodes = []
        for n in nodes:
            if n.get("kind") == "skill" and n.get("skill_type") == "simple_llm_call":
                nd = dict(n)
                nd["kind"] = "utility"
                nd["utility_type"] = "simple_llm_call"
                nd.pop("skill_type", None)
                new_nodes.append(nd)
                changed = True
            else:
                new_nodes.append(n)
        if changed:
            graph["nodes"] = new_nodes
            conn.execute(
                text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
                {"graph": json.dumps(graph), "id": str(wf_id)},
            )
