"""Tests for compact capability output formatting in the compose step.

Covers _compact_capability_output_for_compose and related helpers, verifying that
list-shaped outputs (emails, calendar events, generic items) produce a compact
indexed summary with all items represented, and that the compose prompt and
pipeline preview share the DEFAULT_COMPOSE_BASE_PROMPT constant.
"""

from __future__ import annotations

import json

from app.domain.services.workspace_runtime_service import (
    DEFAULT_COMPOSE_BASE_PROMPT,
    _compact_calendar_line,
    _compact_capability_output_for_compose,
    _compact_email_line,
    _compact_generic_line,
    _extract_list_from_output,
    _is_calendar_item,
    _is_email_item,
)

# ---------------------------------------------------------------------------
# _is_email_item
# ---------------------------------------------------------------------------


class TestIsEmailItem:
    def test_detects_id_and_thread_id(self):
        assert _is_email_item({"id": "abc", "threadId": "t1"}) is True

    def test_detects_subject_and_body_text(self):
        assert _is_email_item({"from": "a@b.com", "body_text": "hello"}) is True

    def test_detects_subject_and_snippet(self):
        assert _is_email_item({"subject": "Hi", "snippet": "short"}) is True

    def test_rejects_empty_dict(self):
        assert _is_email_item({}) is False

    def test_rejects_unrelated_dict(self):
        assert _is_email_item({"summary": "meeting", "start": "2025-01-01"}) is False


# ---------------------------------------------------------------------------
# _is_calendar_item
# ---------------------------------------------------------------------------


class TestIsCalendarItem:
    def test_detects_summary_and_start(self):
        assert _is_calendar_item({"summary": "Standup", "start": "2025-01-01"}) is True

    def test_detects_summary_and_end(self):
        assert _is_calendar_item({"summary": "Standup", "end": "2025-01-01"}) is True

    def test_rejects_missing_summary(self):
        assert _is_calendar_item({"start": "2025-01-01"}) is False

    def test_rejects_non_string_summary(self):
        assert _is_calendar_item({"summary": 42, "start": "2025-01-01"}) is False

    def test_rejects_email_item(self):
        assert _is_calendar_item({"id": "abc", "threadId": "t1", "subject": "Hi"}) is False


# ---------------------------------------------------------------------------
# _compact_email_line
# ---------------------------------------------------------------------------


class TestCompactEmailLine:
    def test_includes_from_subject_date(self):
        item = {"from": "alice@example.com", "subject": "Weekly sync", "date": "Mon Jan 15"}
        result = _compact_email_line(1, item)
        assert result == "[1] | From: alice@example.com | Subject: Weekly sync | Date: Mon Jan 15"

    def test_falls_back_to_snippet_when_no_headers(self):
        item = {"id": "x", "threadId": "t", "body_text": "This is the email body content"}
        result = _compact_email_line(2, item)
        assert "[2]" in result
        assert "This is the email body content" in result

    def test_truncates_long_snippet_fallback(self):
        item = {"id": "x", "threadId": "t", "snippet": "A" * 200}
        result = _compact_email_line(1, item)
        assert len(result) < 200

    def test_handles_empty_strings(self):
        item = {"from": "", "subject": "", "date": ""}
        result = _compact_email_line(1, item)
        assert result == "[1]"


# ---------------------------------------------------------------------------
# _compact_calendar_line
# ---------------------------------------------------------------------------


class TestCompactCalendarLine:
    def test_includes_summary_start_end(self):
        item = {"summary": "Standup", "start": "2025-01-15T09:00:00", "end": "2025-01-15T09:30:00"}
        result = _compact_calendar_line(1, item)
        assert "[1]" in result
        assert "Summary: Standup" in result
        assert "Start: 2025-01-15T09:00:00" in result
        assert "End: 2025-01-15T09:30:00" in result

    def test_handles_dict_start_end(self):
        item = {
            "summary": "Meeting",
            "start": {"dateTime": "2025-01-15T10:00:00-05:00"},
            "end": {"dateTime": "2025-01-15T11:00:00-05:00"},
        }
        result = _compact_calendar_line(3, item)
        assert "[3]" in result
        assert "Start: 2025-01-15T10:00:00-05:00" in result

    def test_includes_location(self):
        item = {"summary": "Lunch", "start": "12:00", "location": "Cafe"}
        result = _compact_calendar_line(1, item)
        assert "Location: Cafe" in result

    def test_skips_none_values(self):
        item = {"summary": "Solo", "start": "12:00", "end": None, "location": None}
        result = _compact_calendar_line(1, item)
        assert "Location" not in result


# ---------------------------------------------------------------------------
# _compact_generic_line
# ---------------------------------------------------------------------------


class TestCompactGenericLine:
    def test_includes_string_fields(self):
        item = {"name": "Widget", "status": "active"}
        result = _compact_generic_line(1, item)
        assert "[1]" in result
        assert "name: Widget" in result
        assert "status: active" in result

    def test_includes_numeric_fields(self):
        item = {"count": 42, "active": True}
        result = _compact_generic_line(1, item)
        assert "count: 42" in result
        assert "active: True" in result

    def test_truncates_long_strings(self):
        item = {"description": "X" * 200}
        result = _compact_generic_line(1, item)
        assert len(result) < 200

    def test_limits_to_six_fields(self):
        item = {f"f{i}": f"v{i}" for i in range(10)}
        result = _compact_generic_line(1, item)
        assert "f6" not in result


