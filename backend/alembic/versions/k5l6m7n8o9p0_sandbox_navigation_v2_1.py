"""Sandbox navigation v2.1: starter workflow + creature facing migration.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-05-22
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.sandbox.starter_workflow_seed import STARTER_BUILTIN_SLUG, STARTER_SANDBOX_WORKFLOW_GRAPH

revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, Sequence[str], None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PET_STAT_KEYS = ("hunger", "energy", "mood", "intent")


def _migrate_creature(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    for k in _PET_STAT_KEYS:
        out.pop(k, None)
    if "facing" not in out or not out.get("facing"):
        out["facing"] = "N"
    return out


def _migrate_sandbox_blob(blob: dict[str, Any]) -> dict[str, Any]:
    sandbox = blob.get("sandbox")
    if not isinstance(sandbox, dict):
        return blob
    creatures = sandbox.get("creatures")
    if isinstance(creatures, list):
        sandbox["creatures"] = [
            _migrate_creature(c) if isinstance(c, dict) else c for c in creatures
        ]
    blob["schema_version"] = "2.1.0"
    blob["sandbox"] = sandbox
    return blob


def _migrate_board_body(body: dict[str, Any]) -> dict[str, Any]:
    creatures = body.get("creatures")
    if isinstance(creatures, list):
        body["creatures"] = [
            _migrate_creature(c) if isinstance(c, dict) else c for c in creatures
        ]
    body["schema_version"] = "2.1.0"
    return body


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    conn.execute(
        sa.text(
            """
            UPDATE workflow_definitions
            SET graph = :graph, name = :name, description = :description, updated_at = :updated_at
            WHERE builtin_slug = :slug
            """
        ),
        {
            "graph": json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH),
            "name": "Starter Sandbox Navigation",
            "description": "Built-in left-hand wall follower using Get nearby and Turn left / Move forward.",
            "updated_at": now,
            "slug": STARTER_BUILTIN_SLUG,
        },
    )

    doc_rows = conn.execute(sa.text("SELECT id, body FROM documents WHERE body LIKE '%\"sandbox\"%'"))
    for row in doc_rows:
        try:
            body = json.loads(row.body or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(body, dict):
            continue
        migrated = _migrate_sandbox_blob(body)
        conn.execute(
            sa.text("UPDATE documents SET body = :body WHERE id = :id"),
            {"body": json.dumps(migrated), "id": row.id},
        )

    board_rows = conn.execute(sa.text("SELECT id, body FROM sandbox_boards"))
    for row in board_rows:
        try:
            body = json.loads(row.body or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(body, dict):
            continue
        migrated = _migrate_board_body(body)
        conn.execute(
            sa.text("UPDATE sandbox_boards SET body = :body WHERE id = :id"),
            {"body": json.dumps(migrated), "id": row.id},
        )


def downgrade() -> None:
    pass
