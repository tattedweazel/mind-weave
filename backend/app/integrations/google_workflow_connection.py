"""Resolve the user's single Google workflow OAuth connection for skill execution."""

from __future__ import annotations

import uuid

from sqlmodel import Session, col, select

from app.core.user_api_keys_crypto import decrypt_sensitive_at_rest
from app.persistence.tables import GoogleWorkflowConnection

GOOGLE_WORKFLOW_CONNECTION_REQUIRED_MSG = (
    "This step requires a Google account for workflows. "
    "Connect or re-connect under My Settings → Google Account → Google for workflows."
)


def get_user_workflow_google_connection(
    session: Session,
    user_id: uuid.UUID,
) -> GoogleWorkflowConnection | None:
    """Return the user's workflow Google connection (most recently updated), if any."""
    stmt = (
        select(GoogleWorkflowConnection)
        .where(col(GoogleWorkflowConnection.user_id) == user_id)
        .order_by(GoogleWorkflowConnection.updated_at.desc())  # type: ignore[attr-defined]
    )
    return session.exec(stmt).first()


def delete_user_google_workflow_connections_except(
    session: Session,
    user_id: uuid.UUID,
    *,
    keep_id: uuid.UUID | None = None,
    revoke: bool = True,
) -> None:
    """Remove all workflow Google connections for ``user_id`` except ``keep_id`` (if set)."""
    from app.core.google_workflow_oauth import revoke_token

    rows = list(
        session.exec(
            select(GoogleWorkflowConnection).where(col(GoogleWorkflowConnection.user_id) == user_id)
        ).all()
    )
    for row in rows:
        if keep_id is not None and row.id == keep_id:
            continue
        if revoke:
            refresh = decrypt_sensitive_at_rest(row.refresh_token_encrypted)
            if refresh:
                revoke_token(refresh)
        session.delete(row)
