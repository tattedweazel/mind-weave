"""Add Companion, Workspace, sessions, turns, replay, memory tables

Revision ID: a1b2c3d4e5f8
Revises: i3j4k5l6m7n8
Create Date: 2026-04-08

Summary:
  - companions: one per user (unique owner_user_id)
  - workspaces: typed runtime config + capability keys per user+name
  - workspace_sessions, workspace_turns, workspace_replays, companion_memory_entries
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default="Companion"),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("persona_id", sa.Uuid(), nullable=True),
        sa.Column("identity_profile", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("default_mode", sa.String(), nullable=False, server_default="default"),
        sa.Column("available_modes", sa.JSON(), nullable=False, server_default='["default"]'),
        sa.Column("enabled_capability_keys", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("memory_policy", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", name="uq_companions_owner_user_id"),
    )
    op.create_index(op.f("ix_companions_owner_user_id"), "companions", ["owner_user_id"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("runtime_configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ui_configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("interaction_configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("available_capability_keys", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_workspaces_owner_name"),
    )
    op.create_index(op.f("ix_workspaces_owner_user_id"), "workspaces", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_workspaces_name"), "workspaces", ["name"], unique=False)

    op.create_table(
        "workspace_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("companion_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default="Chat"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transient_state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["companion_id"], ["companions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspace_sessions_workspace_id"), "workspace_sessions", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_workspace_sessions_companion_id"), "workspace_sessions", ["companion_id"], unique=False)
    op.create_index(op.f("ix_workspace_sessions_status"), "workspace_sessions", ["status"], unique=False)

    op.create_table(
        "workspace_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False, server_default=""),
        sa.Column("outcome_type", sa.String(), nullable=False, server_default="respond_directly"),
        sa.Column("interpretation_result", sa.JSON(), nullable=True),
        sa.Column("routing_plan", sa.JSON(), nullable=True),
        sa.Column("execution_results", sa.JSON(), nullable=True),
        sa.Column("composition_result", sa.JSON(), nullable=True),
        sa.Column("delivered_response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["workspace_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_workspace_turns_session_index"),
    )
    op.create_index(op.f("ix_workspace_turns_session_id"), "workspace_turns", ["session_id"], unique=False)
    op.create_index(op.f("ix_workspace_turns_turn_index"), "workspace_turns", ["turn_index"], unique=False)
    op.create_index(op.f("ix_workspace_turns_trace_id"), "workspace_turns", ["trace_id"], unique=False)
    op.create_index(op.f("ix_workspace_turns_outcome_type"), "workspace_turns", ["outcome_type"], unique=False)

    op.create_table(
        "workspace_replays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("interpretation_trace", sa.JSON(), nullable=True),
        sa.Column("routing_trace", sa.JSON(), nullable=True),
        sa.Column("execution_trace", sa.JSON(), nullable=True),
        sa.Column("composition_trace", sa.JSON(), nullable=True),
        sa.Column("delivery_trace", sa.JSON(), nullable=True),
        sa.Column("state_update_summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["workspace_turns.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["workspace_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", name="uq_workspace_replays_turn_id"),
    )
    op.create_index(op.f("ix_workspace_replays_turn_id"), "workspace_replays", ["turn_id"], unique=True)
    op.create_index(op.f("ix_workspace_replays_workspace_id"), "workspace_replays", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_workspace_replays_session_id"), "workspace_replays", ["session_id"], unique=False)

    op.create_table(
        "companion_memory_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("companion_id", sa.Uuid(), nullable=False),
        sa.Column("memory_type", sa.String(), nullable=False, server_default="fact"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("salience", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source_session_id", sa.Uuid(), nullable=True),
        sa.Column("source_turn_id", sa.Uuid(), nullable=True),
        sa.Column("visibility_policy", sa.String(), nullable=False, server_default="user_only"),
        sa.Column("approval_status", sa.String(), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["companion_id"], ["companions.id"]),
        sa.ForeignKeyConstraint(["source_session_id"], ["workspace_sessions.id"]),
        sa.ForeignKeyConstraint(["source_turn_id"], ["workspace_turns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companion_memory_entries_companion_id"), "companion_memory_entries", ["companion_id"], unique=False)
    op.create_index(op.f("ix_companion_memory_entries_memory_type"), "companion_memory_entries", ["memory_type"], unique=False)
    op.create_index(op.f("ix_companion_memory_entries_approval_status"), "companion_memory_entries", ["approval_status"], unique=False)
    op.create_index(
        op.f("ix_companion_memory_entries_source_session_id"),
        "companion_memory_entries",
        ["source_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_companion_memory_entries_source_turn_id"),
        "companion_memory_entries",
        ["source_turn_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("companion_memory_entries")
    op.drop_table("workspace_replays")
    op.drop_table("workspace_turns")
    op.drop_table("workspace_sessions")
    op.drop_table("workspaces")
    op.drop_table("companions")
