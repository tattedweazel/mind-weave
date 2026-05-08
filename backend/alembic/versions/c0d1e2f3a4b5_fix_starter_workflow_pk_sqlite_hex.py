"""SQLite: normalize starter sandbox workflow PK to 32-char hex (SQLAlchemy UUID bind format).

Revision ID: c0d1e2f3a4b5
Revises: a7b8c9d0e1f2
Create Date: 2026-03-25

Alembic seeded the row with dashed UUID text while SQLModel queries bind UUIDs
without hyphens on SQLite, so `get_workflow(starter_id)` returned None.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.sandbox.starter_workflow_seed import STARTER_BUILTIN_SLUG, STARTER_SANDBOX_WORKFLOW_ID

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    old_id = str(STARTER_SANDBOX_WORKFLOW_ID)
    new_id = STARTER_SANDBOX_WORKFLOW_ID.hex
    slug_row = conn.execute(
        sa.text("SELECT id FROM workflow_definitions WHERE builtin_slug = :slug LIMIT 1"),
        {"slug": STARTER_BUILTIN_SLUG},
    ).fetchone()
    if not slug_row:
        return
    current_id = slug_row[0]
    if current_id == new_id:
        return
    if current_id != old_id:
        # Unexpected id for this slug; do not rewrite.
        return
    conn.execute(
        sa.text("UPDATE workflow_runs SET workflow_id = :new WHERE workflow_id = :old"),
        {"new": new_id, "old": old_id},
    )
    conn.execute(
        sa.text("UPDATE workflow_definitions SET id = :new WHERE id = :old"),
        {"new": new_id, "old": old_id},
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    old_id = str(STARTER_SANDBOX_WORKFLOW_ID)
    new_id = STARTER_SANDBOX_WORKFLOW_ID.hex
    row = conn.execute(
        sa.text("SELECT id FROM workflow_definitions WHERE builtin_slug = :slug LIMIT 1"),
        {"slug": STARTER_BUILTIN_SLUG},
    ).fetchone()
    if not row or row[0] != new_id:
        return
    conn.execute(
        sa.text("UPDATE workflow_runs SET workflow_id = :old WHERE workflow_id = :new"),
        {"new": new_id, "old": old_id},
    )
    conn.execute(
        sa.text("UPDATE workflow_definitions SET id = :old WHERE id = :new"),
        {"new": new_id, "old": old_id},
    )
