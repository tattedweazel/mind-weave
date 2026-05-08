"""Tests for Workspace interpret/compose temporal context (clock anchor for relative dates)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.services.workspace_runtime_service import format_workspace_temporal_context_for_llm


def test_format_temporal_context_utc_only_when_no_zone():
    now = datetime(2026, 4, 8, 15, 0, 0, tzinfo=timezone.utc)
    text = format_workspace_temporal_context_for_llm(now, None)
    assert "Temporal context" in text
    assert "2026-04-08T15:00:00+00:00" in text
    assert "user workflow timezone" not in text
    assert "2024" not in text


def test_format_temporal_context_naive_treated_as_utc():
    now = datetime(2026, 4, 8, 15, 0, 0)
    text = format_workspace_temporal_context_for_llm(now, None)
    assert "2026-04-08T15:00:00+00:00" in text


def test_format_temporal_context_paris_local_line():
    """2026-04-08 15:00 UTC = 17:00 in Europe/Paris (CEST)."""
    now = datetime(2026, 4, 8, 15, 0, 0, tzinfo=timezone.utc)
    text = format_workspace_temporal_context_for_llm(now, "Europe/Paris")
    assert "Europe/Paris" in text
    assert "2026-04-08T17:00:00+02:00" in text
    assert "2024" not in text


def test_format_temporal_context_invalid_zone_skips_local():
    now = datetime(2026, 4, 8, 15, 0, 0, tzinfo=timezone.utc)
    text = format_workspace_temporal_context_for_llm(now, "Not/A_Real_Zone_Id")
    assert "2026-04-08T15:00:00+00:00" in text
    assert "user workflow timezone" not in text
