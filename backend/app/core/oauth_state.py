"""
OAuth state and one-time session codes (DB-backed, SE-005 / SE-003).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Union

from sqlmodel import Session, col, delete

from app.persistence.tables import OAuthSessionCode, OAuthStateRecord, utc_now

_STATE_TTL = timedelta(minutes=5)
_SESSION_CODE_TTL = timedelta(minutes=5)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _purge_expired_states(session: Session) -> None:
    now = utc_now()
    session.exec(delete(OAuthStateRecord).where(col(OAuthStateRecord.expires_at) < now))
    session.exec(delete(OAuthSessionCode).where(col(OAuthSessionCode.expires_at) < now))
    session.commit()


def create_workflow_google_state(session: Session, user_id: uuid.UUID) -> str:
    """Workflow Google OAuth: bind CSRF state to user_id (Gmail/Calendar scopes)."""
    _purge_expired_states(session)
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthStateRecord(
            state=state,
            kind="workflow_google",
            user_id=user_id,
            expires_at=utc_now() + _STATE_TTL,
        )
    )
    session.commit()
    return state


def create_state(session: Session, user_id: uuid.UUID) -> str:
    """Association flow: bind OAuth state to user_id."""
    _purge_expired_states(session)
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthStateRecord(
            state=state,
            kind="associate",
            user_id=user_id,
            expires_at=utc_now() + _STATE_TTL,
        )
    )
    session.commit()
    return state


def create_login_state(session: Session) -> str:
    """Login flow: state token for CSRF only."""
    _purge_expired_states(session)
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthStateRecord(
            state=state,
            kind="login",
            user_id=None,
            expires_at=utc_now() + _STATE_TTL,
        )
    )
    session.commit()
    return state


def consume_state(session: Session, state: str) -> Optional[Union[uuid.UUID, Literal["login"]]]:
    row = session.get(OAuthStateRecord, state)
    if row is None or _as_utc(row.expires_at) < utc_now():
        if row is not None:
            session.delete(row)
            session.commit()
        return None
    session.delete(row)
    session.commit()
    if row.kind == "login":
        return "login"
    # associate and workflow_google both carry user_id
    return row.user_id


def consume_workflow_google_state(session: Session, state: str) -> Optional[uuid.UUID]:
    """Consume OAuth state only if kind is workflow_google (stricter than generic consume)."""
    row = session.get(OAuthStateRecord, state)
    if row is None or row.kind != "workflow_google" or _as_utc(row.expires_at) < utc_now():
        if row is not None:
            session.delete(row)
            session.commit()
        return None
    uid = row.user_id
    session.delete(row)
    session.commit()
    return uid


def create_google_session_code(session: Session, username: str) -> str:
    """Short-lived code sent in URL fragment after Google login; exchanged for HttpOnly cookies via POST."""
    _purge_expired_states(session)
    code = secrets.token_urlsafe(32)
    session.add(
        OAuthSessionCode(
            code=code,
            username=username,
            expires_at=utc_now() + _SESSION_CODE_TTL,
        )
    )
    session.commit()
    return code


def consume_google_session_code(session: Session, code: str) -> Optional[str]:
    row = session.get(OAuthSessionCode, code)
    if row is None or _as_utc(row.expires_at) < utc_now():
        if row is not None:
            session.delete(row)
            session.commit()
        return None
    username = row.username
    session.delete(row)
    session.commit()
    return username
