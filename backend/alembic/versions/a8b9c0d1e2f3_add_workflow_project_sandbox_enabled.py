"""Add sandbox_enabled to workflow_projects

Revision ID: a8b9c0d1e2f3
Revises: k5l6m7n8o9p0
Create Date: 2026-05-24

Summary:
  - workflow_projects.sandbox_enabled: opt-in flag for Sandbox workflow pickers (default false)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("workflow_projects")}
    if "sandbox_enabled" not in cols:
        with op.batch_alter_table("workflow_projects") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "sandbox_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        op.create_index(
            op.f("ix_workflow_projects_sandbox_enabled"),
            "workflow_projects",
            ["sandbox_enabled"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("workflow_projects")}
    if "sandbox_enabled" in cols:
        op.drop_index(op.f("ix_workflow_projects_sandbox_enabled"), table_name="workflow_projects")
        with op.batch_alter_table("workflow_projects") as batch_op:
            batch_op.drop_column("sandbox_enabled")
