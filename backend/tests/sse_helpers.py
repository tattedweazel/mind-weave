"""Helpers for asserting against ``text/event-stream`` responses from the test client."""

from __future__ import annotations

from app.core.sse_parse import parse_sse


def sse_response_body_to_legacy_workflow_events(raw: bytes | str) -> list[dict[str, object]]:
    """Parse SSE from ``GET …/workflow-runs/…/events`` into NDJSON-era dict shapes."""
    from app.domain.workflow_sse_ndjson_compat import sse_tuple_to_ndjson_like_event

    mapped: list[dict[str, object]] = []
    for ev_name, payload in parse_sse(raw):
        row = sse_tuple_to_ndjson_like_event(ev_name, payload)
        if row is not None:
            mapped.append(row)
    return mapped
