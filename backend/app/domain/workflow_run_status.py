"""Map executor aggregate status to persisted WorkflowRun.status values."""

from __future__ import annotations

from typing import Literal


def terminal_status_for_aggregate(overall: Literal["ok", "partial", "error"]) -> str:
    """Executor uses ok/partial/error; persistence uses completed/failed for terminal rows."""
    if overall in {"ok", "partial"}:
        return "completed"
    return "failed"
