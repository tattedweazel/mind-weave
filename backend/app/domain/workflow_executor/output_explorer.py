"""Versioned `details.output_explorer` payloads for GUI-friendly run output (editor / Explorer).

Built from serialized node output using redaction-safe item field names so values align with
persisted run logs after `run_log_redaction`. See docs/OUTPUT_EXPLORER_UI.md.

Legacy API clients may still read `details.skill_explorer` (same shape, deprecated key).
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

OUTPUT_EXPLORER_VERSION = 1
OUTPUT_EXPLORER_MAX_ITEMS = 50
TEASER_MAX_LEN = 180

FORBIDDEN_ITEM_KEYS = frozenset(
    {
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
    }
)


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _truncate_teaser(s: str, max_len: int = TEASER_MAX_LEN) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def extract_dictionary_output_data(output_dump: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return inner `data` for a serialized DictionaryNodeOutput, or None."""
    if not output_dump or not isinstance(output_dump, dict):
        return None
    if output_dump.get("kind") != "dictionary":
        return None
    d = output_dump.get("data")
    return d if isinstance(d, dict) else None


def _json_preview(v: Any, max_len: int = TEASER_MAX_LEN) -> str:
    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except TypeError:
        s = str(v)
    return _truncate_teaser(s, max_len)


def infer_primitive_kind(v: Any) -> str:
    """Coarse JSON-like classification for list rows and dictionary values."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dictionary"
    return "mixed"


def _looks_like_google_calendar_list_events_blob(data: dict[str, Any]) -> bool:
    """True when ``events`` looks like Calendar skill curated rows, not an arbitrary user key."""
    evs = data.get("events")
    if not isinstance(evs, list) or len(evs) == 0:
        return False
    markers = frozenset({"summary", "start", "end", "htmlLink", "status", "iCalUID", "location", "id"})
    for ev in evs:
        if not isinstance(ev, dict):
            continue
        if markers.intersection(ev.keys()):
            return True
        st = ev.get("start")
        en = ev.get("end")
        if isinstance(st, str) and st.strip():
            return True
        if isinstance(en, str) and en.strip():
            return True
    return False


def _looks_like_capture_url_snapshot_blob(data: dict[str, Any]) -> bool:
    """Detect capture_url_snapshot ``output.data`` shape."""
    if isinstance(data.get("error"), dict) and "captured_at" in data:
        return "type" in data["error"]  # type: ignore[operator]
    img = data.get("image")
    if isinstance(img, dict) and "artifact_id" in img:
        return "final_url" in data and "captured_at" in data
    return False


def build_capture_url_snapshot_explorer(data: dict[str, Any]) -> dict[str, Any]:
    """Explorer view for capture_url_snapshot `output.data` (redaction-safe)."""
    err = data.get("error")
    if isinstance(err, dict):
        et = _str(err.get("type")) or "error"
        msg = _str(err.get("message"))
        summary_line = f"Snapshot error · {et}"
        detail = _truncate_teaser(msg) if msg else ""
        return {
            "version": OUTPUT_EXPLORER_VERSION,
            "kind": "capture_url_snapshot",
            "summary": {
                "line": summary_line,
                "detail_lines": [detail] if detail else [],
            },
            "items": [
                {
                    "index": 0,
                    "row_state": "error",
                    "primary_line": et,
                    "secondary_line": "retryable" if err.get("retryable") else "not retryable",
                    "teaser": _truncate_teaser(msg) if msg else "",
                    "badges": [],
                }
            ],
        }

    img = data.get("image") if isinstance(data.get("image"), dict) else {}
    aid = _str(img.get("artifact_id")) if isinstance(img, dict) else ""
    w = img.get("width") if isinstance(img, dict) else None
    h = img.get("height") if isinstance(img, dict) else None
    fu = _str(data.get("final_url"))
    cached = bool(data.get("cached"))
    line = f"PNG {w}×{h} · {fu[:100]}{'…' if len(fu) > 100 else ''}"
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "capture_url_snapshot",
        "summary": {
            "line": line,
            "detail_lines": [
                f"cached: {cached} · duration_ms: {data.get('duration_ms', '')}",
                f"resource: /api/v1/url-snapshot-artifacts/{aid}" if aid else "",
            ],
        },
        "items": [
            {
                "index": 0,
                "row_state": "ok",
                "primary_line": fu or "(url)",
                "secondary_line": f"artifact {aid[:8]}…" if len(aid) > 8 else f"artifact {aid}",
                "teaser": "",
                "badges": ["cached"] if cached else [],
            }
        ],
    }


def _looks_like_fetch_url_blob(data: dict[str, Any]) -> bool:
    """Distinguish fetch_url output from other dictionary steps."""
    if isinstance(data.get("error"), dict) and "fetched_at" in data:
        return "type" in data["error"]  # type: ignore[operator]
    return (
        "status_code" in data
        and "final_url" in data
        and "fetched_at" in data
        and "duration_ms" in data
        and "cached" in data
    )


def build_fetch_url_explorer(data: dict[str, Any]) -> dict[str, Any]:
    """Explorer view for fetch_url `output.data` (redaction-safe)."""
    err = data.get("error")
    if isinstance(err, dict):
        et = _str(err.get("type")) or "error"
        msg = _str(err.get("message"))
        summary_line = f"Fetch error · {et}"
        detail = _truncate_teaser(msg) if msg else ""
        return {
            "version": OUTPUT_EXPLORER_VERSION,
            "kind": "fetch_url",
            "summary": {
                "line": summary_line,
                "detail_lines": [detail] if detail else [],
            },
            "items": [
                {
                    "index": 0,
                    "row_state": "error",
                    "primary_line": et,
                    "secondary_line": "retryable" if err.get("retryable") else "not retryable",
                    "teaser": _truncate_teaser(msg) if msg else "",
                    "badges": [],
                }
            ],
        }

    sc = data.get("status_code")
    fu = _str(data.get("final_url"))
    cached = bool(data.get("cached"))
    line = f"HTTP {sc} · {fu[:120]}{'…' if len(fu) > 120 else ''}"
    body_preview = _str(data.get("body"))
    teaser = _truncate_teaser(body_preview) if body_preview else ""
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "fetch_url",
        "summary": {
            "line": line,
            "detail_lines": [f"cached: {cached} · duration_ms: {data.get('duration_ms', '')}"],
        },
        "items": [
            {
                "index": 0,
                "row_state": "ok",
                "primary_line": fu or "(url)",
                "secondary_line": f"status {sc}",
                "teaser": teaser,
                "badges": ["cached"] if cached else [],
            }
        ],
    }


def try_builtin_dictionary_explorer(data: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch on workflow-facing dictionary shape (Gmail / Calendar / fetch_url / capture_url_snapshot)."""
    if _looks_like_capture_url_snapshot_blob(data):
        return build_capture_url_snapshot_explorer(data)
    if _looks_like_fetch_url_blob(data):
        return build_fetch_url_explorer(data)
    if isinstance(data.get("messages"), list) and "resultSizeEstimate" in data:
        return build_gmail_list_explorer(data)
    if _looks_like_google_calendar_list_events_blob(data):
        return build_calendar_list_explorer(data)
    if _looks_like_google_docs_get_document_blob(data):
        return build_google_docs_get_document_explorer(data)
    return None


