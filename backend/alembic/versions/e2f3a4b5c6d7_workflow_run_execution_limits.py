"""Add workflow_runs.execution_limits_effective JSON snapshot."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "x1y2z3w4sse1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(sa.Column("execution_limits_effective", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("execution_limits_effective")
