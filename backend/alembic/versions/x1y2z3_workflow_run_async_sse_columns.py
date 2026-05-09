"""Workflow run SSE/async execution columns and status normalization.

Adds started_at / completed_at / last_event_seq and migrates terminal statuses:
ok -> completed, partial -> completed, error -> failed.
queued is introduced for POST /runs enqueue semantics.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "x1y2z3w4sse1"
down_revision: Union[str, Sequence[str], None] = "s2t3u4v5w6x7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0")
        )

    conn = op.get_bind()
    # Normalize legacy status values toward async execution vocabulary.
    conn.execute(
        sa.text(
            """
            UPDATE workflow_runs
            SET status = CASE status
                WHEN 'ok' THEN 'completed'
                WHEN 'partial' THEN 'completed'
                WHEN 'error' THEN 'failed'
                ELSE status
            END
            WHERE status IN ('ok', 'partial', 'error')
            """
        )
    )

    with op.batch_alter_table("workflow_runs") as batch:
        batch.alter_column("last_event_seq", server_default=None)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE workflow_runs
            SET status = CASE status
                WHEN 'completed' THEN 'ok'
                WHEN 'failed' THEN 'error'
                ELSE status
            END
            WHERE status IN ('completed', 'failed')
            """
        )
    )
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("last_event_seq")
        batch.drop_column("completed_at")
        batch.drop_column("started_at")
