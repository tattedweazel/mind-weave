"""Add started_by_user_id to workflow_runs

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("workflow_runs")]
    if "started_by_user_id" in cols:
        return

    op.add_column(
        "workflow_runs",
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_workflow_runs_started_by_user_id",
        "workflow_runs",
        ["started_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_workflow_runs_started_by_user_id_users",
        "workflow_runs",
        "users",
        ["started_by_user_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE workflow_runs
        SET started_by_user_id = (
            SELECT workflow_definitions.user_id
            FROM workflow_definitions
            WHERE workflow_definitions.id = workflow_runs.workflow_id
        )
        WHERE EXISTS (
            SELECT 1 FROM workflow_definitions wd
            WHERE wd.id = workflow_runs.workflow_id AND wd.user_id IS NOT NULL
        )
        """
    )

    # Remove runs that could not be attributed (orphan / null owner); logs cascade by explicit delete in app
    op.execute(
        """
        DELETE FROM node_run_logs WHERE run_id IN (
            SELECT id FROM workflow_runs WHERE started_by_user_id IS NULL
        )
        """
    )
    op.execute("DELETE FROM workflow_runs WHERE started_by_user_id IS NULL")

    with op.batch_alter_table("workflow_runs") as batch:
        batch.alter_column(
            "started_by_user_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("workflow_runs")]
    if "started_by_user_id" not in cols:
        return

    op.drop_constraint(
        "fk_workflow_runs_started_by_user_id_users",
        "workflow_runs",
        type_="foreignkey",
    )
    op.drop_index("ix_workflow_runs_started_by_user_id", table_name="workflow_runs")
    op.drop_column("workflow_runs", "started_by_user_id")
