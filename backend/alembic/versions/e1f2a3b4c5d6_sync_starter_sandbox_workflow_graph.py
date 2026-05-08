"""Sync starter sandbox workflow graph to export-shaped canonical JSON.

Revision ID: e1f2a3b4c5d6
Revises: c0d1e2f3a4b5
Create Date: 2026-03-25

Removes legacy top-level schema_version from the built-in graph; nodes/edges
match app export format (implicit v1). App startup also re-syncs via
ensure_starter_sandbox_workflow.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.domain.sandbox.starter_workflow_seed import STARTER_BUILTIN_SLUG, STARTER_SANDBOX_WORKFLOW_GRAPH

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b5"
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
    legacy = {
        **STARTER_SANDBOX_WORKFLOW_GRAPH,
        "schema_version": 1,
    }
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
