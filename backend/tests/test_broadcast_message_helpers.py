"""Unit tests for broadcast_message helpers."""

from app.domain.workflow_executor.broadcast_message import (
    build_broadcast_segment,
    collect_broadcast_segments_from_node_results,
    looks_like_markdown,
    normalize_broadcast_severity,
)
from app.domain.schemas import NodeRunResult


def test_looks_like_markdown():
    assert not looks_like_markdown("plain")
    assert looks_like_markdown("# Title")
    assert looks_like_markdown("- item")


def test_build_broadcast_segment_markdown_flag():
    seg = build_broadcast_segment(node_id="n1", body="# Hi", severity="notice", title="T")
    assert seg["render_markdown"] is True
    assert seg["severity"] == "notice"
    assert seg["title"] == "T"


def test_collect_broadcast_segments_from_node_results():
    rows = [
        NodeRunResult(
            node_id="b",
            status="ok",
            details={"broadcast_segment": {"node_id": "b", "body": "two", "severity": "info"}},
            step_number=2,
        ),
        NodeRunResult(
            node_id="a",
            status="ok",
            details={"broadcast_segment": {"node_id": "a", "body": "one", "severity": "info"}},
            step_number=1,
        ),
    ]
    out = collect_broadcast_segments_from_node_results(rows)
    assert [s["body"] for s in out] == ["one", "two"]


def test_normalize_broadcast_severity_defaults():
    assert normalize_broadcast_severity(None) == "info"
    assert normalize_broadcast_severity("success") == "success"
    assert normalize_broadcast_severity("bogus") == "info"
