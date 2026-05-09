"""Minimal SSE framing parser shared by scripts and backend tests."""

from __future__ import annotations

import json
from typing import Any


def _parse_sse_block_text(stripped: str) -> tuple[str, dict[str, Any]] | None:
    ev_name: str | None = None
    data_lines: list[str] = []
    for raw_line in stripped.split("\n"):
        line = raw_line.rstrip("\r")
        if not line:
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            ev_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
    if not ev_name:
        return None
    if not data_lines:
        return None
    payload = json.loads("\n".join(data_lines))
    return ev_name, payload


def parse_sse(raw: bytes | str) -> list[tuple[str, dict[str, Any]]]:
    """Return `(event_name, decoded JSON)` pairs for SSE blocks separated by blank lines."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    out: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        parsed = _parse_sse_block_text(stripped)
        if parsed is None:
            continue
        out.append(parsed)
    return out


class SseBlockAccumulator:
    """Incrementally decode `text/event-stream` frames split on blank-line boundaries."""

    def __init__(self) -> None:
        self._buf = ""

    def feed_bytes(self, chunk: bytes) -> list[tuple[str, dict[str, Any]]]:
        self._buf += chunk.decode("utf-8", errors="replace")
        messages: list[tuple[str, dict[str, Any]]] = []
        while "\n\n" in self._buf:
            raw_block, self._buf = self._buf.split("\n\n", 1)
            stripped = raw_block.strip()
            if not stripped:
                continue
            parsed = _parse_sse_block_text(stripped)
            if parsed is not None:
                messages.append(parsed)
        return messages
