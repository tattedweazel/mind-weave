"""Migrate Step nodes to SimpleLLMCall utility and drop steps table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-18

Summary:
  - Convert workflow graph nodes with kind=step to kind=utility, utility_type=simple_llm_call
  - Update edges: set target_handle=user_prompt for edges into converted nodes
  - Drop steps table
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Build step_id -> (system_prompt, model, creativity) from steps and personas
    personas_by_id = {}
    try:
        for r in conn.execute(
            text("SELECT id, system_prompt, default_model, creativity FROM personas")
        ).fetchall():
            personas_by_id[str(r[0])] = r
    except Exception:
        pass

    step_data = {}
    try:
        for row in conn.execute(
            text("SELECT id, persona_id, instruction FROM steps")
        ).fetchall():
            step_id, persona_id, instruction = str(row[0]), str(row[1]), row[2]
            persona = personas_by_id.get(persona_id)
            if persona:
                _, system_prompt, default_model, creativity = persona
                combined = f"{system_prompt}\n\n{instruction}" if system_prompt else instruction
                step_data[step_id] = {
                    "system_prompt": combined,
                    "model": default_model,
                    "creativity": creativity or 0.2,
                }
            else:
                step_data[step_id] = {
                    "system_prompt": "You are a helpful assistant.",
                    "model": None,
                    "creativity": 0.2,
                }
    except Exception:
        step_data = {}

    # Fetch all workflow_definitions and convert
    result = conn.execute(text("SELECT id, graph FROM workflow_definitions"))
    rows = result.fetchall()

    for (wf_id, graph_json) in rows:
        if not graph_json:
            continue
        graph = json.loads(graph_json) if isinstance(graph_json, str) else graph_json
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        step_node_ids = set()
        new_nodes = []
        for n in nodes:
            if n.get("kind") == "step":
                step_id = n.get("step_id")
                step_id_str = str(step_id) if step_id is not None else ""
                if step_id_str in step_data:
                    sd = step_data[step_id_str]
                else:
                    sd = {
                        "system_prompt": "You are a helpful assistant.",
                        "model": None,
                        "creativity": 0.2,
                    }
                new_nodes.append({
                    "id": n["id"],
                    "kind": "utility",
                    "utility_type": "simple_llm_call",
                    "label": n.get("label", "LLM Call"),
                    "data": {
                        "required_inputs": [
                            {"key": "system_prompt", "type": "string", "value": sd["system_prompt"]},
                            {"key": "user_prompt", "type": "string", "value": None},
                        ],
                        "model": sd["model"],
                        "creativity": sd["creativity"],
                    },
                    "position": n.get("position", {"x": 0, "y": 0}),
                })
                step_node_ids.add(n["id"])
            else:
                new_nodes.append(n)

        new_edges = []
        for e in edges:
            edge = dict(e) if isinstance(e, dict) else {"source": e.source, "target": e.target}
            if edge.get("target") in step_node_ids and "target_handle" not in edge:
                edge["target_handle"] = "user_prompt"
            new_edges.append(edge)

        graph["nodes"] = new_nodes
        graph["edges"] = new_edges
        conn.execute(
            text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
            {"graph": json.dumps(graph), "id": str(wf_id)},
        )

    # Drop steps table
    op.drop_table("steps")


def downgrade() -> None:
    op.create_table(
        "steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=False, index=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Note: workflow graph conversion cannot be reversed; Step nodes are lost.
