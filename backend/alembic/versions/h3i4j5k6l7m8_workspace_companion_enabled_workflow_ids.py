"""Replace capability key JSON with enabled_workflow_ids on workspaces and companions

Revision ID: h3i4j5k6l7m8
Revises: a1b2c3d4e5f8
Create Date: 2026-04-08

Summary:
  - workspaces: available_capability_keys -> enabled_workflow_ids (UUID strings JSON)
  - companions: enabled_capability_keys -> enabled_workflow_ids
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(
            sa.Column("enabled_workflow_ids", sa.JSON(), nullable=False, server_default="[]"),
        )
        batch_op.drop_column("available_capability_keys")

    with op.batch_alter_table("companions") as batch_op:
        batch_op.add_column(
            sa.Column("enabled_workflow_ids", sa.JSON(), nullable=False, server_default="[]"),
        )
        batch_op.drop_column("enabled_capability_keys")


def downgrade() -> None:
    with op.batch_alter_table("companions") as batch_op:
        batch_op.add_column(
            sa.Column("enabled_capability_keys", sa.JSON(), nullable=False, server_default="[]"),
        )
        batch_op.drop_column("enabled_workflow_ids")

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(
            sa.Column("available_capability_keys", sa.JSON(), nullable=False, server_default="[]"),
        )
        batch_op.drop_column("enabled_workflow_ids")
