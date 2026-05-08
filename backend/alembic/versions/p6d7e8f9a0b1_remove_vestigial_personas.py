"""Remove vestigial system personas from pre-v2.0 architecture

Revision ID: p6d7e8f9a0b1
Revises: o5c6d7e8f9a0
Create Date: 2026-03-19

Summary:
  - Remove legacy personas: system_memory_extractor, conversation_default, system_persona_generator
  - These were removed from code in v2.0 but remained in the database
  - Reassign any workflow node persona_id references to the default persona before deletion
  - Ensure default persona exists (insert if missing) so workflows have a valid target
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "p6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "o5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VESTIGIAL_NAMES = ("system_memory_extractor", "conversation_default", "system_persona_generator")

DEFAULT_PERSONA = {
    "name": "default",
    "description": "A helpful general-purpose assistant.",
    "system_prompt": "You are a helpful, concise, and professional assistant.",
    "is_default": True,
    "type": "system",
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure default persona exists
    default_row = conn.execute(
        text("SELECT id FROM personas WHERE name = 'default' AND user_id IS NULL")
    ).fetchone()

    if default_row:
        default_id = str(default_row[0])
    else:
        default_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            text("""
                INSERT INTO personas (id, user_id, name, type, description, system_prompt,
                    default_model, is_default, creativity, created_at, updated_at)
                VALUES (:id, NULL, :name, :type, :description, :system_prompt,
                    NULL, :is_default, 0.2, :now, :now)
            """),
            {
                "id": default_id,
                "name": DEFAULT_PERSONA["name"],
                "type": DEFAULT_PERSONA["type"],
                "description": DEFAULT_PERSONA["description"],
                "system_prompt": DEFAULT_PERSONA["system_prompt"],
                "is_default": 1 if DEFAULT_PERSONA["is_default"] else 0,
                "now": now,
            },
        )

    # 2. For each vestigial persona, reassign workflow refs and delete
    for name in VESTIGIAL_NAMES:
        row = conn.execute(
            text("SELECT id FROM personas WHERE name = :name AND user_id IS NULL"),
            {"name": name},
        ).fetchone()
        if not row:
            continue

        vestigial_id = str(row[0])

        # Update workflow_definitions: replace persona_id in graph nodes
        result = conn.execute(text("SELECT id, graph FROM workflow_definitions"))
        for (wf_id, graph_json) in result.fetchall():
            if not graph_json:
                continue
            graph = json.loads(graph_json) if isinstance(graph_json, str) else graph_json
            nodes = graph.get("nodes", [])
            modified = False
            for node in nodes:
                data = node.get("data") or {}
                if isinstance(data, dict) and data.get("persona_id") == vestigial_id:
                    data["persona_id"] = default_id
                    node["data"] = data
                    modified = True
            if modified:
                graph["nodes"] = nodes
                conn.execute(
                    text("UPDATE workflow_definitions SET graph = :graph WHERE id = :id"),
                    {"graph": json.dumps(graph), "id": str(wf_id)},
                )

        conn.execute(text("DELETE FROM personas WHERE id = :id"), {"id": vestigial_id})


def downgrade() -> None:
    # Cannot restore deleted vestigial personas; no-op.
    pass
