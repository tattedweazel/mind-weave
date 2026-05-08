"""Add index on workflow_runs.created_at for startup purge query

Revision ID: m1n2o3p4q5r6
Revises: k9l0m1n2o3p4
Create Date: 2026-04-11

Summary:
  - Index on workflow_runs.created_at speeds up _purge_old_workflow_runs()
    which runs on every startup with a WHERE created_at < cutoff filter.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "n2o3p4q5r6s7"
down_revision: Union[str, Sequence[str], None] = "k9l0m1n2o3p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_created_at", table_name="workflow_runs")
