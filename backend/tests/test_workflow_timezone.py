"""Workflow time zone: Gmail day mapping resolution (profile + execution_time_zone)."""

from app.domain.workflow_executor.executor import _effective_gmail_calendar_zone


def test_effective_gmail_zone_explicit_profile_wins():
    assert _effective_gmail_calendar_zone({"workflow_time_zone": "Europe/Paris"}, "America/New_York") == "Europe/Paris"


def test_effective_gmail_zone_system_uses_execution():
    assert _effective_gmail_calendar_zone({"workflow_time_zone": "system"}, "Asia/Tokyo") == "Asia/Tokyo"


def test_effective_gmail_zone_missing_setting_uses_execution():
    assert _effective_gmail_calendar_zone({}, "Asia/Tokyo") == "Asia/Tokyo"


def test_effective_gmail_zone_none_when_no_execution_for_system():
    assert _effective_gmail_calendar_zone({"workflow_time_zone": "system"}, None) is None
    assert _effective_gmail_calendar_zone({}, None) is None
