"""Starter sandbox: explicit signal_out/trigger + data edges (Start/Stop wiring).

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-03-25

Replaces two legacy edges (null handles) with four edges so the editor shows
control flow vs data wiring correctly. Downgrade restores the prior two-edge graph.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.sandbox.starter_workflow_seed import STARTER_BUILTIN_SLUG, STARTER_SANDBOX_WORKFLOW_GRAPH

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_TWO_EDGE_GRAPH = {
    "nodes": STARTER_SANDBOX_WORKFLOW_GRAPH["nodes"],
    "edges": [
        {
            "source": "sandbox_start",
            "target": "sandbox_brain",
            "source_handle": "sandbox_tick",
            "target_handle": None,
        },
        {
            "source": "sandbox_brain",
            "target": "sandbox_stop",
            "source_handle": None,
            "target_handle": None,
        },
    ],
}


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
    graph_json = json.dumps(_LEGACY_TWO_EDGE_GRAPH)
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
