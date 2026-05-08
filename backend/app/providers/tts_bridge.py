"""HTTP client for the vendor-neutral TTS bridge (services/tts-bridge)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class TtsBridgeError(Exception):
    """Raised when the bridge returns an error or unreachable."""


def _bridge_headers() -> dict[str, str]:
    tok = (settings.TTS_BRIDGE_TOKEN or "").strip()
    if tok:
        return {"X-TTS-Bridge-Token": tok}
    return {}


async def pull_model(engine: str, artifact_id: str, source: dict[str, Any]) -> str:
    """POST /v1/models/pull — returns local_key from the bridge."""
    base = settings.TTS_BRIDGE_URL.rstrip("/")
    url = f"{base}/v1/models/pull"
    try:
        async with httpx.AsyncClient(timeout=settings.TTS_BRIDGE_PULL_TIMEOUT) as client:
            r = await client.post(
                url,
                json={"engine": engine, "artifact_id": artifact_id, "source": source},
                headers={**_bridge_headers(), "Content-Type": "application/json"},
            )
    except httpx.RequestError as e:
        raise TtsBridgeError(f"TTS bridge unreachable: {e}") from e
    if r.status_code >= 400:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = str(body["detail"])
        except Exception:
            detail = (r.text or "")[:500]
        raise TtsBridgeError(f"TTS bridge pull failed ({r.status_code}): {detail or r.reason_phrase}")
    data = r.json()
    key = data.get("local_key") if isinstance(data, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise TtsBridgeError("TTS bridge pull returned no local_key")
    return key.strip()


async def synthesize_wav(engine: str, model_local_key: str, text: str, options: dict[str, Any] | None = None) -> bytes:
    """POST /v1/tts — raw audio/wav bytes."""
    base = settings.TTS_BRIDGE_URL.rstrip("/")
    url = f"{base}/v1/tts"
    payload = {
        "engine": engine,
        "model_local_key": model_local_key,
        "text": text,
        "options": options or {},
        "response_format": "wav",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.TTS_BRIDGE_SYNTH_TIMEOUT) as client:
            r = await client.post(
                url,
                json=payload,
                headers={**_bridge_headers(), "Content-Type": "application/json"},
            )
    except httpx.RequestError as e:
        raise TtsBridgeError(f"TTS bridge unreachable: {e}") from e
    if r.status_code >= 400:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict) and body.get("detail"):
                detail = str(body["detail"])
        except Exception:
            detail = (r.text or "")[:500]
        raise TtsBridgeError(f"TTS bridge synthesize failed ({r.status_code}): {detail or r.reason_phrase}")
    data = r.content
    cap = max(1024, int(settings.TTS_BRIDGE_MAX_AUDIO_BYTES))
    if len(data) > cap:
        raise TtsBridgeError(f"TTS audio exceeds configured cap ({len(data)} > {cap})")
    return data
