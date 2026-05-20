"""Drop workspace default_google_workflow_connection_id; dedupe google_workflow_connections to one per user.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-20

Summary:
  - Remove workspaces.default_google_workflow_connection_id (user-level connection is SSOT)
  - Delete legacy duplicate google_workflow_connections rows per user (keep most recently updated)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Keep one google_workflow_connections row per user (most recently updated).
    conn.execute(
        sa.text(
            """
            DELETE FROM google_workflow_connections
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY user_id ORDER BY updated_at DESC, created_at DESC
                           ) AS rn
                    FROM google_workflow_connections
                ) ranked
                WHERE rn = 1
            )
            """
        )
    )

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint("fk_workspaces_default_google_workflow_connection", type_="foreignkey")
        batch_op.drop_column("default_google_workflow_connection_id")


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("default_google_workflow_connection_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workspaces_default_google_workflow_connection",
            "google_workflow_connections",
            ["default_google_workflow_connection_id"],
            ["id"],
        )
