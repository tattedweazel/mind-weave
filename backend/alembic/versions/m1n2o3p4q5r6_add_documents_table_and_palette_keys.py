"""Add documents table and palette keys for document / read_document_property

Revision ID: m1n2o3p4q5r6
Revises: f9a0b1c2d3e4
Create Date: 2026-03-22

Summary:
  - Create documents table (Markdown body, globally unique name)
  - Add document and read_document_property keys to existing palettes' colors JSON
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {
    "document": "#2dd4bf",
    "read_document_property": "#14b8a6",
}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "documents" not in inspector.get_table_names():
        op.create_table(
            "documents",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"], unique=False)
        op.create_index(op.f("ix_documents_name"), "documents", ["name"], unique=True)

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
    if "documents" in inspector.get_table_names():
        op.drop_index(op.f("ix_documents_name"), table_name="documents")
        op.drop_index(op.f("ix_documents_user_id"), table_name="documents")
        op.drop_table("documents")
