"""Tests for user-level Google workflow connection resolution."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session

from app.integrations.google_workflow_connection import get_user_workflow_google_connection
from app.persistence.tables import GoogleWorkflowConnection, User, utc_now


def _add_user(session: Session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, username=f"u_{uid.hex[:8]}", password_hash="h", is_admin=False))
    session.commit()
    return uid


def _add_connection(session: Session, user_id: uuid.UUID, *, sub_suffix: str = "a") -> uuid.UUID:
    cid = uuid.uuid4()
    now = utc_now()
    session.add(
        GoogleWorkflowConnection(
            id=cid,
            user_id=user_id,
            google_sub=f"sub_{sub_suffix}_{cid.hex[:8]}",
            refresh_token_encrypted="encrypted-test-token",
            scopes="https://www.googleapis.com/auth/gmail.readonly",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return cid


def test_get_user_workflow_google_connection_none_when_empty(db_session: Session):
    uid = _add_user(db_session)
    assert get_user_workflow_google_connection(db_session, uid) is None


def test_get_user_workflow_google_connection_returns_row(db_session: Session):
    uid = _add_user(db_session)
    cid = _add_connection(db_session, uid)
    row = get_user_workflow_google_connection(db_session, uid)
    assert row is not None
    assert row.id == cid


def test_get_user_workflow_google_connection_prefers_most_recently_updated(db_session: Session):
    from datetime import timedelta

    uid = _add_user(db_session)
    _add_connection(db_session, uid, sub_suffix="old")
    newer = _add_connection(db_session, uid, sub_suffix="new")
    newer_row = db_session.get(GoogleWorkflowConnection, newer)
    assert newer_row is not None
    newer_row.updated_at = utc_now() + timedelta(seconds=60)
    db_session.add(newer_row)
    db_session.commit()
    row = get_user_workflow_google_connection(db_session, uid)
    assert row is not None
    assert row.id == newer
