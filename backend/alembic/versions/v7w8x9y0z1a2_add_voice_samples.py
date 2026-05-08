"""Add voice_samples for TTS voice clone references

Revision ID: v7w8x9y0z1a2
Revises: a0b1c2d3e4f5
Create Date: 2026-04-21

Summary:
  - voice_samples: per-user named reference WAV + ref_text for Qwen Base clone
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "voice_samples" in inspector.get_table_names():
        return
    op.create_table(
        "voice_samples",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("name_lower", sa.String(length=256), nullable=False),
        sa.Column("ref_text", sa.Text(), nullable=False),
        sa.Column("ref_audio", sa.LargeBinary(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("instruct", sa.Text(), nullable=False),
        sa.Column("design_model_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["design_model_id"], ["tts_model_artifacts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_lower", name="uq_voice_samples_user_name_lower"),
    )
    op.create_index(op.f("ix_voice_samples_user_id"), "voice_samples", ["user_id"], unique=False)
    op.create_index(op.f("ix_voice_samples_name"), "voice_samples", ["name"], unique=False)
    op.create_index(op.f("ix_voice_samples_name_lower"), "voice_samples", ["name_lower"], unique=False)
    op.create_index(op.f("ix_voice_samples_design_model_id"), "voice_samples", ["design_model_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_voice_samples_design_model_id"), table_name="voice_samples")
    op.drop_index(op.f("ix_voice_samples_name_lower"), table_name="voice_samples")
    op.drop_index(op.f("ix_voice_samples_name"), table_name="voice_samples")
    op.drop_index(op.f("ix_voice_samples_user_id"), table_name="voice_samples")
    op.drop_table("voice_samples")
