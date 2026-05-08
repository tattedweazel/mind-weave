"""Add string_to_list to palette colors

Revision ID: a1b2c3d4e5f7
Revises: z6a7b8c9d0e1
Create Date: 2026-03-20

Summary:
  - Add string_to_list key to existing palettes' colors JSON
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLOR = {"string_to_list": "#67e8f9"}


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
