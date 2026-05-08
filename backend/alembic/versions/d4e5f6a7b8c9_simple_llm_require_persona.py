"""Simple LLM Call: require Persona, rename system_prompt handle to additional_context

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-18

Summary:
  - Update edges: target_handle "system_prompt" -> "additional_context" for simple_llm_call targets
  - Strip model and creativity from simple_llm_call node data (now from Persona)
  - Simplify required_inputs: remove system_prompt entry, keep user_prompt
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
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
        edges = graph.get("edges", [])

        simple_llm_ids = {
            n["id"] for n in nodes
            if n.get("kind") == "utility" and n.get("utility_type") == "simple_llm_call"
        }

        changed = False

        # Update edges: system_prompt -> additional_context for simple_llm_call targets
        new_edges = []
        for e in edges:
            ed = dict(e)
            if ed.get("target") in simple_llm_ids and ed.get("target_handle") == "system_prompt":
                ed["target_handle"] = "additional_context"
                changed = True
            new_edges.append(ed)

        # Strip model, creativity from simple_llm_call nodes; simplify required_inputs
        new_nodes = []
        for n in nodes:
            if n.get("kind") == "utility" and n.get("utility_type") == "simple_llm_call":
                data = dict(n.get("data", {}))
                data.pop("model", None)
                data.pop("creativity", None)
                req = data.get("required_inputs") or []
                new_req = [r for r in req if isinstance(r, dict) and r.get("key") == "user_prompt"]
                if not new_req:
                    new_req = [{"key": "user_prompt", "type": "string", "value": None}]
                data["required_inputs"] = new_req
                new_nodes.append({**n, "data": data})
                changed = True
            else:
                new_nodes.append(n)

        if changed:
            graph["nodes"] = new_nodes
            graph["edges"] = new_edges
            conn.execute(
                text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
                {"graph": json.dumps(graph), "id": str(wf_id)},
            )


def downgrade() -> None:
    # Cannot restore model/creativity; no-op.
    pass
