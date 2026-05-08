"""Add tts_model_artifacts table

Revision ID: a0b1c2d3e4f5
Revises: q1r2s3t4u5v6
Create Date: 2026-04-21

Summary:
  - Registry rows for TTS bundles pulled via the local bridge (metadata only).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "tts_model_artifacts" in insp.get_table_names():
        return
    op.create_table(
        "tts_model_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("local_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tts_model_artifacts_display_name"), "tts_model_artifacts", ["display_name"], unique=False)
    op.create_index(op.f("ix_tts_model_artifacts_engine"), "tts_model_artifacts", ["engine"], unique=False)
    op.create_index(op.f("ix_tts_model_artifacts_status"), "tts_model_artifacts", ["status"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "tts_model_artifacts" not in insp.get_table_names():
        return
    op.drop_index(op.f("ix_tts_model_artifacts_status"), table_name="tts_model_artifacts")
    op.drop_index(op.f("ix_tts_model_artifacts_engine"), table_name="tts_model_artifacts")
    op.drop_index(op.f("ix_tts_model_artifacts_display_name"), table_name="tts_model_artifacts")
    op.drop_table("tts_model_artifacts")