def _looks_like_google_docs_get_document_blob(data: dict[str, Any]) -> bool:
    payload = data.get("document_payload")
    if isinstance(payload, dict) and isinstance(payload.get("tabs"), list):
        return True
    return isinstance(data.get("tabs"), list) and "document_id" in data


def build_google_docs_get_document_explorer(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("document_payload")
    if not isinstance(payload, dict):
        payload = data
    title = _str(payload.get("title")) or "(Untitled document)"
    tab_count = payload.get("tab_count")
    image_count = payload.get("image_count")
    detail_lines: list[str] = []
    if tab_count is not None:
        detail_lines.append(f"Tabs: {tab_count}")
    if image_count is not None:
        detail_lines.append(f"Images fetched: {image_count}")
    err_n = len(payload.get("fetch_errors") or []) if isinstance(payload.get("fetch_errors"), list) else 0
    if err_n:
        detail_lines.append(f"Image fetch errors: {err_n}")
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "google_docs_get_document",
        "summary": {"line": title, "detail_lines": detail_lines},
        "items": [],
    }


def _looks_like_google_docs_chunk_list(arr: list[Any]) -> bool:
    if not arr or not all(isinstance(x, dict) for x in arr):
        return False
    for row in arr[:5]:
        if row.get("chunk_id") and row.get("kind") in ("text", "table", "image"):
            return True
    return False


