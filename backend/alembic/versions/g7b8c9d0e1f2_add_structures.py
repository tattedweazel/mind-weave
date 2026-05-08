"""Add structures table

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-18

Summary:
  - Add structures table for JSON schemas used in structured LLM outputs
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create structures table if it does not exist."""
    conn = op.get_bind()
    inspector = inspect(conn)
    if "structures" in inspector.get_table_names():
        return
    op.create_table(
        "structures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("json_schema", sa.String(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_structures_user_id"), "structures", ["user_id"], unique=False)
    op.create_index(op.f("ix_structures_name"), "structures", ["name"], unique=False)


def downgrade() -> None:
    """Drop structures table."""
    op.drop_index(op.f("ix_structures_name"), table_name="structures")
    op.drop_index(op.f("ix_structures_user_id"), table_name="structures")
    op.drop_table("structures")
