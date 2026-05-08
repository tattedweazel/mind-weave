"""Add revoked_refresh_tokens for refresh JWT jti revocation (SE-010)."""

from alembic import op
import sqlalchemy as sa


revision = "r7s8t9u0v1w2"
down_revision = "q8r9s0t1u2v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "revoked_refresh_tokens" in insp.get_table_names():
        return
    op.create_table(
        "revoked_refresh_tokens",
        sa.Column("jti", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index(
        "ix_revoked_refresh_tokens_expires_at",
        "revoked_refresh_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "revoked_refresh_tokens" not in insp.get_table_names():
        return
    try:
        op.drop_index("ix_revoked_refresh_tokens_expires_at", table_name="revoked_refresh_tokens")
    except Exception:
        pass
    op.drop_table("revoked_refresh_tokens")
