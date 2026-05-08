"""Unit tests for RFC3339 parsing helpers used by workflow execution."""

from app.domain.workflow_executor.helpers import parse_rfc3339_datetime_string, shift_rfc3339_instant_by_days


def test_parse_rfc3339_datetime_string_z_suffix() -> None:
    assert parse_rfc3339_datetime_string("2026-01-15T12:30:00Z") == "2026-01-15T12:30:00Z"


def test_parse_rfc3339_datetime_string_offset_preserved() -> None:
    out = parse_rfc3339_datetime_string("2026-01-15T12:30:00-05:00")
    assert out == "2026-01-15T12:30:00-05:00"


def test_parse_rfc3339_datetime_string_invalid() -> None:
    assert parse_rfc3339_datetime_string("") is None
    assert parse_rfc3339_datetime_string("not-a-date") is None


def test_shift_rfc3339_instant_by_days_negative() -> None:
    norm = parse_rfc3339_datetime_string("2026-03-10T12:00:00Z")
    assert norm is not None
    out = shift_rfc3339_instant_by_days(norm, -5)
    assert out == "2026-03-05T12:00:00Z"


def test_shift_rfc3339_instant_by_days_positive() -> None:
    norm = parse_rfc3339_datetime_string("2026-01-28T00:00:00Z")
    assert norm is not None
    out = shift_rfc3339_instant_by_days(norm, 3)
    assert out == "2026-01-31T00:00:00Z"
