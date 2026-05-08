"""Gmail message dict → compact string for Simple LLM user prompts (headers + plain body only)."""

from __future__ import annotations

import json
from typing import Any

from app.core.text_noise import NoiseFilterConfig, filter_text_noise

# LLM-prompt-time slimmer. Bodies have already been noise-filtered by the Gmail extraction
# step; here we only strip stray invisible characters and tidy whitespace without imposing a
# second character cap (the wire-shape cap already applies upstream).
_LLM_PROMPT_NOISE_FILTER = NoiseFilterConfig(
    strip_invisible_unicode=True,
    drop_html_style_and_script=True,
    collapse_whitespace=True,
    strip_repeated_separators=False,
    shorten_long_urls=False,
    strip_quoted_reply_chains=False,
    strip_marketing_footers=False,
    max_chars=None,
)


def strip_invisible_email_text_for_llm(text: str) -> str:
    """
    Remove invisible / format noise common in HTML-derived email (zero-width spaces, bidi
    overrides, soft hyphens, etc.) before sending to a model. Delegates to the shared
    ``filter_text_noise`` so this module and Gmail extraction stay in lockstep.
    """
    if not text:
        return text
    filtered, _ = filter_text_noise(text, _LLM_PROMPT_NOISE_FILTER)
    return filtered


def _clean_slim_string(s: str) -> str:
    """Trim outer whitespace then strip invisible/format characters."""
    return strip_invisible_email_text_for_llm(s.strip())


def is_gmail_like_message_dict(d: Any) -> bool:
    """
    True if ``d`` looks like a workflow-facing Gmail message dict (curated list item or Gmail primitive).
    Used to choose a compact string form for LLM user prompts without dropping full dicts elsewhere.
    """
    if not isinstance(d, dict) or not d:
        return False
    if isinstance(d.get("id"), str) and d.get("id").strip() and isinstance(d.get("threadId"), str):
        return True
    if any(k in d for k in ("body_text", "snippet")) and any(k in d for k in ("from", "subject", "to")):
        return True
    return False


def slim_gmail_dict_for_llm_prompt(d: dict[str, Any]) -> dict[str, Any]:
    """
    Headers + plain body only for LLM prompts. Omits labelIds, internalDate, fetch_error, body_truncated,
    and snippet when body_text is present. Curated wire shape never includes raw HTML in body_text.
    """
    out: dict[str, Any] = {}
    for k in ("id", "threadId", "subject", "from", "to", "date"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = _clean_slim_string(v)
        elif v is not None and not isinstance(v, str):
            out[k] = v
    body = d.get("body_text")
    if isinstance(body, str) and body.strip():
        out["body_text"] = _clean_slim_string(body)
    elif isinstance(d.get("snippet"), str) and str(d.get("snippet")).strip():
        out["snippet"] = _clean_slim_string(str(d.get("snippet")))
    return out


def format_gmail_message_dict_for_llm_prompt(d: dict[str, Any]) -> str:
    """Stable string for Simple LLM user messages: compact JSON of the slim Gmail fields."""
    slim = slim_gmail_dict_for_llm_prompt(d)
    return json.dumps(slim, indent=2, ensure_ascii=False)
