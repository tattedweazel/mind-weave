"""Add step_number to node_run_logs

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "v3w4x5y6z7a8"
down_revision: Union[str, Sequence[str], None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "node_run_logs",
        sa.Column("step_number", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_node_run_logs_step_number",
        "node_run_logs",
        ["step_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_node_run_logs_step_number", table_name="node_run_logs")
    op.drop_column("node_run_logs", "step_number")
