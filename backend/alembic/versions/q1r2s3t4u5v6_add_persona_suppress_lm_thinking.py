"""Add suppress_lm_thinking to personas

Revision ID: q1r2s3t4u5v6
Revises: d8e9f0a1b2c3
Create Date: 2026-04-20

Summary:
  - Boolean: when true, chat/completions requests include reasoning_effort none (LM Studio 0.4.8+)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("personas")}
    if "suppress_lm_thinking" in cols:
        return
    op.add_column(
        "personas",
        sa.Column(
            "suppress_lm_thinking",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("personas")}
    if "suppress_lm_thinking" not in cols:
        return
    op.drop_column("personas", "suppress_lm_thinking")
