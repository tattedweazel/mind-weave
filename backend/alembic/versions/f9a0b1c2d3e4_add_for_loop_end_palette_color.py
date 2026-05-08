"""Add for_loop_end_control to palette colors

Revision ID: f9a0b1c2d3e4
Revises: d5e6f7a8b9c0
Create Date: 2026-03-22

Summary:
  - Add for_loop_end_control key to existing palettes' colors JSON
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLOR = {"for_loop_end_control": "#047857"}


def upgrade() -> None:
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
