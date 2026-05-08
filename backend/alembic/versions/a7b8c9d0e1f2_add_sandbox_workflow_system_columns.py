"""Add workflow_definitions.is_system, builtin_slug; seed starter sandbox workflow.

Revision ID: a7b8c9d0e1f2
Revises: z9a0b1c2d3e4
Create Date: 2026-03-24
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.sandbox.starter_workflow_seed import (
    STARTER_SANDBOX_WORKFLOW_GRAPH,
    STARTER_SANDBOX_WORKFLOW_ID,
)

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "z9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_definitions",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("workflow_definitions", sa.Column("builtin_slug", sa.String(length=128), nullable=True))
    op.create_index(
        "ix_workflow_definitions_builtin_slug",
        "workflow_definitions",
        ["builtin_slug"],
        unique=True,
    )
    op.create_index("ix_workflow_definitions_is_system", "workflow_definitions", ["is_system"])

    conn = op.get_bind()
    graph_json = json.dumps(STARTER_SANDBOX_WORKFLOW_GRAPH)
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            """
            INSERT INTO workflow_definitions (
                id, user_id, name, description, palette_id, project_id,
                expose_as_custom_skill, is_system, builtin_slug, graph,
                created_at, updated_at
            ) VALUES (
                :id, NULL, :name, :desc, NULL, NULL,
                0, 1, :slug, :graph,
                :created_at, :updated_at
            )
            """
        ),
        {
            # Must match SQLModel/SQLAlchemy UUID→SQLite bind format (32 hex chars, no hyphens).
            "id": STARTER_SANDBOX_WORKFLOW_ID.hex,
            "name": "Starter Sandbox Behavior",
            "desc": "Built-in deterministic pet brain (sandbox_behavior primitive).",
            "slug": "starter_sandbox_behavior",
            "graph": graph_json,
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM workflow_definitions WHERE builtin_slug = :slug"),
        {"slug": "starter_sandbox_behavior"},
    )
    op.drop_index("ix_workflow_definitions_is_system", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_builtin_slug", table_name="workflow_definitions")
    op.drop_column("workflow_definitions", "builtin_slug")
    op.drop_column("workflow_definitions", "is_system")
