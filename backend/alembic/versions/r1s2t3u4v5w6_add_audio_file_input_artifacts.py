"""Add audio file artifacts and Audio File Input palette key.

Revision ID: r1s2t3u4v5w6
Revises: a3b4c5d6e7f8
Create Date: 2026-05-06

Summary:
  - audio_file_artifacts: per-user audio bytes for workflow Audio File Input
  - Add audio_file_input to palettes.colors JSON
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "r1s2t3u4v5w6"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {"audio_file_input": "#22c55e"}


def upgrade() -> None:
    op.create_table(
        "audio_file_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("audio_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audio_file_artifacts_user_id"), "audio_file_artifacts", ["user_id"], unique=False)
    op.create_index(op.f("ix_audio_file_artifacts_filename"), "audio_file_artifacts", ["filename"], unique=False)

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, colors FROM palettes")).fetchall()
    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key, value in NEW_COLORS.items():
            if key not in colors:
                colors[key] = value
                updated = True
        if updated:
            conn.execute(
                text("UPDATE palettes SET colors = :colors WHERE id = :id"),
                {"colors": json.dumps(colors), "id": str(palette_id)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, colors FROM palettes")).fetchall()
    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key in NEW_COLORS:
            if key in colors:
                del colors[key]
                updated = True
        if updated:
            conn.execute(
                text("UPDATE palettes SET colors = :colors WHERE id = :id"),
                {"colors": json.dumps(colors), "id": str(palette_id)},
            )

    op.drop_index(op.f("ix_audio_file_artifacts_filename"), table_name="audio_file_artifacts")
    op.drop_index(op.f("ix_audio_file_artifacts_user_id"), table_name="audio_file_artifacts")
    op.drop_table("audio_file_artifacts")
