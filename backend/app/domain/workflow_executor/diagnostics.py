"""Repeatable patterns for skill run details: vendor diagnostics (Explorer-only, not for graph edges)."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
from typing import Any

from app.core.text_noise import (
    EMAIL_BODY_NOISE_FILTER,
    EMAIL_HEADER_NOISE_FILTER,
    filter_text_noise,
    html_to_plain_text,
)

# Stream / DB size guard for Calendar events.list (items array).
GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS = 100

# Gmail users.messages.list — messages array in diagnostic payload.
GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS = 100

# Max characters per message for workflow output body_text (after decode + HTML strip + noise filter).
# Sourced from EMAIL_BODY_NOISE_FILTER so tuning lives in app/core/text_noise.py.
GMAIL_MESSAGE_BODY_MAX_CHARS = EMAIL_BODY_NOISE_FILTER.max_chars or 0

SKILL_DIAGNOSTICS_KEY = "skill_diagnostics"


def merge_skill_diagnostics(
    details: dict[str, Any],
    *,
    vendor_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Attach integration payload under details['skill_diagnostics'][vendor_key]."""
    out = deepcopy(details)
    sd = dict(out.get(SKILL_DIAGNOSTICS_KEY) or {})
    sd[vendor_key] = payload
    out[SKILL_DIAGNOSTICS_KEY] = sd
    return out


def truncate_google_calendar_events_list_response(
    raw: dict[str, Any],
    *,
    max_items: int = GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS,
) -> tuple[dict[str, Any], bool, int]:
    """
    Return a shallow-safe copy of the list response with items capped.
    Returns (truncated_response, truncated, omitted_event_count).
    """
    data = deepcopy(raw)
    items = data.get("items")
    if not isinstance(items, list):
        return data, False, 0
    n = len(items)
    if n <= max_items:
        return data, False, 0
    data["items"] = items[:max_items]
    return data, True, n - max_items


def truncate_gmail_messages_list_response(
    raw: dict[str, Any],
    *,
    max_messages: int = GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS,
) -> tuple[dict[str, Any], bool, int]:
    """Cap messages[] for skill_diagnostics payload. Returns (copy, truncated, omitted_count)."""
    data = deepcopy(raw)
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        return data, False, 0
    n = len(msgs)
    if n <= max_messages:
        return data, False, 0
    data["messages"] = msgs[:max_messages]
    return data, True, n - max_messages


