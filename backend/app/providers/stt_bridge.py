"""HTTP client for the local STT bridge (services/stt-bridge)."""

from __future__ import annotations

import io
import json
from typing import Any, Optional

import httpx

from app.core.config import settings


class SttBridgeError(Exception):
    """Raised when the STT bridge returns an error or is unreachable."""


def _headers() -> dict[str, str]:
    tok = (settings.STT_BRIDGE_TOKEN or "").strip()
    if tok:
        return {"X-STT-Bridge-Token": tok}
    return {}


async def transcribe_audio_bytes(
    data: bytes,
    *,
    task: str = "transcribe",
    language: Optional[str] = None,
    filename: str = "audio.webm",
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """POST /v1/transcribe (multipart) and return the JSON body."""
    base = settings.STT_BRIDGE_URL.rstrip("/")
    url = f"{base}/v1/transcribe"
    t = (task or "transcribe").strip().lower()
    if t not in ("transcribe", "translate"):
        t = "transcribe"
    form: dict[str, Any] = {"task": t}
    if language and str(language).strip():
        form["language"] = str(language).strip()
    try:
        async with httpx.AsyncClient(timeout=settings.STT_BRIDGE_TIMEOUT) as client:
            r = await client.post(
                url,
                data=form,
                files={"file": (filename, io.BytesIO(data), content_type)},
                headers=_headers(),
            )
    except httpx.RequestError as e:
        raise SttBridgeError(f"STT bridge unreachable: {e}") from e
    if r.status_code >= 400:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = str(body["detail"])
        except Exception:
            detail = (r.text or "")[:500]
        raise SttBridgeError(f"STT bridge failed ({r.status_code}): {detail or r.reason_phrase}")
    try:
        return r.json()  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        raise SttBridgeError("STT bridge returned non-JSON body") from e
