"""Unit tests for :mod:`app.core.sse_parse` (SSE framing reused by APIs + scripts)."""

from __future__ import annotations

from app.core.sse_parse import SseBlockAccumulator, parse_sse


def test_parse_sse_splits_blocks() -> None:
    raw = (
        'event: workflow.started\n'
        'data: {"workflow_id":"w","run_id":"r"}\n'
        '\n'
        ": comment\n\n"
        'event: node.started\n'
        'data: {"node_id":"n1"}\n'
        '\n'
    )
    parsed = parse_sse(raw)
    assert parsed == [
        ("workflow.started", {"workflow_id": "w", "run_id": "r"}),
        ("node.started", {"node_id": "n1"}),
    ]


def test_sse_accumulator_splits_across_chunk_boundaries() -> None:
    acc = SseBlockAccumulator()
    a = (
        'event: ping\n'
        'data: {"x":1}\n'
        '\n'
        'event: pong\n'
    )
    b = (
        'data: {"y":2}\n'
        '\n'
    )
    first = acc.feed_bytes(a.encode())
    second = acc.feed_bytes(b.encode())
    assert first == [("ping", {"x": 1})]
    assert second == [("pong", {"y": 2})]
