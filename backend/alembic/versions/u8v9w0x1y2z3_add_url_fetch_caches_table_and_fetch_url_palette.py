"""Add url_fetch_caches and fetch_url palette key.

Revision ID: u8v9w0x1y2z3
Revises: v7w8x9y0z1a2
Create Date: 2026-04-23

Summary:
  - Create url_fetch_caches for workflow fetch_url skill (per-user response cache)
  - Add fetch_url to palettes.colors JSON
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, Sequence[str], None] = "v7w8x9y0z1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLOR = {"fetch_url": "#0ea5e9"}


def upgrade() -> None:
    op.create_table(
        "url_fetch_caches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cache_key", name="uq_url_fetch_caches_user_key"),
    )
    op.create_index(op.f("ix_url_fetch_caches_user_id"), "url_fetch_caches", ["user_id"], unique=False)
    op.create_index(op.f("ix_url_fetch_caches_cache_key"), "url_fetch_caches", ["cache_key"], unique=False)

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

    op.drop_index(op.f("ix_url_fetch_caches_cache_key"), table_name="url_fetch_caches")
    op.drop_index(op.f("ix_url_fetch_caches_user_id"), table_name="url_fetch_caches")
    op.drop_table("url_fetch_caches")
