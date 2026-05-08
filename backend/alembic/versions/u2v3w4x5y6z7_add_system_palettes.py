"""Add system_palettes for app-wide theme presets.

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, Sequence[str], None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "system_palettes" not in insp.get_table_names():
        op.create_table(
            "system_palettes",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("slug", sa.String(), nullable=True),
            sa.Column("colors", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    insp = sa.inspect(bind)
    ix = {i["name"] for i in insp.get_indexes("system_palettes")}
    if "ix_system_palettes_slug" not in ix:
        op.create_index("ix_system_palettes_slug", "system_palettes", ["slug"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "system_palettes" in insp.get_table_names():
        if "ix_system_palettes_slug" in {i["name"] for i in insp.get_indexes("system_palettes")}:
            op.drop_index("ix_system_palettes_slug", table_name="system_palettes")
        op.drop_table("system_palettes")
