"""Add workflow_projects and workflow_definitions.project_id; seed Shared per user

Revision ID: w1x2y3z4a5b6
Revises: m1n2o3p4q5r6
Create Date: 2026-03-23

Summary:
  - workflow_projects: per-user folders (unique user_id + name_lower)
  - workflow_definitions.project_id FK (nullable, ON DELETE SET NULL)
  - Seed Shared folder per user; assign user-owned workflows to Shared
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "w1x2y3z4a5b6"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHARED_NAME = "Shared"
SHARED_LOWER = "shared"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "workflow_projects" not in inspector.get_table_names():
        op.create_table(
            "workflow_projects",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("name_lower", sa.String(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name_lower", name="uq_workflow_projects_user_name_lower"),
        )
        op.create_index(op.f("ix_workflow_projects_user_id"), "workflow_projects", ["user_id"], unique=False)
        op.create_index(op.f("ix_workflow_projects_name"), "workflow_projects", ["name"], unique=False)
        op.create_index(op.f("ix_workflow_projects_name_lower"), "workflow_projects", ["name_lower"], unique=False)
        op.create_index(op.f("ix_workflow_projects_sort_order"), "workflow_projects", ["sort_order"], unique=False)

    now = datetime.now(timezone.utc)
    users = conn.execute(text("SELECT id FROM users")).fetchall()
    for (uid,) in users:
        uid_s = str(uid)
        exists = conn.execute(
            text(
                "SELECT 1 FROM workflow_projects WHERE user_id = :uid AND name_lower = :nl LIMIT 1"
            ),
            {"uid": uid_s, "nl": SHARED_LOWER},
        ).fetchone()
        if exists:
            continue
        pid = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO workflow_projects (id, user_id, name, name_lower, sort_order, created_at, updated_at)
                VALUES (:id, :uid, :name, :nl, 0, :ts, :ts)
                """
            ),
            {"id": pid, "uid": uid_s, "name": SHARED_NAME, "nl": SHARED_LOWER, "ts": now},
        )

    inspector = inspect(conn)
    wf_cols = {c["name"] for c in inspector.get_columns("workflow_definitions")}
    if "project_id" not in wf_cols:
        with op.batch_alter_table("workflow_definitions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "project_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "workflow_projects.id",
                        ondelete="SET NULL",
                        name="fk_workflow_definitions_project_id",
                    ),
                    nullable=True,
                )
            )

    conn.execute(
        text(
            """
            UPDATE workflow_definitions AS wd
            SET project_id = (
                SELECT wp.id FROM workflow_projects wp
                WHERE wp.user_id = wd.user_id AND wp.name_lower = :nl
                LIMIT 1
            )
            WHERE wd.user_id IS NOT NULL
              AND wd.project_id IS NULL
            """
        ),
        {"nl": SHARED_LOWER},
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "workflow_definitions" in inspector.get_table_names():
        wf_cols = {c["name"] for c in inspector.get_columns("workflow_definitions")}
        if "project_id" in wf_cols:
            with op.batch_alter_table("workflow_definitions") as batch_op:
                batch_op.drop_column("project_id")

    if "workflow_projects" in inspector.get_table_names():
        op.drop_index(op.f("ix_workflow_projects_sort_order"), table_name="workflow_projects")
        op.drop_index(op.f("ix_workflow_projects_name_lower"), table_name="workflow_projects")
        op.drop_index(op.f("ix_workflow_projects_name"), table_name="workflow_projects")
        op.drop_index(op.f("ix_workflow_projects_user_id"), table_name="workflow_projects")
        op.drop_table("workflow_projects")
