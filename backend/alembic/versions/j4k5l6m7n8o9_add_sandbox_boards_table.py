"""Add sandbox_boards table and seed empty system board.

Revision ID: j4k5l6m7n8o9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-22
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID
from app.domain.sandbox.empty_board_seed import EMPTY_BOARD_BUILTIN_SLUG, empty_board_definition

revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_boards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("builtin_slug", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sandbox_boards_user_id", "sandbox_boards", ["user_id"])
    op.create_index("ix_sandbox_boards_name", "sandbox_boards", ["name"])
    op.create_index("ix_sandbox_boards_is_system", "sandbox_boards", ["is_system"])
    op.create_index("ix_sandbox_boards_builtin_slug", "sandbox_boards", ["builtin_slug"], unique=True)

    body = deterministic_json_dumps(empty_board_definition().model_dump(mode="json"))
    now = datetime.now(timezone.utc)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO sandbox_boards (
                id, user_id, name, description, body, is_system, builtin_slug,
                created_at, updated_at
            ) VALUES (
                :id, NULL, :name, :desc, :body, 1, :slug,
                :created_at, :updated_at
            )
            """
        ),
        {
            "id": EMPTY_SANDBOX_BOARD_ID.hex,
            "name": "Empty Board",
            "desc": "Default empty sandbox grid with no items or creatures",
            "body": body,
            "slug": EMPTY_BOARD_BUILTIN_SLUG,
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM sandbox_boards WHERE builtin_slug = :slug"),
        {"slug": EMPTY_BOARD_BUILTIN_SLUG},
    )
    op.drop_index("ix_sandbox_boards_builtin_slug", table_name="sandbox_boards")
    op.drop_index("ix_sandbox_boards_is_system", table_name="sandbox_boards")
    op.drop_index("ix_sandbox_boards_name", table_name="sandbox_boards")
    op.drop_index("ix_sandbox_boards_user_id", table_name="sandbox_boards")
    op.drop_table("sandbox_boards")
