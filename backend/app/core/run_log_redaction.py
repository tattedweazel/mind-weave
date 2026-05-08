"""Redact prompt-like fields in workflow run logs (SE-016) — shared by API and persistence."""

from __future__ import annotations

import re
from typing import Any

_URL_IN_ERROR_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def _is_sensitive_detail_key(key: str) -> bool:
    kl = key.lower()
    if "prompt" in kl or kl in ("additional_context", "user_role_message"):
        return True
    # Gmail/Calendar workflow outputs (and similar) — avoid persisting titles, bodies, etc.
    if kl in (
        "summary",
        "description",
        "snippet",
        "subject",
        "location",
        "html",
        "body",
        "payload",
        "raw",
        "attendees",
        "organizer",
        "audio_base64",
        "wav_base64",
    ):
        return True
    return False


def redact_error_for_api(error: str | None) -> str | None:
    """Redact URL-like substrings from persisted node error messages (SE-030)."""
    if error is None:
        return None
    return _URL_IN_ERROR_RE.sub("[url]", error)


def redact_prompt_like(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: "[redacted]" if _is_sensitive_detail_key(k) else redact_prompt_like(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_prompt_like(x) for x in obj[:200]]
    return obj


def redact_node_log_for_storage(
    output_data: dict[str, Any] | None,
    details: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return copies safe to persist at rest (no raw prompts in details/output_metadata)."""
    out = redact_prompt_like(output_data) if output_data is not None else None
    det_raw: dict[str, Any] = dict(details) if details is not None else {}
    det = redact_prompt_like(det_raw)
    return out, det
