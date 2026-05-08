"""Add url_snapshot_artifacts, url_snapshot_caches, and capture_url_snapshot palette key.

Revision ID: a2b3c4d5e6f7
Revises: v9w0x1y2z3a4
Create Date: 2026-04-23

Summary:
  - Create url_snapshot_artifacts and url_snapshot_caches for capture_url_snapshot skill
  - Add capture_url_snapshot to palettes.colors JSON
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "v9w0x1y2z3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLOR = {"capture_url_snapshot": "#7c3aed"}


def upgrade() -> None:
    op.create_table(
        "url_snapshot_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_url_snapshot_artifacts_user_id"), "url_snapshot_artifacts", ["user_id"], unique=False)

    op.create_table(
        "url_snapshot_caches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["url_snapshot_artifacts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cache_key", name="uq_url_snapshot_caches_user_key"),
    )
    op.create_index(op.f("ix_url_snapshot_caches_user_id"), "url_snapshot_caches", ["user_id"], unique=False)
    op.create_index(op.f("ix_url_snapshot_caches_cache_key"), "url_snapshot_caches", ["cache_key"], unique=False)
    op.create_index(
        op.f("ix_url_snapshot_caches_artifact_id"), "url_snapshot_caches", ["artifact_id"], unique=False
    )

    conn = op.get_bind()
    result = conn.execute(text("SELECT id, colors FROM palettes"))
    rows = result.fetchall()

    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key, value in NEW_COLOR.items():
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
    result = conn.execute(text("SELECT id, colors FROM palettes"))
    rows = result.fetchall()

    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key in NEW_COLOR:
            if key in colors:
                del colors[key]
                updated = True
        if updated:
            conn.execute(
                text("UPDATE palettes SET colors = :colors WHERE id = :id"),
                {"colors": json.dumps(colors), "id": str(palette_id)},
            )

    op.drop_index(op.f("ix_url_snapshot_caches_artifact_id"), table_name="url_snapshot_caches")
    op.drop_index(op.f("ix_url_snapshot_caches_cache_key"), table_name="url_snapshot_caches")
    op.drop_index(op.f("ix_url_snapshot_caches_user_id"), table_name="url_snapshot_caches")
    op.drop_table("url_snapshot_caches")
    op.drop_index(op.f("ix_url_snapshot_artifacts_user_id"), table_name="url_snapshot_artifacts")
    op.drop_table("url_snapshot_artifacts")
