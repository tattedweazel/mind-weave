"""Google OAuth connections for workflow skills (Gmail / Calendar readonly)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.google_workflow_oauth import (
    build_workflow_authorization_url,
    exchange_code_for_token_response,
    fetch_userinfo_sub_email,
    revoke_token,
)
from app.core.logging import logger
from app.core.oauth_state import consume_workflow_google_state as consume_wf_google_state
from app.core.oauth_state import create_workflow_google_state
from app.core.user_api_keys_crypto import decrypt_sensitive_at_rest, encrypt_sensitive_at_rest
from app.persistence.db import get_session
from app.persistence.tables import GoogleWorkflowConnection, User, utc_now

router = APIRouter()


class GoogleWorkflowAuthorizeResponse(BaseModel):
    redirect_url: str


class GoogleWorkflowConnectionRead(BaseModel):
    id: uuid.UUID
    google_email: str | None
    label: str | None
    scopes: str
    created_at: datetime
    updated_at: datetime


class GoogleWorkflowConnectionLabelUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=128)


@router.post("/oauth/authorize", response_model=GoogleWorkflowAuthorizeResponse)
async def google_workflow_authorize(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    state = create_workflow_google_state(session, current_user.id)
    return GoogleWorkflowAuthorizeResponse(redirect_url=build_workflow_authorization_url(state))


@router.get("/oauth/callback")
async def google_workflow_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    base = settings.FRONTEND_URL.rstrip("/")
    if error:
        return RedirectResponse(url=f"{base}/?google_error=workflow_denied")
    if not code or not state:
        return RedirectResponse(url=f"{base}/?google_error=workflow_missing_params")

    user_id = consume_wf_google_state(session, state)
    if user_id is None:
        return RedirectResponse(url=f"{base}/?google_error=workflow_expired")

    try:
        token_json = exchange_code_for_token_response(code)
    except Exception:
        logger.exception("Google workflow token exchange failed")
        return RedirectResponse(url=f"{base}/?google_error=workflow_exchange_failed")

    refresh = token_json.get("refresh_token")
    access = token_json.get("access_token")
    if not refresh or not access:
        return RedirectResponse(url=f"{base}/?google_error=workflow_no_refresh")

    scope_str = token_json.get("scope") or ""
    if not isinstance(scope_str, str):
        scope_str = str(scope_str)

    try:
        info = fetch_userinfo_sub_email(access)
    except Exception:
        logger.exception("Google workflow userinfo failed")
        return RedirectResponse(url=f"{base}/?google_error=workflow_userinfo_failed")

    google_sub = info["sub"]
    google_email = info.get("email") or ""

    enc_refresh = encrypt_sensitive_at_rest(refresh)
    enc_access = encrypt_sensitive_at_rest(access)
    expires_in = token_json.get("expires_in")
    expires_at = None
    if isinstance(expires_in, (int, float)):
        expires_at = utc_now() + timedelta(seconds=float(expires_in))

    now = utc_now()
    existing = session.exec(
        select(GoogleWorkflowConnection).where(
            col(GoogleWorkflowConnection.user_id) == user_id,
            col(GoogleWorkflowConnection.google_sub) == google_sub,
        )
    ).first()

    if existing:
        existing.refresh_token_encrypted = enc_refresh
        existing.access_token_encrypted = enc_access
        existing.access_token_expires_at = expires_at
        existing.scopes = scope_str[:1024]
        existing.google_email = google_email or existing.google_email
        existing.updated_at = now
        session.add(existing)
    else:
        session.add(
            GoogleWorkflowConnection(
                user_id=user_id,
                google_sub=google_sub,
                google_email=google_email or None,
                refresh_token_encrypted=enc_refresh,
                access_token_encrypted=enc_access,
                access_token_expires_at=expires_at,
                scopes=scope_str[:1024],
                created_at=now,
                updated_at=now,
            )
        )
    session.commit()

    return RedirectResponse(url=f"{base}/?google_workflow_connected=1")


@router.get("/connections", response_model=list[GoogleWorkflowConnectionRead])
async def list_google_workflow_connections(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stmt = (
        select(GoogleWorkflowConnection)
        .where(col(GoogleWorkflowConnection.user_id) == current_user.id)
        .order_by(GoogleWorkflowConnection.created_at)  # type: ignore[arg-type]
    )
    rows = session.exec(stmt).all()
    return [
        GoogleWorkflowConnectionRead(
            id=r.id,
            google_email=r.google_email,
            label=r.label,
            scopes=r.scopes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.patch("/connections/{connection_id}", response_model=GoogleWorkflowConnectionRead)
async def update_google_workflow_connection_label(
    connection_id: uuid.UUID,
    body: GoogleWorkflowConnectionLabelUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    row = session.exec(
        select(GoogleWorkflowConnection).where(
            col(GoogleWorkflowConnection.id) == connection_id,
            col(GoogleWorkflowConnection.user_id) == current_user.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    row.label = body.label
    row.updated_at = utc_now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return GoogleWorkflowConnectionRead(
        id=row.id,
        google_email=row.google_email,
        label=row.label,
        scopes=row.scopes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_google_workflow_connection(
    connection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    row = session.exec(
        select(GoogleWorkflowConnection).where(
            col(GoogleWorkflowConnection.id) == connection_id,
            col(GoogleWorkflowConnection.user_id) == current_user.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    refresh = decrypt_sensitive_at_rest(row.refresh_token_encrypted)
    if refresh:
        revoke_token(refresh)
    session.delete(row)
    session.commit()
    return None
