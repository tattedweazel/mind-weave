"""Tests for `details.output_explorer` builders."""

from __future__ import annotations

from app.core.run_log_redaction import redact_node_log_for_storage
from app.domain.workflow_executor.output_explorer import (
    FORBIDDEN_ITEM_KEYS,
    OUTPUT_EXPLORER_MAX_ITEMS,
    attach_output_explorer_after_redact,
    build_calendar_list_explorer,
    build_gmail_list_explorer,
    merge_details_with_output_explorer,
    try_build_output_explorer,
    try_builtin_dictionary_explorer,
)


def _assert_items_redaction_safe(items: list[dict]) -> None:
    for it in items:
        for k in it:
            kl = k.lower()
            assert kl not in FORBIDDEN_ITEM_KEYS
            assert "prompt" not in kl


def test_build_gmail_list_explorer_happy_path():
    data = {
        "resultSizeEstimate": 200,
        "messages": [
            {
                "id": "a1",
                "threadId": "t1",
                "subject": "Hello",
                "from": "a@ex.com",
                "date": "Mon, 1 Jan 2024",
                "snippet": "Short snippet here",
                "labelIds": ["UNREAD", "INBOX"],
            },
        ],
    }
    ex = build_gmail_list_explorer(data)
    assert ex["version"] == 1
    assert ex["kind"] == "gmail_list_messages"
    assert ex["summary"]["line"] == "1 message(s) returned"
    assert len(ex["items"]) == 1
    row = ex["items"][0]
    assert row["row_state"] == "ok"
    assert row["primary_line"] == "Hello"
    assert "a@ex.com" in row["secondary_line"]
    assert "Short snippet" in row["teaser"]
    assert "UNREAD" in row["badges"]
    _assert_items_redaction_safe(ex["items"])


def test_build_gmail_list_explorer_fetch_error_row():
    data = {
        "resultSizeEstimate": 1,
        "messages": [
            {"id": "x", "fetch_error": "something went wrong"},
        ],
    }
    ex = build_gmail_list_explorer(data)
    row = ex["items"][0]
    assert row["row_state"] == "error"
    assert row["primary_line"] == "Fetch error"
    assert "something went wrong" in row["teaser"]
    _assert_items_redaction_safe(ex["items"])


def test_build_gmail_list_explorer_overflow():
    msgs = [{"id": str(i), "subject": f"S{i}"} for i in range(OUTPUT_EXPLORER_MAX_ITEMS + 12)]
    data = {"resultSizeEstimate": 900, "messages": msgs}
    ex = build_gmail_list_explorer(data)
    assert len(ex["items"]) == OUTPUT_EXPLORER_MAX_ITEMS
    assert ex["overflow_count"] == 12


def test_build_calendar_list_explorer():
    data = {
        "events": [
            {
                "id": "e1",
                "summary": "Standup",
                "start": "2026-03-20T15:00:00-05:00",
                "end": "2026-03-20T15:30:00-05:00",
                "status": "confirmed",
            },
            {"id": "e2", "start": "2026-03-21"},
        ]
    }
    ex = build_calendar_list_explorer(data)
    assert ex["kind"] == "calendar_list_events"
    assert ex["summary"]["line"] == "2 event(s) in window"
    assert ex["items"][0]["primary_line"] == "Standup"
    assert "→" in ex["items"][0]["secondary_line"]
    assert "confirmed" in ex["items"][0]["badges"]
    assert ex["items"][1]["primary_line"] == "(No title)"
    _assert_items_redaction_safe(ex["items"])


def test_try_builtin_dictionary_explorer_dispatch():
    g = try_builtin_dictionary_explorer(
        {"resultSizeEstimate": 1, "messages": []},
    )
    assert g is not None and g["kind"] == "gmail_list_messages"

    assert try_builtin_dictionary_explorer({"events": []}) is None
    assert try_builtin_dictionary_explorer({"events": [{"not_calendar": 1}]}) is None

    c = try_builtin_dictionary_explorer(
        {"events": [{"summary": "Standup", "start": "2026-03-20T15:00:00Z", "end": "2026-03-20T15:30:00Z"}]},
    )
    assert c is not None and c["kind"] == "calendar_list_events"

    assert try_builtin_dictionary_explorer({"foo": []}) is None


def test_try_build_output_explorer_dictionary_primitive():
    ex = try_build_output_explorer(
        {"kind": "dictionary", "node_id": "n1", "data": {"foo": [], "bar": 1}},
    )
    assert ex is not None
    assert ex["kind"] == "dictionary_primitive"
    assert ex["summary"]["line"] == "2 key(s)"
    keys = {row["primary_line"] for row in ex["items"]}
    assert keys == {"bar", "foo"}


