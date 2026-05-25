"""Replace item_definitions.default_energy with custom_metadata JSON

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b6
Create Date: 2026-05-25

Summary:
  - Add custom_metadata JSON column to item_definitions
  - Migrate default_energy values into custom_metadata.energy
  - Drop default_energy column
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUILTIN_FOOD_ID = "a1000000-0000-4000-8000-000000000001"


def _table_exists(conn, name: str) -> bool:
    return name in inspect(conn).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "item_definitions"):
        return

    cols = {c["name"] for c in inspect(conn).get_columns("item_definitions")}
    if "custom_metadata" not in cols:
        op.add_column(
            "item_definitions",
            sa.Column(
                "custom_metadata",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    if "default_energy" in cols:
        rows = conn.execute(
            text("SELECT id, default_energy FROM item_definitions WHERE default_energy IS NOT NULL")
        ).fetchall()
        for row_id, default_energy in rows:
            meta = json.dumps({"energy": int(default_energy)})
            conn.execute(
                text(
                    "UPDATE item_definitions SET custom_metadata = :meta WHERE id = :id"
                ),
                {"meta": meta, "id": str(row_id)},
            )
        op.drop_column("item_definitions", "default_energy")

    conn.execute(
        text(
            "UPDATE item_definitions SET custom_metadata = :meta WHERE id = :id"
        ),
        {
            "meta": json.dumps({"energy": 48}),
            "id": BUILTIN_FOOD_ID,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "item_definitions"):
        return

    cols = {c["name"] for c in inspect(conn).get_columns("item_definitions")}
    if "default_energy" not in cols:
        op.add_column("item_definitions", sa.Column("default_energy", sa.Integer(), nullable=True))

    if "custom_metadata" in cols:
        rows = conn.execute(text("SELECT id, custom_metadata FROM item_definitions")).fetchall()
        for row_id, raw_meta in rows:
            energy = None
            if isinstance(raw_meta, dict) and raw_meta.get("energy") is not None:
                try:
                    energy = int(raw_meta["energy"])
                except (TypeError, ValueError):
                    energy = None
            conn.execute(
                text("UPDATE item_definitions SET default_energy = :energy WHERE id = :id"),
                {"energy": energy, "id": str(row_id)},
            )
        op.drop_column("item_definitions", "custom_metadata")
