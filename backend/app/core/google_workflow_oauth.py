"""
Google OAuth for workflow API access (Gmail / Calendar readonly scopes).
Separate redirect URI and scopes from identity-only Google sign-in / association.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Minimal readonly scopes for MVP Gmail + Calendar workflow skills.
WORKFLOW_GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def build_workflow_authorization_url(state: str) -> str:
    """Authorization URL using workflow redirect URI and API scopes."""
    redirect_uri = settings.GOOGLE_WORKFLOW_REDIRECT_URI.strip()
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(WORKFLOW_GOOGLE_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token_response(code: str) -> dict[str, Any]:
    """Exchange authorization code for token JSON (sync; use httpx in tests)."""
    redirect_uri = settings.GOOGLE_WORKFLOW_REDIRECT_URI.strip()
    with httpx.Client() as client:
        token_resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_resp.raise_for_status()
        return token_resp.json()


async def exchange_code_for_token_response_async(code: str) -> dict[str, Any]:
    redirect_uri = settings.GOOGLE_WORKFLOW_REDIRECT_URI.strip()
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_resp.raise_for_status()
        return token_resp.json()


def fetch_userinfo_sub_email(access_token: str) -> dict[str, str]:
    """Return {\"sub\": str, \"email\": str} from userinfo."""
    with httpx.Client() as client:
        userinfo_resp = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    sub = userinfo.get("sub")
    if not sub:
        raise ValueError("No sub in userinfo response")
    email = userinfo.get("email") or ""
    return {"sub": str(sub), "email": str(email)}


async def fetch_userinfo_sub_email_async(access_token: str) -> dict[str, str]:
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    sub = userinfo.get("sub")
    if not sub:
        raise ValueError("No sub in userinfo response")
    email = userinfo.get("email") or ""
    return {"sub": str(sub), "email": str(email)}


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    with httpx.Client() as client:
        token_resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_resp.raise_for_status()
        return token_resp.json()


async def refresh_access_token_async(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_resp.raise_for_status()
        return token_resp.json()


def revoke_token(token: str) -> None:
    """Best-effort revoke (refresh or access token). Failures are ignored by callers."""
    try:
        with httpx.Client() as client:
            resp = client.post(
                GOOGLE_REVOKE_URL,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        return
