"""Add process_results and process_trace columns for process pipeline

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-04-13

Summary:
  - workspace_turns: add process_results (JSON, nullable)
  - workspace_replays: add process_trace (JSON, nullable)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o3p4q5r6s7t8"
down_revision: Union[str, Sequence[str], None] = "n2o3p4q5r6s7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspace_turns") as batch_op:
        batch_op.add_column(sa.Column("process_results", sa.JSON(), nullable=True))

    with op.batch_alter_table("workspace_replays") as batch_op:
        batch_op.add_column(sa.Column("process_trace", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workspace_replays") as batch_op:
        batch_op.drop_column("process_trace")

    with op.batch_alter_table("workspace_turns") as batch_op:
        batch_op.drop_column("process_results")
