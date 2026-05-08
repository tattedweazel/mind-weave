"""Add google_user_id and google_email to users for Google OAuth association

Revision ID: o5c6d7e8f9a0
Revises: n4b5c6d7e8f9
Create Date: 2026-03-18

Summary:
  - Add google_user_id (unique when not null) and google_email to users table
  - Enables Google account association for existing users
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "n4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Google OAuth fields to users table."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("google_user_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("google_email", sa.String(), nullable=True)
        )
        batch_op.create_index(
            "ix_users_google_user_id",
            ["google_user_id"],
            unique=True,
        )


def downgrade() -> None:
    """Remove Google OAuth fields from users table."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_google_user_id", column_names=["google_user_id"])
        batch_op.drop_column("google_email")
        batch_op.drop_column("google_user_id")
