"""Add int toolkit utility and control palette colors

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-03-20

Summary:
  - Add add_ints, subtract_ints, multiply_ints, divide_ints, modulo_ints, min_ints,
    max_ints, not_control, between_control keys to existing palettes' colors JSON
"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "z6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "y5z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {
    "add_ints": "#2dd4bf",
    "subtract_ints": "#14b8a6",
    "multiply_ints": "#5eead4",
    "divide_ints": "#0d9488",
    "modulo_ints": "#f472b6",
    "min_ints": "#34d399",
    "max_ints": "#eab308",
    "not_control": "#6366f1",
    "between_control": "#c026d3",
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
