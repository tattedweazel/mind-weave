"""Encrypt user api_keys values at rest (SE-023); Fernet key derived from SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logging import logger

_PREFIX = "v1."

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        _fernet = Fernet(key)
    return _fernet


def encrypt_api_keys_store(raw: dict[str, Any]) -> dict[str, Any]:
    """Encrypt non-empty string values for JSON storage."""
    if not raw:
        return {}
    f = _get_fernet()
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None or v == "":
            out[k] = v
        elif isinstance(v, str):
            out[k] = _PREFIX + f.encrypt(v.encode("utf-8")).decode("ascii")
        else:
            raise ValueError(f"api_keys.{k} must be a string or empty")
    return out


def decrypt_api_keys_store(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt values written by encrypt_api_keys_store; pass through legacy plaintext."""
    if not stored:
        return {}
    f = _get_fernet()
    out: dict[str, Any] = {}
    for k, v in stored.items():
        if v is None or v == "":
            out[k] = v
        elif isinstance(v, str) and v.startswith(_PREFIX):
            try:
                out[k] = f.decrypt(v[len(_PREFIX) :].encode("ascii")).decode("utf-8")
            except InvalidToken:
                # Never pass ciphertext through as a secret (LM Studio returns 401 on bogus Bearer).
                logger.warning(
                    "api_keys.%s: decrypt failed (wrong SECRET_KEY, corrupted row, or truncated paste). "
                    "Omitting; re-save the key in My Settings or set LMSTUDIO_API_KEY on the server.",
                    k,
                )
        else:
            out[k] = v
    return out


_SENSITIVE_PREFIX = "v1s."


def encrypt_sensitive_at_rest(plain: str) -> str:
    """Encrypt a single secret for DB storage (OAuth tokens). Same Fernet key as api_keys."""
    if not plain:
        return plain
    f = _get_fernet()
    return _SENSITIVE_PREFIX + f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_sensitive_at_rest(stored: str) -> str:
    """Decrypt value from encrypt_sensitive_at_rest; pass through if not prefixed."""
    if not stored:
        return stored
    if not stored.startswith(_SENSITIVE_PREFIX):
        return stored
    f = _get_fernet()
    try:
        return f.decrypt(stored[len(_SENSITIVE_PREFIX) :].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return stored
