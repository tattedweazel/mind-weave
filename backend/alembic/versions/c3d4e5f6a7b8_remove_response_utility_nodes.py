"""Remove response utility nodes from workflow graphs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-18

Summary:
  - Remove nodes with kind=utility and utility_type=response from workflow graph.nodes
  - Remove edges whose source or target is a removed node
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
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

        response_node_ids = {
            n["id"] for n in nodes
            if n.get("kind") == "utility" and n.get("utility_type") == "response"
        }
        if not response_node_ids:
            continue

        new_nodes = [n for n in nodes if n["id"] not in response_node_ids]
        new_edges = [
            e for e in edges
            if e.get("source") not in response_node_ids and e.get("target") not in response_node_ids
        ]

        graph["nodes"] = new_nodes
        graph["edges"] = new_edges
        conn.execute(
            text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
            {"graph": json.dumps(graph), "id": str(wf_id)},
        )


def downgrade() -> None:
    # Response utility nodes cannot be restored; no-op.
    pass
