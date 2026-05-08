"""Add final_url to url_snapshot_artifacts.

Revision ID: d0e1f2a3b4c5
Revises: a2b3c4d5e6f7
Create Date: 2026-04-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("url_snapshot_artifacts", sa.Column("final_url", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("url_snapshot_artifacts", "final_url")