# ---------------------------------------------------------------------------
# _extract_list_from_output
# ---------------------------------------------------------------------------


class TestExtractListFromOutput:
    def test_extracts_data_list(self):
        output = {"node_id": "n1", "data": [{"a": 1}, {"a": 2}]}
        assert _extract_list_from_output(output) == [{"a": 1}, {"a": 2}]

    def test_extracts_from_json_text(self):
        items = [{"id": "1"}, {"id": "2"}]
        output = {"node_id": "n1", "text": json.dumps(items)}
        assert _extract_list_from_output(output) == items

    def test_returns_none_for_non_list_text(self):
        output = {"node_id": "n1", "text": "just a string"}
        assert _extract_list_from_output(output) is None

    def test_returns_none_for_json_object_text(self):
        output = {"node_id": "n1", "text": '{"key": "value"}'}
        assert _extract_list_from_output(output) is None

    def test_returns_none_for_empty_dict(self):
        assert _extract_list_from_output({}) is None

    def test_returns_none_for_invalid_json(self):
        output = {"text": "[not valid json"}
        assert _extract_list_from_output(output) is None

    def test_returns_empty_list_when_data_is_empty(self):
        output = {"data": []}
        assert _extract_list_from_output(output) == []


# ---------------------------------------------------------------------------
# _compact_capability_output_for_compose (integration of the above)
# ---------------------------------------------------------------------------


class TestCompactCapabilityOutputForCompose:
    def test_five_emails_all_visible(self):
        emails = [
            {
                "id": f"m{i}",
                "threadId": f"t{i}",
                "from": f"sender{i}@example.com",
                "subject": f"Subject {i}",
                "date": f"2025-01-{15 - i}",
            }
            for i in range(5)
        ]
        output = {"node_id": "stop1", "text": json.dumps(emails)}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("5 items:")
        for i in range(5):
            assert f"sender{i}@example.com" in result
            assert f"Subject {i}" in result

    def test_five_emails_via_data_key(self):
        emails = [
            {"id": f"m{i}", "threadId": f"t{i}", "from": f"user{i}@test.com", "subject": f"Email {i}", "date": "Jan 1"}
            for i in range(5)
        ]
        output = {"node_id": "stop1", "data": emails}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("5 items:")
        for i in range(5):
            assert f"user{i}@test.com" in result

    def test_calendar_events_all_visible(self):
        events = [
            {
                "summary": f"Meeting {i}",
                "start": {"dateTime": f"2025-01-15T{9 + i}:00:00"},
                "end": {"dateTime": f"2025-01-15T{10 + i}:00:00"},
            }
            for i in range(3)
        ]
        output = {"node_id": "stop1", "data": events}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("3 items:")
        for i in range(3):
            assert f"Meeting {i}" in result

    def test_generic_items(self):
        items = [{"name": f"Item {i}", "price": i * 10} for i in range(4)]
        output = {"data": items}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("4 items:")
        for i in range(4):
            assert f"Item {i}" in result

    def test_non_list_output_falls_back_to_truncated_json(self):
        output = {"node_id": "stop1", "text": "This is a plain text response"}
        result = _compact_capability_output_for_compose(output)
        assert "items:" not in result
        assert "plain text response" in result

    def test_empty_list_falls_back_to_truncated_json(self):
        output = {"data": []}
        result = _compact_capability_output_for_compose(output)
        assert "items:" not in result

    def test_non_dict_items_fall_back_to_truncated_json(self):
        output = {"data": ["just", "strings"]}
        result = _compact_capability_output_for_compose(output)
        assert "items:" not in result

    def test_mixed_dict_and_non_dict_uses_only_dicts(self):
        output = {"data": [{"name": "Widget"}, "stray string", {"name": "Gadget"}]}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("2 items:")
        assert "Widget" in result
        assert "Gadget" in result

    def test_single_email_still_uses_compact_format(self):
        output = {"data": [{"id": "m1", "threadId": "t1", "from": "a@b.com", "subject": "Hi"}]}
        result = _compact_capability_output_for_compose(output)
        assert result.startswith("1 items:")
        assert "a@b.com" in result

    def test_fallback_truncation_respects_limit(self):
        output = {"text": "X" * 5000}
        result = _compact_capability_output_for_compose(output)
        assert len(result) <= 1600


# ---------------------------------------------------------------------------
# Compose prompt constant used by both _compose_and_memory and preview
# ---------------------------------------------------------------------------


class TestComposePromptConstant:
    def test_contains_multi_item_instruction(self):
        assert "summarize ALL of them" in DEFAULT_COMPOSE_BASE_PROMPT

    def test_contains_reply_text_instruction(self):
        assert "reply_text" in DEFAULT_COMPOSE_BASE_PROMPT

    def test_contains_memory_instruction(self):
        assert "memory_candidates" in DEFAULT_COMPOSE_BASE_PROMPT


def test_pipeline_preview_compose_uses_shared_constant(client):
    """The compose_system in pipeline preview must include DEFAULT_COMPOSE_BASE_PROMPT."""
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    r = client.get(f"/api/v1/workspaces/{wid}/pipeline/preview")
    assert r.status_code == 200
    body = r.json()
    assert DEFAULT_COMPOSE_BASE_PROMPT in body["compose_system"]