def test_try_build_output_explorer_dictionary_primitive_null_row_state_empty():
    ex = try_build_output_explorer(
        {"kind": "dictionary", "node_id": "n1", "data": {"region_label": None, "kind": "empty"}},
    )
    assert ex is not None
    by_key = {row["primary_line"]: row for row in ex["items"]}
    assert by_key["region_label"]["row_state"] == "empty"
    assert by_key["kind"]["row_state"] == "ok"


def test_try_build_dictionary_with_events_key_not_calendar_shape_uses_primitive():
    """Arbitrary ``events`` lists must not hijack the Calendar explorer."""
    ex = try_build_output_explorer(
        {"kind": "dictionary", "node_id": "n1", "data": {"a": 1, "events": [{"custom": True}]}},
    )
    assert ex is not None
    assert ex["kind"] == "dictionary_primitive"
    assert ex["summary"]["line"] == "2 key(s)"


def test_try_build_output_explorer_list_primitive():
    ex = try_build_output_explorer(
        {"kind": "list", "node_id": "n1", "data": [1, "a", True]},
    )
    assert ex is not None
    assert ex["kind"] == "list_primitive"
    assert "Heterogeneous" in (ex["summary"].get("detail_lines") or [""])[0]
    assert len(ex["items"]) == 3


def test_try_build_output_explorer_list_gmail_curated_shape():
    ex = try_build_output_explorer(
        {
            "kind": "list",
            "node_id": "n1",
            "data": [{"id": "a1", "threadId": "t1", "subject": "Hi", "snippet": "S"}],
        },
    )
    assert ex is not None
    assert ex["kind"] == "gmail_list_messages"
    assert ex["summary"]["line"] == "1 message(s) returned"


def test_try_build_output_explorer_generic_response():
    ex = try_build_output_explorer(
        {"kind": "response", "node_id": "n1", "text": "Hello model", "metadata": {}},
    )
    assert ex is not None
    assert ex["kind"] == "generic"
    assert "Hello model" in (ex["summary"]["detail_lines"] or [""])[0]


def test_try_build_output_explorer_start_outputs_preserves_key_order():
    ex = try_build_output_explorer(
        {
            "kind": "start",
            "node_id": "n_start",
            "outputs": {"z_first": 1, "a_second": "two", "m_third": [3]},
            "text": "ignored for explorer rows",
        },
    )
    assert ex is not None
    assert ex["kind"] == "start_outputs"
    assert ex["summary"]["line"] == "Start outputs"
    assert "3 output slot(s)" in ex["summary"]["detail_lines"][0]
    assert "Multiple value types" in ex["summary"]["detail_lines"]
    lines = [row["primary_line"] for row in ex["items"]]
    assert lines == ["z_first", "a_second", "m_third"]
    _assert_items_redaction_safe(ex["items"])


def test_try_build_output_explorer_start_empty_outputs_falls_back_generic():
    ex = try_build_output_explorer(
        {"kind": "start", "node_id": "n1", "outputs": {}, "text": "hello"},
    )
    assert ex is not None
    assert ex["kind"] == "generic"


def test_try_build_output_explorer_start_outputs_overflow():
    outs = {f"k{i}": i for i in range(OUTPUT_EXPLORER_MAX_ITEMS + 5)}
    ex = try_build_output_explorer(
        {"kind": "start", "node_id": "n1", "outputs": outs, "text": ""},
    )
    assert ex is not None
    assert ex["kind"] == "start_outputs"
    assert len(ex["items"]) == OUTPUT_EXPLORER_MAX_ITEMS
    assert ex["overflow_count"] == 5


def test_merge_and_attach_align_with_redaction():
    """Persisted explorer rows should not be more revealing than redacted output.data."""
    raw_inner = {
        "resultSizeEstimate": 5,
        "messages": [
            {
                "id": "m1",
                "subject": "Secret subject",
                "snippet": "Secret snippet",
            },
        ],
    }
    raw_dump = {"kind": "dictionary", "node_id": "n1", "data": raw_inner}
    detailed = merge_details_with_output_explorer({"message_count": 1}, raw_dump)
    assert detailed["output_explorer"]["items"][0]["primary_line"] == "Secret subject"

    safe_out, safe_det = redact_node_log_for_storage(raw_dump, {"message_count": 1})
    assert safe_out is not None
    safe_det2 = attach_output_explorer_after_redact(safe_out, safe_det)
    prim = safe_det2["output_explorer"]["items"][0]["primary_line"]
    assert prim == "[redacted]"
