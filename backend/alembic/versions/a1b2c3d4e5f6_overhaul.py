"""Overhaul: simplify personas, add steps and workflow_definitions, drop conversations/messages/memories

Revision ID: a1b2c3d4e5f6
Revises: da529fe9d995
Create Date: 2026-03-17

Summary of changes:
  - personas: drop old structured columns, add system_prompt / default_model / updated_at
  - steps: new table
  - workflow_definitions: new table
  - conversations, messages, memories: dropped
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "da529fe9d995"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply schema changes."""

    # ------------------------------------------------------------------
    # 1. Alter personas table
    # ------------------------------------------------------------------
    # Add new columns first (with server defaults so existing rows are valid).
    with op.batch_alter_table("personas") as batch_op:
        # Migrate primary_goal → system_prompt if the column exists.
        # SQLite doesn't support dropping columns in ALTER TABLE, so we use
        # batch mode which rewrites the table.
        batch_op.add_column(
            sa.Column("system_prompt", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("default_model", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        # Drop old columns that no longer belong.
        batch_op.drop_column("primary_goal")
        batch_op.drop_column("communication_style")
        batch_op.drop_column("target_demographic")
        batch_op.drop_column("profanity_disabled")

    # ------------------------------------------------------------------
    # 2. Create steps table
    # ------------------------------------------------------------------
    op.create_table(
        "steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=False, index=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # 3. Create workflow_definitions table
    # ------------------------------------------------------------------
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("graph", sa.JSON(), nullable=False, server_default='{"nodes":[],"edges":[]}'),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # 4. Drop old tables (order matters: child tables before parents)
    # ------------------------------------------------------------------
    op.drop_table("messages")
    op.drop_table("memories")
    op.drop_table("conversations")


def downgrade() -> None:
    """Reverse schema changes (restores to the original structure)."""

    # Restore conversations, messages, memories tables.
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False, index=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=True, index=True),
        sa.Column("role", sa.String(), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=True, index=True),
        sa.Column("kind", sa.String(), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("source", sa.String(), nullable=False, server_default="user_confirmed"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_table("workflow_definitions")
    op.drop_table("steps")

    with op.batch_alter_table("personas") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("default_model")
        batch_op.drop_column("system_prompt")
        batch_op.add_column(sa.Column("primary_goal", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("communication_style", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("target_demographic", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("profanity_disabled", sa.Boolean(), nullable=False, server_default="0"))
