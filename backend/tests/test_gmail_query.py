"""Unit tests for Gmail `q` composition helpers."""

from app.integrations.gmail_query import (
    append_category_q_clauses,
    build_messages_list_q,
    normalize_gmail_exclude_categories,
    normalize_gmail_inbox_focus,
    rfc3339_to_gmail_date,
)


def test_normalize_gmail_inbox_focus():
    assert normalize_gmail_inbox_focus(None) == "off"
    assert normalize_gmail_inbox_focus("primary") == "primary"
    assert normalize_gmail_inbox_focus("PRIMARY") == "primary"
    assert normalize_gmail_inbox_focus("off") == "off"
    assert normalize_gmail_inbox_focus("nope") == "off"


def test_normalize_gmail_exclude_categories():
    assert normalize_gmail_exclude_categories(None) == []
    assert normalize_gmail_exclude_categories("x") == []
    assert normalize_gmail_exclude_categories(["promotions", "PROMOTIONS", "social", "primary", "nope"]) == [
        "promotions",
        "social",
    ]


def test_append_category_q_clauses_primary_only():
    assert (
        append_category_q_clauses(None, inbox_focus="primary", exclude_categories=["promotions"]) == "category:primary"
    )
    assert (
        append_category_q_clauses("is:unread", inbox_focus="primary", exclude_categories=["promotions"])
        == "is:unread category:primary"
    )


def test_append_category_q_clauses_excludes_when_not_primary():
    q = append_category_q_clauses("has:attachment", inbox_focus="off", exclude_categories=["promotions", "social"])
    assert q == "has:attachment -category:promotions -category:social"


def test_append_category_q_clauses_none_when_empty():
    assert append_category_q_clauses(None, inbox_focus="off", exclude_categories=[]) is None


def test_build_then_append_order():
    base = build_messages_list_q(
        raw_query="from:test@example.com",
        after_rfc3339=None,
        before_rfc3339=None,
        unread_only=True,
    )
    assert base == "is:unread from:test@example.com"
    final = append_category_q_clauses(base, inbox_focus="off", exclude_categories=["promotions"])
    assert final == "is:unread from:test@example.com -category:promotions"


def test_rfc3339_to_gmail_date_utc_by_default():
    assert rfc3339_to_gmail_date("2026-03-01T15:00:00Z") == "2026/03/01"


def test_rfc3339_to_gmail_date_uses_calendar_zone():
    """Same instant: UTC March 1 15:00 is March 2 00:00 in Tokyo."""
    assert rfc3339_to_gmail_date("2026-03-01T15:00:00Z", calendar_zone="Asia/Tokyo") == "2026/03/02"


def test_build_messages_list_q_passes_zone_to_after_before():
    q = build_messages_list_q(
        raw_query=None,
        after_rfc3339="2026-03-01T15:00:00Z",
        before_rfc3339="2026-03-10T00:00:00Z",
        unread_only=False,
        gmail_list_calendar_zone="Asia/Tokyo",
    )
    assert q == "after:2026/03/02 before:2026/03/10"
