"""Workspace interpretation_model and default_google_workflow_connection_id

Revision ID: k9l0m1n2o3p4
Revises: h3i4j5k6l7m8
Create Date: 2026-04-08

Summary:
  - workspaces.interpretation_model: optional LM Studio id for interpret phase
  - workspaces.default_google_workflow_connection_id: optional FK for Gmail/Calendar skills
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k9l0m1n2o3p4"
down_revision: Union[str, Sequence[str], None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("interpretation_model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("default_google_workflow_connection_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workspaces_default_google_workflow_connection",
            "google_workflow_connections",
            ["default_google_workflow_connection_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint("fk_workspaces_default_google_workflow_connection", type_="foreignkey")
        batch_op.drop_column("default_google_workflow_connection_id")
        batch_op.drop_column("interpretation_model")
