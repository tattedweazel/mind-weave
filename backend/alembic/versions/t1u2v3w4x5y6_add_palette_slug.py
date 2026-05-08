"""Add palettes.slug for stable built-in preset ids.

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-03-19

Summary:
  - Nullable unique slug on palettes
  - Backfill system palettes (user_id IS NULL) from display name
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, Sequence[str], None] = "s0t1u2v3w4x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME_TO_SLUG = (
    ("Default", "default"),
    ("Slate", "slate"),
    ("Paper", "paper"),
    ("Maritime", "maritime"),
    ("Aurora", "aurora"),
    ("Meadow", "meadow"),
    ("Arcade", "arcade"),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("palettes")]
    if "slug" not in cols:
        with op.batch_alter_table("palettes") as batch_op:
            batch_op.add_column(sa.Column("slug", sa.String(), nullable=True))
    insp = sa.inspect(bind)
    ix_names = {ix["name"] for ix in insp.get_indexes("palettes")}
    if "ix_palettes_slug" not in ix_names:
        op.create_index("ix_palettes_slug", "palettes", ["slug"], unique=True)

    for name, slug in NAME_TO_SLUG:
        bind.execute(
            sa.text(
                "UPDATE palettes SET slug = :slug "
                "WHERE user_id IS NULL AND name = :name AND (slug IS NULL OR slug = '')"
            ),
            {"slug": slug, "name": name},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ix_palettes_slug" in {ix["name"] for ix in insp.get_indexes("palettes")}:
        op.drop_index("ix_palettes_slug", table_name="palettes")
    cols = [c["name"] for c in insp.get_columns("palettes")]
    if "slug" in cols:
        with op.batch_alter_table("palettes") as batch_op:
            batch_op.drop_column("slug")
