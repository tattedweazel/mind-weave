"""Map internal SSE `(event_name, payload)` pairs to NDJSON-era dicts used by CLI tools and tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def sse_tuple_to_ndjson_like_event(event_name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    seq = payload.get("seq")
    base_extra: dict[str, Any] = {}
    if isinstance(seq, int):
        base_extra["seq"] = seq

    if event_name == "workflow.started":
        return {"event": "start", "workflow_id": payload["workflow_id"], "run_id": payload["run_id"], **base_extra}
    if event_name == "node.started":
        return {"event": "node_start", "node_id": payload["node_id"], **base_extra}
    if event_name in {"node.completed", "node.failed"}:
        row: dict[str, Any] = {
            "event": "node_end",
            "node_id": payload.get("node_id"),
            "result": payload.get("result"),
            **base_extra,
        }
        return row
    if event_name == "workflow.completed":
        return {"event": "end", "result": payload.get("result"), **base_extra}
    if event_name == "workflow.failed":
        return {"event": "error", "error": payload.get("error") or "Workflow failed", **base_extra}
    if event_name == "workflow.events_timeout":
        return {"event": "error", "error": payload.get("error") or "timeout", **base_extra}
    if event_name == "input_required":
        stripped = {k: v for k, v in payload.items() if k != "seq"}
        return {"event": "input_required", **stripped}
    if event_name == "transcription_job_status":
        stripped = {k: v for k, v in payload.items() if k not in {"seq", "event"}}
        return {"event": "transcription_job_status", **stripped}
    return None


def iter_sse_pairs_as_ndjson(events: Iterable[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, payload in events:
        row = sse_tuple_to_ndjson_like_event(name, payload)
        if row is not None:
            out.append(row)
    return out
