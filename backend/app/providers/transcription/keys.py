"""API-key resolution for transcription providers.

Mirrors :func:`app.providers.lmstudio_http.resolve_lmstudio_bearer` so users entering a
key in **My Settings → API Settings** take precedence over the deployment-wide env
fallback. The encrypted store is read by callers via
:func:`app.core.user_api_keys_crypto.decrypt_api_keys_store`; this module only does the
key-name lookup + secret-string sanitation.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings
from app.providers.lmstudio_http import normalize_bearer_secret_value


def resolve_assemblyai_api_key(decrypted_api_keys: Optional[dict[str, Any]]) -> Optional[str]:
    """Return the AssemblyAI API key for the calling user.

    Resolution order (matches LM Studio):

    1. ``decrypted_api_keys["assemblyai"]`` — user-entered key from My Settings.
    2. ``settings.ASSEMBLYAI_API_KEY`` — deployment-wide env fallback.
    3. ``None`` — caller treats as missing-credential and surfaces a structured error.

    The literal ``[stored]`` placeholder (returned by masked GET responses) is treated as
    "no key" so an older client persisting the masked GET value can never accidentally
    send it as a real Bearer token.
    """

    if decrypted_api_keys:
        v = decrypted_api_keys.get("assemblyai")
        if isinstance(v, str) and v.strip():
            t = normalize_bearer_secret_value(v)
            if t == "[stored]":
                t = ""
            if t:
                return t

    env = settings.ASSEMBLYAI_API_KEY
    if isinstance(env, str) and env.strip():
        return normalize_bearer_secret_value(env)

    return None
