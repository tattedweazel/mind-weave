"""Per-run ephemeral outputs for auxiliary source handles (e.g. For Loop ``summary``)."""

from contextvars import ContextVar
from typing import Any

_for_loop_summaries_ctx: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar("for_loop_summaries", default=None)


def attach_for_loop_summaries_token() -> Any:
    """Return a ContextVar ``set`` token; caller must reset in ``finally``."""
    return _for_loop_summaries_ctx.set({})


def reset_for_loop_summaries_token(token: Any) -> None:
    _for_loop_summaries_ctx.reset(token)


def record_for_loop_summary(node_id: str, summary: dict[str, Any]) -> None:
    store = _for_loop_summaries_ctx.get()
    if store is not None:
        store[node_id] = summary


def get_for_loop_summary(node_id: str) -> dict[str, Any] | None:
    store = _for_loop_summaries_ctx.get()
    if store is None:
        return None
    raw = store.get(node_id)
    return dict(raw) if isinstance(raw, dict) else None
