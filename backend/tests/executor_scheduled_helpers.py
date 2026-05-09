"""Test helpers around ``WorkflowExecutor.execute_scheduled_run``."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import WorkflowDefinition, WorkflowRun

# Optional hook so tests can unblock ``input_required`` / transcribe waits *during*
# ``execute_scheduled_run`` (the executor awaits uploads while publishing SSE).
OnSseEventHook = Callable[[str, dict[str, Any]], Any]


async def execute_scheduled_collect_sse(
    executor: WorkflowExecutor,
    wf_row: WorkflowDefinition,
    *,
    persist_run_record: WorkflowRun,
    on_sse_event: OnSseEventHook | None = None,
    **kwargs: Any,
) -> tuple[Any, list[tuple[str, dict[str, Any]]]]:
    collected: list[tuple[str, dict[str, Any]]] = []

    async def sse_publish(en: str, payload: dict[str, object]) -> int:
        p = dict(payload)
        collected.append((en, p))
        if on_sse_event is not None:
            r = on_sse_event(en, p)
            if inspect.isawaitable(r):
                await r
        return len(collected)

    final = await executor.execute_scheduled_run(
        wf_row,
        persist_run_record=persist_run_record,
        sse_publish=sse_publish,
        **kwargs,
    )
    return final, collected
