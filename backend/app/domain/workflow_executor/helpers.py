"""Small pure helpers for workflow graph execution."""

import json
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple, Union

from app.domain.schemas.graph_nodes import (
    AudioFileInputSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
)


def pop_wave_batch(ready: deque[str], order_index: dict[str, int], cap: int) -> list[str]:
    """
    Take up to `cap` node ids from `ready`, ordered by `order_index`, leaving the rest on `ready`.
    """
    if not ready:
        return []
    items = sorted(ready, key=lambda n: order_index.get(n, 0))
    take = min(len(items), cap)
    batch = items[:take]
    remainder = items[take:]
    ready.clear()
    ready.extend(remainder)
    return batch


_AUDIO_STEP_TYPES: tuple[type, ...] = (
    TranscribeAudioSkillNode,
    AudioFileInputSkillNode,
    TranscribeFileSkillNode,
)


def split_batch_isolating_audio_steps(
    batch: list[str], ready: deque[str], order_index: dict[str, int], nodes_by_id: dict[str, Any]
) -> list[str]:
    """
    If the batch includes a run-time audio input/transcription node, run only the first
    such node this wave and re-queue the rest (so one browser upload UI is shown at a
    time, and each `transcription_jobs` row is created in a stable order).
    """
    tr = [n for n in batch if isinstance(nodes_by_id.get(n), _AUDIO_STEP_TYPES)]
    if not tr:
        return batch
    chosen = tr[0]
    rest = [n for n in batch if n != chosen]
    for n in sorted(rest, key=lambda x: order_index.get(x, 0)):
        ready.append(n)
    return [chosen]


# Backwards-compatible alias (older imports may still reference this name).
split_batch_isolating_transcribe_audio = split_batch_isolating_audio_steps


def _format_exception(e: BaseException) -> str:
    """Format exception for user display. Handles empty str(e) (e.g. httpx.ConnectError)."""
    msg = str(e).strip()
    if not msg:
        return f"{type(e).__name__} (no details available)"
    return f"{type(e).__name__}: {msg}"


def _condition_to_bool(val: Any) -> bool:
    """Convert a value to bool for Basic Conditional. None/empty/false/no/0 -> False; true/yes/1 or non-empty -> True."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("false", "no", "0"):
        return False
    if s in ("true", "yes", "1"):
        return True
    return len(s) > 0


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two values for equality. Handles JSON strings from upstream."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        a_val = json.loads(a) if isinstance(a, str) else a
        b_val = json.loads(b) if isinstance(b, str) else b
        return bool(a_val == b_val)
    except (json.JSONDecodeError, TypeError):
        return bool(a == b)


def _to_comparable(a: Any, b: Any) -> tuple[Any, Any]:
    """Convert a and b to comparable types (int or float). Falls back to string comparison."""
    if a is None:
        a = 0
    if b is None:
        b = 0
    try:
        a_num = float(a) if isinstance(a, (int, float)) else float(json.loads(a) if isinstance(a, str) else a)
        b_num = float(b) if isinstance(b, (int, float)) else float(json.loads(b) if isinstance(b, str) else b)
        return a_num, b_num
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return str(a), str(b)


def parse_strict_int_for_slot(raw: Any, slot_label: str) -> Union[Tuple[int, None], Tuple[None, str]]:
    """
    Parse a resolved workflow input to int. Returns (value, None) or (None, error_message).
    Rejects bool (subclass of int in Python) so true/false are not coerced to 0/1.
    """
    if raw is None:
        return None, f"{slot_label} is required"
    if isinstance(raw, bool):
        return None, f"{slot_label} must be an integer (got boolean)"
    if isinstance(raw, int):
        return raw, None
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw), None
        return None, f"{slot_label} must be an integer"
    s = str(raw).strip()
    if s == "":
        return None, f"{slot_label} is required"
    try:
        return int(s), None
    except (ValueError, TypeError):
        return None, f"{slot_label} must be a valid integer"


def parse_rfc3339_datetime_string(raw: Any) -> Optional[str]:
    """
    Validate a workflow datetime (RFC3339 instant). Returns normalized ISO string with Z for UTC,
    or None if empty or unparseable.
    """
    if raw is None:
        return None
    t = str(raw).strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


def utc_now_for_workflow_execution() -> datetime:
    """Return current UTC instant for DateTime ``use_now`` (patch in tests; avoids mutating ``datetime.now`` on Py3.14+)."""
    return datetime.now(timezone.utc)


def utc_now_rfc3339_normalized_for_executor() -> str:
    """
    Current UTC instant normalized like ``parse_rfc3339_datetime_string`` (Z suffix for UTC).

    Falls back to a coarse RFC3339 string if ``datetime.isoformat()`` is not accepted by the parser
    (defensive; should not happen for stdlib datetimes).
    """
    dt = utc_now_for_workflow_execution()
    parsed = parse_rfc3339_datetime_string(dt.isoformat())
    if parsed is not None:
        return parsed
    u = dt.astimezone(timezone.utc) if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    coarse = u.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    parsed2 = parse_rfc3339_datetime_string(coarse)
    if parsed2 is not None:
        return parsed2
    raise RuntimeError("DateTime use_now: failed to normalize current UTC time")


def shift_rfc3339_instant_by_days(norm: str, days: int) -> Optional[str]:
    """
    Shift a normalized RFC3339 instant (from parse_rfc3339_datetime_string) by ``days``
    using timezone-aware UTC arithmetic (``timedelta(days=...)``).
    """
    t = norm
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc) + timedelta(days=int(days))
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso
