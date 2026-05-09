"""Async Gmail / Calendar REST calls — mock httpx in tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from uuid import UUID

import httpx
from sqlmodel import Session, col, select

from app.core.google_workflow_oauth import refresh_access_token_async
from app.core.logging import logger
from app.core.user_api_keys_crypto import decrypt_sensitive_at_rest, encrypt_sensitive_at_rest
from app.persistence.tables import GoogleWorkflowConnection, utc_now

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


def _access_buffer_seconds() -> int:
    return 90


async def ensure_workflow_google_access_token(session: Session, connection_id: UUID, user_id: UUID) -> str:
    """
    Load connection for user, refresh access token if missing or near expiry, persist, return bearer token.
    """
    row = session.exec(
        select(GoogleWorkflowConnection).where(
            col(GoogleWorkflowConnection.id) == connection_id,
            col(GoogleWorkflowConnection.user_id) == user_id,
        )
    ).first()
    if row is None:
        raise ValueError("Google workflow connection not found")

    refresh_plain = decrypt_sensitive_at_rest(row.refresh_token_encrypted)
    if not refresh_plain:
        raise ValueError("Invalid stored refresh token")

    now = utc_now()
    need_refresh = True
    access_plain: Optional[str] = None
    if row.access_token_encrypted and row.access_token_expires_at:
        expires = row.access_token_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now + timedelta(seconds=_access_buffer_seconds()):
            need_refresh = False
            access_plain = decrypt_sensitive_at_rest(row.access_token_encrypted)

    if need_refresh:
        try:
            data = await refresh_access_token_async(refresh_plain)
        except httpx.HTTPError as e:
            logger.warning("Google token refresh failed: %s", e)
            raise ValueError("Could not refresh Google access token") from e
        access_plain = data.get("access_token")
        if not access_plain or not isinstance(access_plain, str):
            raise ValueError("No access_token in refresh response")
        expires_in = data.get("expires_in")
        expires_at: Optional[datetime] = None
        if isinstance(expires_in, (int, float)):
            expires_at = now + timedelta(seconds=float(expires_in))
        row.access_token_encrypted = encrypt_sensitive_at_rest(access_plain)
        row.access_token_expires_at = expires_at
        row.updated_at = now
        new_refresh = data.get("refresh_token")
        if isinstance(new_refresh, str) and new_refresh:
            row.refresh_token_encrypted = encrypt_sensitive_at_rest(new_refresh)
        session.add(row)
        session.commit()
        session.refresh(row)

    assert access_plain is not None
    return access_plain


async def gmail_list_messages(
    access_token: str,
    *,
    max_results: int = 10,
    query: Optional[str] = None,
    label_ids: Optional[list[str]] = None,
    include_spam_trash: bool = False,
) -> dict[str, Any]:
    """GET users.messages.list — returns raw API JSON."""
    params: list[tuple[str, Any]] = [
        ("maxResults", max(1, min(max_results, 100))),
    ]
    if query:
        params.append(("q", query))
    if include_spam_trash:
        params.append(("includeSpamTrash", "true"))
    for lid in label_ids or []:
        if isinstance(lid, str) and lid.strip():
            params.append(("labelIds", lid.strip()))
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GMAIL_API_BASE}/users/me/messages",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())


async def gmail_get_message_full(access_token: str, message_id: str) -> dict[str, Any]:
    """GET users.messages.get — format=full for payload, headers, and body parts."""
    from urllib.parse import quote

    mid = quote(str(message_id), safe="")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GMAIL_API_BASE}/users/me/messages/{mid}",
            params={"format": "full"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())


async def calendar_list_events(
    access_token: str,
    calendar_id: str,
    *,
    time_min: str,
    time_max: str,
) -> dict[str, Any]:
    """GET calendars.events.list — RFC3339 time_min / time_max."""
    params: dict[str, Any] = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    from urllib.parse import quote

    cal_path = quote(calendar_id, safe="")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{CALENDAR_API_BASE}/calendars/{cal_path}/events",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())