def build_google_docs_parse_document_explorer(chunks: list[Any]) -> dict[str, Any]:
    if not isinstance(chunks, list):
        chunks = []
    by_kind: dict[str, int] = {}
    for c in chunks:
        if isinstance(c, dict):
            k = _str(c.get("kind"))
            if k:
                by_kind[k] = by_kind.get(k, 0) + 1
    detail = ", ".join(f"{k}: {v}" for k, v in sorted(by_kind.items())) if by_kind else ""
    items: list[dict[str, Any]] = []
    overflow = max(0, len(chunks) - OUTPUT_EXPLORER_MAX_ITEMS)
    for idx, c in enumerate(chunks[:OUTPUT_EXPLORER_MAX_ITEMS]):
        if not isinstance(c, dict):
            continue
        kind = _str(c.get("kind")) or "chunk"
        path = c.get("tab_path")
        path_s = " / ".join(str(p) for p in path) if isinstance(path, list) else ""
        primary = f"{kind}" + (f" · {path_s}" if path_s else "")
        teaser = ""
        if kind == "text":
            teaser = _truncate_teaser(_str(c.get("text")))
        elif kind == "table":
            rows = c.get("table", {}).get("rows") if isinstance(c.get("table"), dict) else []
            teaser = f"{len(rows)} row(s)" if isinstance(rows, list) else ""
        items.append(
            {
                "index": idx,
                "row_state": "ok",
                "primary_line": primary,
                "secondary_line": _str(c.get("chunk_id")),
                "teaser": teaser,
                "badges": [kind] if kind else [],
            }
        )
    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "google_docs_parse_document",
        "summary": {
            "line": f"{len(chunks)} chunk(s)",
            "detail_lines": [detail] if detail else [],
        },
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def _looks_like_gmail_curated_message_list(arr: list[Any]) -> bool:
    """True when list items look like Gmail List Messages curated rows (not arbitrary dicts)."""
    if not arr or not all(isinstance(x, dict) for x in arr):
        return False
    markers = (
        "fetch_error",
        "labelIds",
        "snippet",
        "threadId",
        "internalDate",
        "body_text",
        "subject",
    )
    for m in arr:
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.strip():
            return False
    return any(any(k in row for k in markers) for row in arr)


