"""Add palettes table and workflow_definitions.palette_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-18

Summary:
  - Create palettes table (id, user_id, name, colors JSON, created_at, updated_at)
  - Add palette_id FK to workflow_definitions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    if "palettes" not in insp.get_table_names():
        op.create_table(
            "palettes",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("colors", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "palette_id" not in [c["name"] for c in insp.get_columns("workflow_definitions")]:
        with op.batch_alter_table("workflow_definitions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "palette_id",
                    sa.Uuid(),
                    sa.ForeignKey("palettes.id", name="fk_wf_def_palette_id"),
                    nullable=True,
                    index=True,
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("workflow_definitions") as batch_op:
        batch_op.drop_column("palette_id")
    op.drop_table("palettes")
