"""LM Studio HTTP helpers: OpenAI-compat base URL, native origin, Bearer resolution."""

from __future__ import annotations

from typing import Any

from app.core.config import settings


def normalize_openai_base_url(base: str) -> str:
    """Strip trailing slashes from LMSTUDIO_BASE_URL (e.g. .../v1)."""
    return base.rstrip("/")


def lmstudio_origin_from_openai_base(openai_base: str) -> str:
    """http://127.0.0.1:1234/v1 -> http://127.0.0.1:1234 for native /api/v1/* routes."""
    b = normalize_openai_base_url(openai_base)
    if b.endswith("/v1"):
        return b[:-3]
    return b


def lmstudio_origin() -> str:
    """Native REST origin derived from settings.LMSTUDIO_BASE_URL."""
    return lmstudio_origin_from_openai_base(settings.LMSTUDIO_BASE_URL)


def normalize_bearer_secret_value(s: str) -> str:
    """Strip BOM and accidental ``Bearer `` prefix(es) from pasted tokens.

    Docs and UIs often show ``Authorization: Bearer <token>``; pasting ``Bearer …`` into My Settings
    would otherwise yield ``Authorization: Bearer Bearer …`` and LM Studio returns **401**.
    """
    t = s.strip().lstrip("\ufeff")
    for _ in range(4):
        low = t.lower()
        if low.startswith("bearer "):
            t = t[7:].strip().lstrip("\ufeff")
            continue
        break
    return t


def resolve_lmstudio_bearer(*, decrypted_api_keys: dict[str, Any] | None) -> str | None:
    """Return Bearer token: user's lmstudio_api_key if set, else LMSTUDIO_API_KEY env.

    Chat and workflow LLM calls pass decrypted **User.api_keys**. **`GET /api/v1/models/`** passes
    ``decrypted_api_keys=None`` so listing uses **LMSTUDIO_API_KEY** only (shared picker catalog).
    """
    if decrypted_api_keys:
        v = decrypted_api_keys.get("lmstudio_api_key")
        if isinstance(v, str) and v.strip():
            t = normalize_bearer_secret_value(v)
            # Never use literal "[stored]" — can happen if an older client saved the masked GET value.
            if t == "[stored]":
                t = ""
            if t:
                return t
    env = settings.LMSTUDIO_API_KEY
    if isinstance(env, str) and env.strip():
        return normalize_bearer_secret_value(env)
    return None


def bearer_auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
