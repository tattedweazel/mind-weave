"""Add google_workflow_connections for per-user Gmail/Calendar OAuth tokens

Revision ID: x4y5z6a7b8c9
Revises: v3w4x5y6z7a8
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "google_workflow_connections" in insp.get_table_names():
        return

    op.create_table(
        "google_workflow_connections",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("google_email", sa.String(length=320), nullable=True),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("refresh_token_encrypted", sa.String(length=4096), nullable=False),
        sa.Column("access_token_encrypted", sa.String(length=4096), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_google_workflow_connections_user_id",
        "google_workflow_connections",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_workflow_connections_google_sub",
        "google_workflow_connections",
        ["google_sub"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_gwc_user_google_sub",
        "google_workflow_connections",
        ["user_id", "google_sub"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_gwc_user_google_sub", "google_workflow_connections", type_="unique")
    op.drop_index("ix_google_workflow_connections_google_sub", table_name="google_workflow_connections")
    op.drop_index("ix_google_workflow_connections_user_id", table_name="google_workflow_connections")
    op.drop_table("google_workflow_connections")
