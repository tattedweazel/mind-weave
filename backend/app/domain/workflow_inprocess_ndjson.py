"""Consume ``execute_scheduled_run`` as NDJSON-era event dicts (for scripts and tooling)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlmodel import Session

from app.domain.workflow_sse_ndjson_compat import sse_tuple_to_ndjson_like_event
from app.persistence.tables import WorkflowRun, utc_now

if TYPE_CHECKING:
    from app.domain.services.workflow_executor import WorkflowExecutor
    from app.persistence.tables import WorkflowDefinition


def start_persisted_run_row(
    session: Session,
    *,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WorkflowRun:
    """Insert a persisted run row in ``running`` state (mirrors ``execute_workflow_run_job`` prelude)."""
    row = WorkflowRun(workflow_id=workflow_id, started_by_user_id=user_id, status="queued")
    session.add(row)
    session.commit()
    session.refresh(row)
    row.status = "running"
    if row.started_at is None:
        row.started_at = utc_now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


async def iterate_scheduled_run_ndjson_dicts(
    executor: WorkflowExecutor,
    wf_row: WorkflowDefinition,
    *,
    persist_run_record: WorkflowRun,
    input_overrides: dict[str, Any] | None = None,
    output_overrides_map: dict[str, Any] | None = None,
    execution_time_zone: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    seq_counter = 0

    async def sse_publish(en: str, payload: dict[str, object]) -> int:
        nonlocal seq_counter
        seq_counter += 1
        pl: dict[str, Any] = {str(k): v for k, v in payload.items()}
        pl["seq"] = seq_counter
        row = sse_tuple_to_ndjson_like_event(en, pl)
        if row is not None:
            await queue.put(row)
        return seq_counter

    async def sse_raw(_line: str) -> None:
        return None

    async def runner() -> None:
        try:
            await executor.execute_scheduled_run(
                wf_row,
                persist_run_record=persist_run_record,
                input_overrides=input_overrides,
                output_overrides_map=output_overrides_map,
                execution_time_zone=execution_time_zone,
                sse_publish=sse_publish,
                sse_raw=sse_raw,
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        await task


def sse_events_to_legacy_workflow(events: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for ev_name, payload in events:
        row = sse_tuple_to_ndjson_like_event(ev_name, payload)
        if row is not None:
            mapped.append(row)
    return mapped