def build_gmail_list_explorer_from_messages(
    messages: Any,
    result_size_estimate: Any = None,
) -> dict[str, Any]:
    """Explorer rows for a list of curated Gmail message dicts."""
    if not isinstance(messages, list):
        messages = []

    est = result_size_estimate
    n = len(messages)
    failed = sum(1 for m in messages if isinstance(m, dict) and _str(m.get("fetch_error")) != "")
    ok = n - failed

    summary: dict[str, Any] = {
        "line": f"{n} message(s) returned",
        "detail_lines": [],
    }
    if est is not None:
        summary["detail_lines"].append(f"API resultSizeEstimate: {est}")
    if n > 0:
        summary["detail_lines"].append(f"Fetched OK: {ok} · failed: {failed}")

    items: list[dict[str, Any]] = []
    overflow = max(0, n - OUTPUT_EXPLORER_MAX_ITEMS)
    slice_msgs = messages[:OUTPUT_EXPLORER_MAX_ITEMS]

    for idx, m in enumerate(slice_msgs):
        if not isinstance(m, dict):
            continue
        err = _str(m.get("fetch_error"))
        if err:
            items.append(
                {
                    "index": idx,
                    "row_state": "error",
                    "primary_line": "Fetch error",
                    "secondary_line": _str(m.get("id")) or "—",
                    "teaser": _truncate_teaser(err),
                    "badges": [],
                }
            )
            continue

        subj = _str(m.get("subject"))
        primary = subj if subj else "(No subject)"
        from_ = _str(m.get("from"))
        date_ = _str(m.get("date")) or _str(m.get("internalDate"))
        secondary_parts = [p for p in (from_, date_) if p]
        secondary = " · ".join(secondary_parts) if secondary_parts else ""

        snip = _str(m.get("snippet"))
        body = _str(m.get("body_text"))
        teaser_src = snip if snip else body
        teaser = _truncate_teaser(teaser_src) if teaser_src else ""

        labels = m.get("labelIds")
        badges: list[str] = []
        if isinstance(labels, list):
            for x in labels[:6]:
                if x is not None:
                    sx = str(x).strip()
                    if sx:
                        badges.append(sx)

        items.append(
            {
                "index": idx,
                "row_state": "ok",
                "primary_line": primary,
                "secondary_line": secondary,
                "teaser": teaser,
                "badges": badges,
            }
        )

    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "gmail_list_messages",
        "summary": summary,
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def build_gmail_list_explorer(data: dict[str, Any]) -> dict[str, Any]:
    """Explorer view for legacy dictionary skill output: ``messages`` + ``resultSizeEstimate``."""
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    return build_gmail_list_explorer_from_messages(messages, data.get("resultSizeEstimate"))


