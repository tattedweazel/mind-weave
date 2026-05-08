"""Add gt_control, lt_control, gte_control, lte_control, and_control, or_control, xor_control to palette colors

Revision ID: n4b5c6d7e8f9
Revises: m3a4b5c6d7e8
Create Date: 2026-03-18

Summary:
  - Add new control node keys to existing palettes' colors JSON
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "n4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "m3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {
    "gt_control": "#0891b2",
    "lt_control": "#0891b2",
    "gte_control": "#0891b2",
    "lte_control": "#0891b2",
    "and_control": "#0d9488",
    "or_control": "#0d9488",
    "xor_control": "#0d9488",
}


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT id, colors FROM palettes"))
    rows = result.fetchall()

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
    result = conn.execute(text("SELECT id, colors FROM palettes"))
    rows = result.fetchall()

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
