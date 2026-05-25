"""Broadcast Message utility helpers (segment shape, markdown heuristic, run aggregation)."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from app.domain.schemas import NodeRunResult, WorkflowRunResult

BroadcastSeverity = Literal["info", "notice", "success"]

_VALID_SEVERITIES = frozenset({"info", "notice", "success"})

_MARKDOWN_PATTERNS = (
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),
    re.compile(r"```"),
    re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s+\S", re.MULTILINE),
    re.compile(r"\*\*[^*\n]+\*\*"),
    re.compile(r"__[^_\n]+__"),
)


def normalize_broadcast_severity(raw: Any) -> BroadcastSeverity:
    s = str(raw or "info").strip().lower()
    if s in _VALID_SEVERITIES:
        return s  # type: ignore[return-value]
    return "info"


def looks_like_markdown(text: str) -> bool:
    if not text or not text.strip():
        return False
    return any(p.search(text) for p in _MARKDOWN_PATTERNS)


def build_broadcast_segment(
    *,
    node_id: str,
    body: str,
    title: Optional[str] = None,
    severity: BroadcastSeverity = "info",
    source: Optional[str] = None,
    step_number: Optional[int] = None,
) -> dict[str, Any]:
    title_clean = (title or "").strip() or None
    seg: dict[str, Any] = {
        "node_id": node_id,
        "body": body,
        "severity": severity,
        "render_markdown": looks_like_markdown(body),
    }
    if title_clean:
        seg["title"] = title_clean
    if source:
        seg["source"] = source
    if step_number is not None:
        seg["step_number"] = step_number
    return seg


def broadcast_segment_from_node_result(nr: NodeRunResult) -> dict[str, Any] | None:
    if nr.status != "ok" or not nr.details:
        return None
    det = nr.details if isinstance(nr.details, dict) else {}
    raw = det.get("broadcast_segment")
    if not isinstance(raw, dict):
        return None
    body = raw.get("body")
    if not isinstance(body, str) or not body.strip():
        return None
    return dict(raw)


def collect_broadcast_segments_from_node_results(
    node_results: list[NodeRunResult] | None,
    *,
    source: Optional[str] = None,
) -> list[dict[str, Any]]:
    if not node_results:
        return []
    sorted_rows = sorted(
        node_results,
        key=lambda nr: (nr.step_number if nr.step_number is not None else 0, nr.node_id),
    )
    out: list[dict[str, Any]] = []
    for nr in sorted_rows:
        seg = broadcast_segment_from_node_result(nr)
        if seg is None:
            continue
        if source and "source" not in seg:
            seg = {**seg, "source": source}
        out.append(seg)
    return out


def append_broadcast_segments_from_run(
    target: list[dict[str, Any]],
    run_result: WorkflowRunResult | None,
    *,
    source: Optional[str] = None,
) -> None:
    if run_result is None:
        return
    for seg in collect_broadcast_segments_from_node_results(run_result.node_results, source=source):
        target.append(seg)


def merge_broadcast_segment_lists(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for lst in lists:
        merged.extend(lst)
    merged.sort(
        key=lambda s: (
            s.get("step_number") if isinstance(s.get("step_number"), int) else 0,
            str(s.get("node_id") or ""),
        )
    )
    return merged