def build_calendar_list_explorer(data: dict[str, Any]) -> dict[str, Any]:
    """Explorer view for calendar_list_events `output.data`."""
    events = data.get("events")
    if not isinstance(events, list):
        events = []

    n = len(events)
    summary: dict[str, Any] = {
        "line": f"{n} event(s) in window",
        "detail_lines": [],
    }

    items: list[dict[str, Any]] = []
    overflow = max(0, n - OUTPUT_EXPLORER_MAX_ITEMS)
    slice_ev = events[:OUTPUT_EXPLORER_MAX_ITEMS]

    for idx, ev in enumerate(slice_ev):
        if not isinstance(ev, dict):
            continue
        title = _str(ev.get("summary"))
        primary = title if title else "(No title)"
        start = _str(ev.get("start"))
        end = _str(ev.get("end"))
        when = ""
        if start and end:
            when = f"{start} → {end}"
        elif start:
            when = start
        loc = _str(ev.get("location"))
        secondary_parts = [p for p in (when, loc) if p]
        secondary = " · ".join(secondary_parts) if secondary_parts else ""

        badges: list[str] = []
        st = _str(ev.get("status"))
        if st:
            badges.append(st)

        items.append(
            {
                "index": idx,
                "row_state": "ok",
                "primary_line": primary,
                "secondary_line": secondary,
                "teaser": "",
                "badges": badges,
            }
        )

    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "calendar_list_events",
        "summary": summary,
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def build_dictionary_primitive_explorer(data: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(data.keys(), key=lambda k: str(k))
    n = len(keys)
    summary: dict[str, Any] = {
        "line": f"{n} key(s)",
        "detail_lines": [],
    }
    items: list[dict[str, Any]] = []
    overflow = max(0, n - OUTPUT_EXPLORER_MAX_ITEMS)
    for idx, k in enumerate(keys[:OUTPUT_EXPLORER_MAX_ITEMS]):
        val = data[k]
        ik = str(k)
        inf = infer_primitive_kind(val)
        items.append(
            {
                "index": idx,
                "row_state": "empty" if val is None else "ok",
                "primary_line": ik,
                "secondary_line": inf,
                "teaser": _json_preview(val),
                "badges": [],
                "inferred_primitive": inf,
            }
        )
    kinds = {infer_primitive_kind(data[k]) for k in keys}
    if len(kinds) > 1:
        summary["detail_lines"].append("Multiple value types")

    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "dictionary_primitive",
        "summary": summary,
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def build_start_outputs_explorer(data: dict[str, Any]) -> dict[str, Any]:
    """One row per Start output slot; preserve insertion order (matches executor / required_inputs)."""
    keys = list(data.keys())
    n = len(keys)
    summary: dict[str, Any] = {
        "line": "Start outputs",
        "detail_lines": [f"{n} output slot(s)"],
    }
    items: list[dict[str, Any]] = []
    overflow = max(0, n - OUTPUT_EXPLORER_MAX_ITEMS)
    for idx, k in enumerate(keys[:OUTPUT_EXPLORER_MAX_ITEMS]):
        val = data[k]
        ik = str(k)
        inf = infer_primitive_kind(val)
        items.append(
            {
                "index": idx,
                "row_state": "ok",
                "primary_line": ik,
                "secondary_line": inf,
                "teaser": _json_preview(val),
                "badges": [],
                "inferred_primitive": inf,
            }
        )
    kinds = {infer_primitive_kind(data[k]) for k in keys}
    if len(kinds) > 1:
        summary["detail_lines"].append("Multiple value types")

    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "start_outputs",
        "summary": summary,
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def build_list_primitive_explorer(arr: list[Any]) -> dict[str, Any]:
    n = len(arr)
    kinds = [infer_primitive_kind(x) for x in arr]
    distinct = set(kinds)
    summary: dict[str, Any] = {
        "line": f"{n} item(s)",
        "detail_lines": [],
    }
    if len(distinct) > 1:
        summary["detail_lines"].append("Heterogeneous list")

    items: list[dict[str, Any]] = []
    overflow = max(0, n - OUTPUT_EXPLORER_MAX_ITEMS)
    for idx, val in enumerate(arr[:OUTPUT_EXPLORER_MAX_ITEMS]):
        inf = kinds[idx]
        inferred_row = "mixed" if len(distinct) > 1 else inf
        items.append(
            {
                "index": idx,
                "row_state": "ok",
                "primary_line": f"[{idx}]",
                "secondary_line": inf,
                "teaser": _json_preview(val),
                "badges": [],
                "inferred_primitive": inferred_row,
            }
        )

    out: dict[str, Any] = {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "list_primitive",
        "summary": summary,
        "items": items,
    }
    if overflow > 0:
        out["overflow_count"] = overflow
    return out


def build_string_primitive_explorer(text: Any) -> dict[str, Any]:
    s = _str(text)
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "string_primitive",
        "summary": {
            "line": "String value",
            "detail_lines": [_truncate_teaser(s, 500)] if s else ["(empty)"],
        },
        "items": [],
    }


def build_boolean_primitive_explorer(value: Any) -> dict[str, Any]:
    v = value
    if not isinstance(v, bool):
        v = bool(v) if v is not None else False
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "boolean_primitive",
        "summary": {
            "line": "Boolean value",
            "detail_lines": ["true" if v else "false"],
        },
        "items": [],
    }


def build_int_primitive_explorer(value: Any) -> dict[str, Any]:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = 0
    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "int_primitive",
        "summary": {
            "line": "Integer value",
            "detail_lines": [str(n)],
        },
        "items": [],
    }


