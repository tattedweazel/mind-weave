"""Add board_projects and sandbox_boards.project_id; seed Shared per user

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-24

Summary:
  - board_projects: per-user folders (unique user_id + name_lower)
  - sandbox_boards.project_id FK (nullable, ON DELETE SET NULL)
  - Seed Shared folder per user; assign user-owned boards to Shared
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHARED_NAME = "Shared"
SHARED_LOWER = "shared"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "board_projects" not in inspector.get_table_names():
        op.create_table(
            "board_projects",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("name_lower", sa.String(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name_lower", name="uq_board_projects_user_name_lower"),
        )
        op.create_index(op.f("ix_board_projects_user_id"), "board_projects", ["user_id"], unique=False)
        op.create_index(op.f("ix_board_projects_name"), "board_projects", ["name"], unique=False)
        op.create_index(op.f("ix_board_projects_name_lower"), "board_projects", ["name_lower"], unique=False)
        op.create_index(op.f("ix_board_projects_sort_order"), "board_projects", ["sort_order"], unique=False)

    now = datetime.now(timezone.utc)
    users = conn.execute(text("SELECT id FROM users")).fetchall()
    for (uid,) in users:
        uid_s = str(uid)
        exists = conn.execute(
            text(
                "SELECT 1 FROM board_projects WHERE user_id = :uid AND name_lower = :nl LIMIT 1"
            ),
            {"uid": uid_s, "nl": SHARED_LOWER},
        ).fetchone()
        if exists:
            continue
        pid = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO board_projects (id, user_id, name, name_lower, sort_order, created_at, updated_at)
                VALUES (:id, :uid, :name, :nl, 0, :ts, :ts)
                """
            ),
            {"id": pid, "uid": uid_s, "name": SHARED_NAME, "nl": SHARED_LOWER, "ts": now},
        )

    inspector = inspect(conn)
    sb_cols = {c["name"] for c in inspector.get_columns("sandbox_boards")}
    if "project_id" not in sb_cols:
        with op.batch_alter_table("sandbox_boards") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "project_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "board_projects.id",
                        ondelete="SET NULL",
                        name="fk_sandbox_boards_project_id",
                    ),
                    nullable=True,
                )
            )
        op.create_index(op.f("ix_sandbox_boards_project_id"), "sandbox_boards", ["project_id"], unique=False)

    conn.execute(
        text(
            """
            UPDATE sandbox_boards AS sb
            SET project_id = (
                SELECT bp.id FROM board_projects bp
                WHERE bp.user_id = sb.user_id AND bp.name_lower = :nl
                LIMIT 1
            )
            WHERE sb.user_id IS NOT NULL
              AND sb.is_system = 0
              AND sb.project_id IS NULL
            """
        ),
        {"nl": SHARED_LOWER},
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "sandbox_boards" in inspector.get_table_names():
        sb_cols = {c["name"] for c in inspector.get_columns("sandbox_boards")}
        if "project_id" in sb_cols:
            op.drop_index(op.f("ix_sandbox_boards_project_id"), table_name="sandbox_boards")
            with op.batch_alter_table("sandbox_boards") as batch_op:
                batch_op.drop_column("project_id")

    if "board_projects" in inspector.get_table_names():
        op.drop_index(op.f("ix_board_projects_sort_order"), table_name="board_projects")
        op.drop_index(op.f("ix_board_projects_name_lower"), table_name="board_projects")
        op.drop_index(op.f("ix_board_projects_name"), table_name="board_projects")
        op.drop_index(op.f("ix_board_projects_user_id"), table_name="board_projects")
        op.drop_table("board_projects")
