"""Build Gmail API `q` strings from structured workflow inputs (users.messages.list)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Slugs allowed in `category:` / `-category:` for inbox tabs (Gmail search operators).
# See https://support.google.com/mail/answer/7190 — excludes `primary`, which is handled via inbox focus.
GMAIL_EXCLUDABLE_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {"promotions", "social", "updates", "forums", "reservations", "purchases"}
)

GMAIL_INBOX_FOCUS_MODES: frozenset[str] = frozenset({"off", "primary"})


def normalize_gmail_inbox_focus(raw: Any) -> str:
    """Return `off` or `primary`; invalid or missing → `off`."""
    if raw is None:
        return "off"
    s = str(raw).strip().lower()
    return s if s in GMAIL_INBOX_FOCUS_MODES else "off"


def normalize_gmail_exclude_categories(raw: Any) -> list[str]:
    """Deduplicate and keep only documented excludable slugs; preserves stable order."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = item.strip().lower()
        if slug in GMAIL_EXCLUDABLE_CATEGORY_SLUGS and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def append_category_q_clauses(
    base_q: Optional[str],
    *,
    inbox_focus: str,
    exclude_categories: list[str],
) -> Optional[str]:
    """
    Append `category:primary` or `-category:…` fragments after structured `q` composition.

    When `inbox_focus` is `primary`, only `category:primary` is added (excludes are ignored
    — primary focus already narrows to the Primary tab).
    """
    focus = normalize_gmail_inbox_focus(inbox_focus)
    parts: list[str] = []
    if base_q is not None and str(base_q).strip():
        parts.append(str(base_q).strip())
    if focus == "primary":
        parts.append("category:primary")
    else:
        for slug in normalize_gmail_exclude_categories(exclude_categories):
            parts.append(f"-category:{slug}")
    if not parts:
        return None
    return " ".join(parts)


def coerce_bool_unread(val: Any) -> bool:
    """Interpret workflow/boolean primitive values as bool."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "", "no", "off"):
        return False
    return False


def rfc3339_to_gmail_date(s: str, *, calendar_zone: Optional[str] = None) -> str:
    """
    Convert an RFC3339 instant to YYYY/MM/DD for Gmail after:/before: operators (date-only).

    When ``calendar_zone`` is set (IANA), uses the **calendar day in that zone** at this instant,
    matching the workflow editor **Time & limits** timezone. When missing or invalid, falls back
    to the calendar day in **UTC** (legacy behavior). See WORKFLOW_SKILLS.md for Gmail UI caveats.
    """
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    z = str(calendar_zone).strip() if calendar_zone else ""
    if z:
        try:
            local = dt.astimezone(ZoneInfo(z))
            return f"{local.year}/{local.month:02d}/{local.day:02d}"
        except Exception:
            pass
    dt_utc = dt.astimezone(timezone.utc)
    return f"{dt_utc.year}/{dt_utc.month:02d}/{dt_utc.day:02d}"


def build_messages_list_q(
    *,
    raw_query: Optional[str],
    after_rfc3339: Optional[str],
    before_rfc3339: Optional[str],
    unread_only: bool,
    gmail_list_calendar_zone: Optional[str] = None,
) -> Optional[str]:
    """
    Compose Gmail search `q` from optional structured filters and raw query.
    Clauses are space-joined (implicit AND). Returns None if no constraints.
    """
    parts: list[str] = []
    if unread_only:
        parts.append("is:unread")
    after_s = str(after_rfc3339).strip() if after_rfc3339 else ""
    if after_s:
        parts.append(f"after:{rfc3339_to_gmail_date(after_s, calendar_zone=gmail_list_calendar_zone)}")
    before_s = str(before_rfc3339).strip() if before_rfc3339 else ""
    if before_s:
        parts.append(f"before:{rfc3339_to_gmail_date(before_s, calendar_zone=gmail_list_calendar_zone)}")
    rq = str(raw_query).strip() if raw_query else ""
    if rq:
        parts.append(rq)
    if not parts:
        return None
    return " ".join(parts)
