"""Sync starter sandbox graph to sandbox_starter_decision utility node.

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-03-24

Replaces the default seeded brain node from sandbox_behavior primitive to
sandbox_starter_decision utility (same deterministic policy). App startup
also re-syncs via ensure_starter_sandbox_workflow.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.sandbox.starter_workflow_seed import STARTER_BUILTIN_SLUG, STARTER_SANDBOX_WORKFLOW_GRAPH

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    graph_json = json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH)
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            """
            UPDATE workflow_definitions
            SET graph = :graph, updated_at = :updated_at
            WHERE builtin_slug = :slug
            """
        ),
        {"graph": graph_json, "updated_at": now, "slug": STARTER_BUILTIN_SLUG},
    )


def downgrade() -> None:
    conn = op.get_bind()
    legacy = copy.deepcopy(STARTER_SANDBOX_WORKFLOW_GRAPH)
    for i, n in enumerate(legacy["nodes"]):
        if isinstance(n, dict) and n.get("id") == "sandbox_brain":
            legacy["nodes"][i] = {
                "id": "sandbox_brain",
                "kind": "primitive",
                "primitive_type": "sandbox_behavior",
                "label": "Sandbox behavior",
                "data": {},
                "position": {"x": 220, "y": 0},
            }
            break
    graph_json = json.dumps(legacy)
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            """
            UPDATE workflow_definitions
            SET graph = :graph, updated_at = :updated_at
            WHERE builtin_slug = :slug
            """
        ),
        {"graph": graph_json, "updated_at": now, "slug": STARTER_BUILTIN_SLUG},
    )