def _decode_gmail_body_b64(data: Any) -> str:
    if not data or not isinstance(data, str):
        return ""
    s = data.strip()
    pad = "=" * (-len(s) % 4)
    try:
        raw = base64.urlsafe_b64decode(s + pad)
        return raw.decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _gmail_leaf_mime_parts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect leaf MIME parts (those with a body, or non-multipart single part)."""
    acc: list[dict[str, Any]] = []

    def visit(part: dict[str, Any] | None) -> None:
        if not part or not isinstance(part, dict):
            return
        kids = part.get("parts")
        if isinstance(kids, list) and len(kids) > 0:
            for c in kids:
                if isinstance(c, dict):
                    visit(c)
        else:
            acc.append(part)

    if payload and isinstance(payload, dict):
        visit(payload)
    return acc


def _header_map_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return {}
    raw: dict[str, str] = {}
    for h in headers:
        if not isinstance(h, dict):
            continue
        name = h.get("name")
        if not isinstance(name, str):
            continue
        raw[name.strip().lower()] = str(h.get("value") if h.get("value") is not None else "")
    return raw


def _pick_plain_and_html_bodies(payload: dict[str, Any]) -> tuple[str, str]:
    plain_chunks: list[str] = []
    html_chunks: list[str] = []
    for p in _gmail_leaf_mime_parts(payload):
        mt = str(p.get("mimeType") or "").lower()
        body_holder = p.get("body")
        b = body_holder if isinstance(body_holder, dict) else {}
        decoded = _decode_gmail_body_b64(b.get("data"))
        if not decoded:
            continue
        if mt == "text/plain":
            plain_chunks.append(decoded)
        elif mt == "text/html":
            html_chunks.append(decoded)
    plain = "\n\n".join(plain_chunks).strip()
    html = "\n\n".join(html_chunks).strip()
    return plain, html


def _clean_header(value: str) -> str:
    """Run a short header-style string through ``EMAIL_HEADER_NOISE_FILTER`` (invisible-char + entity cleanup)."""
    cleaned, _ = filter_text_noise(value, EMAIL_HEADER_NOISE_FILTER)
    return cleaned


def curated_gmail_message_from_full_api(
    msg: dict[str, Any],
    *,
    max_body_chars: int = GMAIL_MESSAGE_BODY_MAX_CHARS,
) -> dict[str, Any]:
    """
    Stable workflow-facing dict from users.messages.get format=full.
    Omits raw payload; includes body_text (plain preferred, else HTML stripped to text) with optional body_truncated.
    Never includes raw HTML in the wire shape.
    """
    row: dict[str, Any] = {}
    mid = msg.get("id")
    if mid is not None:
        row["id"] = mid
    tid = msg.get("threadId")
    if tid is not None:
        row["threadId"] = tid
    internal = msg.get("internalDate")
    if isinstance(internal, str) and internal:
        row["internalDate"] = internal
    snip = msg.get("snippet")
    if isinstance(snip, str) and snip:
        cleaned_snip = _clean_header(snip)
        if cleaned_snip:
            row["snippet"] = cleaned_snip
    labels = msg.get("labelIds")
    if isinstance(labels, list) and labels:
        row["labelIds"] = [str(x) for x in labels if x is not None]

    payload_any = msg.get("payload")
    payload = payload_any if isinstance(payload_any, dict) else {}

    hmap = _header_map_from_payload(payload)
    for hk, outk in (
        ("subject", "subject"),
        ("from", "from"),
        ("to", "to"),
        ("date", "date"),
    ):
        v = hmap.get(hk)
        if isinstance(v, str) and v.strip():
            cleaned_header = _clean_header(v)
            if cleaned_header:
                row[outk] = cleaned_header

    body_config = (
        EMAIL_BODY_NOISE_FILTER
        if max_body_chars == EMAIL_BODY_NOISE_FILTER.max_chars
        else replace(EMAIL_BODY_NOISE_FILTER, max_chars=max_body_chars)
    )
    # Pass an uncapped config to html_to_plain_text so we don't lose the truncation signal
    # to the inner filter_text_noise call; final cap is applied below in one place.
    html_extract_config = replace(body_config, max_chars=None)
    plain, html = _pick_plain_and_html_bodies(payload)
    if plain:
        body_text, truncated = filter_text_noise(plain, body_config)
    elif html:
        body_text, truncated = filter_text_noise(
            html_to_plain_text(html, html_extract_config),
            body_config,
        )
    else:
        body_text, truncated = "", False
    if body_text:
        row["body_text"] = body_text
    if truncated:
        row["body_truncated"] = True

    return row


def curated_gmail_messages_list_item(ref: dict[str, Any]) -> dict[str, Any]:
    """
    Stable, workflow-facing subset of an entry in users.messages.list `messages[]`.
    The list endpoint only returns id, threadId, and sometimes internalDate.
    """
    row: dict[str, Any] = {
        "id": ref.get("id"),
        "threadId": ref.get("threadId"),
    }
    internal = ref.get("internalDate")
    if isinstance(internal, str) and internal:
        row["internalDate"] = internal
    return {k: v for k, v in row.items() if v is not None}


def curated_google_calendar_event(event: dict[str, Any]) -> dict[str, Any]:
    """Stable, workflow-facing subset of a Calendar API Event resource."""
    start_ev = event.get("start")
    start: dict[str, Any] = start_ev if isinstance(start_ev, dict) else {}
    end_ev = event.get("end")
    end: dict[str, Any] = end_ev if isinstance(end_ev, dict) else {}
    row: dict[str, Any] = {
        "id": event.get("id"),
        "status": event.get("status"),
        "htmlLink": event.get("htmlLink"),
        "summary": event.get("summary"),
        "location": event.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
    }
    optional_str_keys = (
        "created",
        "updated",
        "iCalUID",
        "recurringEventId",
        "hangoutLink",
        "colorId",
        "visibility",
        "transparency",
    )
    for k in optional_str_keys:
        v = event.get(k)
        if isinstance(v, str) and v:
            row[k] = v
    organizer = event.get("organizer")
    if isinstance(organizer, dict):
        od: dict[str, Any] = {}
        if isinstance(organizer.get("email"), str):
            od["email"] = organizer["email"]
        if isinstance(organizer.get("displayName"), str):
            od["displayName"] = organizer["displayName"]
        if od:
            row["organizer"] = od
    creator = event.get("creator")
    if isinstance(creator, dict):
        cd: dict[str, Any] = {}
        if isinstance(creator.get("email"), str):
            cd["email"] = creator["email"]
        if isinstance(creator.get("displayName"), str):
            cd["displayName"] = creator["displayName"]
        if cd:
            row["creator"] = cd
    recurrence = event.get("recurrence")
    if isinstance(recurrence, list) and recurrence:
        row["recurrence"] = recurrence
    return {k: v for k, v in row.items() if v is not None}