def build_generic_node_explorer(output_dump: dict[str, Any]) -> dict[str, Any]:
    kind = _str(output_dump.get("kind")) or "output"
    detail_lines: list[str] = []

    if kind == "response":
        t = _str(output_dump.get("text"))
        detail_lines.append(_truncate_teaser(t) if t else "(empty)")
    elif kind == "conditional":
        detail_lines.append(f"branch: {output_dump.get('branch')}")
        pt = output_dump.get("passthrough_value")
        if isinstance(pt, list):
            detail_lines.append(f"passthrough: list ({len(pt)} item(s))")
        elif isinstance(pt, dict):
            detail_lines.append(f"passthrough: dictionary ({len(pt)} key(s))")
        elif pt is not None:
            detail_lines.append(f"passthrough: {_truncate_teaser(str(pt))}")
    elif kind == "stop":
        t = _str(output_dump.get("text"))
        detail_lines.append(_truncate_teaser(t) if t else "(empty)")
    elif kind == "start":
        outs = output_dump.get("outputs")
        if isinstance(outs, dict):
            detail_lines.append(f"{len(outs)} start input(s)")
        t = _str(output_dump.get("text"))
        if t:
            detail_lines.append(_truncate_teaser(t))
    elif kind == "structure":
        schema = output_dump.get("schema_dict")
        if isinstance(schema, dict):
            detail_lines.append(f"Schema with {len(schema)} top-level key(s)")
        else:
            detail_lines.append("Structure output")
    elif kind == "document":
        nm = _str(output_dump.get("name"))
        if nm:
            detail_lines.append(f"Document: {nm}")
        md = _str(output_dump.get("markdown"))
        if md:
            detail_lines.append(_truncate_teaser(md))
    elif kind == "audio":
        mt = _str(output_dump.get("mime_type")) or "audio/wav"
        ab = output_dump.get("audio_base64")
        n = len(ab) if isinstance(ab, str) else 0
        detail_lines.append(f"{mt} · base64 length {n}")

    line = f"{kind} output"
    if not detail_lines:
        detail_lines.append("(see raw output)")

    return {
        "version": OUTPUT_EXPLORER_VERSION,
        "kind": "generic",
        "summary": {"line": line, "detail_lines": detail_lines},
        "items": [],
    }


def try_build_output_explorer(raw_output_dump: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build explorer metadata from serialized node output (`model_dump(mode='json')`), or None."""
    if not raw_output_dump or not isinstance(raw_output_dump, dict):
        return None

    kind = raw_output_dump.get("kind")

    if kind == "dictionary":
        inner = raw_output_dump.get("data")
        if not isinstance(inner, dict):
            return None
        builtin = try_builtin_dictionary_explorer(inner)
        if builtin is not None:
            return builtin
        return build_dictionary_primitive_explorer(inner)

    if kind == "list":
        data = raw_output_dump.get("data")
        if not isinstance(data, list):
            return None
        if _looks_like_gmail_curated_message_list(data):
            return build_gmail_list_explorer_from_messages(data, None)
        if _looks_like_google_docs_chunk_list(data):
            return build_google_docs_parse_document_explorer(data)
        return build_list_primitive_explorer(data)

    if kind == "string":
        return build_string_primitive_explorer(raw_output_dump.get("text"))

    if kind == "boolean":
        return build_boolean_primitive_explorer(raw_output_dump.get("value"))

    if kind == "int":
        return build_int_primitive_explorer(raw_output_dump.get("value"))

    if kind == "start":
        outs = raw_output_dump.get("outputs")
        if isinstance(outs, dict) and len(outs) > 0:
            return build_start_outputs_explorer(outs)
        return build_generic_node_explorer(raw_output_dump)

    if kind in ("response", "structure", "document", "stop", "conditional", "audio"):
        return build_generic_node_explorer(raw_output_dump)

    return build_generic_node_explorer(raw_output_dump)


def merge_details_with_output_explorer(
    details: dict[str, Any],
    raw_output_dump: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach `output_explorer` from unredacted output for stream/API client display."""
    out = dict(details)
    ex = try_build_output_explorer(raw_output_dump)
    if ex:
        out["output_explorer"] = ex
    return out


def attach_output_explorer_after_redact(
    safe_output_dump: dict[str, Any] | None,
    safe_details: dict[str, Any],
) -> dict[str, Any]:
    """After redact_node_log_for_storage, add explorer built from redacted output (at-rest alignment)."""
    det = dict(safe_details)
    ex = try_build_output_explorer(safe_output_dump)
    if ex:
        det["output_explorer"] = deepcopy(ex)
    return det
