#!/usr/bin/env python3
"""
Load a user from ``DATABASE_URL``, decrypt ``api_keys``, print ``lmstudio_api_key``, and optionally
probe LM Studio (``GET {LMSTUDIO_BASE_URL}/models``).

**Local debugging only.** ``chdir`` to ``backend/`` before importing ``app`` so ``.env`` and SQLite
match ``uvicorn``.

Examples::

  cd backend && uv run python scripts/inspect_user_lmstudio_key.py --username Dave
  cd backend && uv run python scripts/inspect_user_lmstudio_key.py --username Dave --compare-to 'YOUR_TOKEN'
  cd backend && uv run python scripts/inspect_user_lmstudio_key.py --username Dave --probe-lm-studio
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

import httpx
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import settings
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.persistence.db import engine
from app.persistence.tables import User
from app.providers.lmstudio_http import (
    bearer_auth_headers,
    normalize_openai_base_url,
    resolve_lmstudio_bearer,
)


def _find_user(session: Session, username: str) -> User | None:
    u = session.exec(select(User).where(User.username == username)).first()
    if u:
        return u
    return session.exec(
        select(User).where(func.lower(User.username) == username.lower())
    ).first()


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect decrypted lmstudio_api_key for a user.")
    p.add_argument("--username", default="Dave", help="User login name (case-insensitive fallback)")
    p.add_argument(
        "--compare-to",
        default=None,
        help="If set, exit 1 when decrypted lmstudio_api_key != this string (after strip).",
    )
    p.add_argument(
        "--probe-lm-studio",
        action="store_true",
        help="GET OpenAI-compat /models with per-user resolve_lmstudio_bearer (same as chat; not GET /api/v1/models/).",
    )
    args = p.parse_args()

    with Session(engine) as session:
        user = _find_user(session, args.username)
        if not user:
            print(f"No user found matching username {args.username!r}", file=sys.stderr)
            return 2

        raw = user.api_keys or {}
        dec = decrypt_api_keys_store(raw)
        lm_plain = dec.get("lmstudio_api_key")
        token = resolve_lmstudio_bearer(decrypted_api_keys=dec)

        print(f"user id: {user.id}")
        print(f"username: {user.username!r}")
        print(f"raw api_keys keys (DB JSON): {sorted(raw.keys())}")
        print(f"decrypted lmstudio_api_key (repr): {lm_plain!r}")
        print(f"resolve_lmstudio_bearer() (repr): {token!r}")
        if args.compare_to is not None:
            expected = args.compare_to.strip()
            if (token or "") != expected:
                print(
                    f"COMPARE FAIL: expected {expected!r} got {token!r}",
                    file=sys.stderr,
                )
                return 1
            print("COMPARE OK: matches --compare-to")

        print(f"LMSTUDIO_BASE_URL: {settings.LMSTUDIO_BASE_URL!r}")
        print(f"LMSTUDIO_API_KEY env set: {bool(settings.LMSTUDIO_API_KEY and settings.LMSTUDIO_API_KEY.strip())}")

        if args.probe_lm_studio:
            if not token:
                print("Cannot probe: no Bearer token (no user key and no LMSTUDIO_API_KEY).", file=sys.stderr)
                return 3
            base = normalize_openai_base_url(settings.LMSTUDIO_BASE_URL)
            url = f"{base}/models"
            headers = bearer_auth_headers(token)
            print(f"GET {url}")
            print(f"Authorization (repr): {headers.get('Authorization')!r}")
            try:
                r = httpx.get(url, headers=headers, timeout=15.0, trust_env=False)
            except httpx.RequestError as e:
                print(f"Request failed: {e}", file=sys.stderr)
                return 4
            print(f"status: {r.status_code}")
            body = r.text
            if len(body) > 800:
                print(body[:800] + "\n... [truncated]")
            else:
                print(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
