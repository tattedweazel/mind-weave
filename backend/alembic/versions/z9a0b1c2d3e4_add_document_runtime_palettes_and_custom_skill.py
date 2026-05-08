"""Add document runtime palette keys and workflow_definitions.expose_as_custom_skill

Revision ID: z9a0b1c2d3e4
Revises: w1x2y3z4a5b6
Create Date: 2026-03-24

Summary:
  - Add expose_as_custom_skill to workflow_definitions (default false)
  - Add palette color keys for new document utilities
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "z9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "w1x2y3z4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {
    "load_document": "#2dd4bf",
    "upsert_document": "#14b8a6",
    "parse_document_body": "#5eead4",
    "write_object_to_document_body": "#0d9488",
    "append_value_to_document": "#0f766e",
    "validate_against_structure": "#a78bfa",
}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("workflow_definitions")]
    if "expose_as_custom_skill" not in cols:
        op.add_column(
            "workflow_definitions",
            sa.Column(
                "expose_as_custom_skill",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        op.create_index(
            op.f("ix_workflow_definitions_expose_as_custom_skill"),
            "workflow_definitions",
            ["expose_as_custom_skill"],
            unique=False,
        )

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

    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("workflow_definitions")]
    if "expose_as_custom_skill" in cols:
        op.drop_index(
            op.f("ix_workflow_definitions_expose_as_custom_skill"),
            table_name="workflow_definitions",
        )
        op.drop_column("workflow_definitions", "expose_as_custom_skill")
