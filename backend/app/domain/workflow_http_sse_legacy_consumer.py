"""Map Build ``POST …/runs`` + ``GET …/workflow-runs/{id}/events`` to legacy NDJSON-shaped dicts (for HTTP e2e scripts)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.sse_parse import SseBlockAccumulator
from app.domain.workflow_inprocess_ndjson import sse_events_to_legacy_workflow


async def enqueue_workflow_run(client: httpx.AsyncClient, workflow_id: str, body: dict[str, Any] | None = None) -> str:
    r = await client.post(f"/api/v1/workflow-definitions/{workflow_id}/runs", json=body or {})
    r.raise_for_status()
    rid = r.json().get("run_id")
    if rid is None:
        raise RuntimeError(f"enqueue response missing run_id: {r.text!r}")
    return str(rid)


async def iter_workflow_sse_as_legacy_ndjson_events(
    client: httpx.AsyncClient,
    run_id: str,
    *,
    timeout: httpx.Timeout | None = None,
) -> AsyncIterator[dict[str, Any]]:
    acc = SseBlockAccumulator()
    t = timeout if timeout is not None else httpx.Timeout(None, connect=30.0)
    async with client.stream(
        "GET",
        f"/api/v1/workflow-runs/{run_id}/events",
        timeout=t,
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            for tup in acc.feed_bytes(chunk):
                for legacy_ev in sse_events_to_legacy_workflow([tup]):
                    yield legacy_ev


async def enqueue_and_iterate_build_events(
    client: httpx.AsyncClient,
    workflow_id: str,
    body: dict[str, Any] | None = None,
    *,
    sse_timeout: httpx.Timeout | None = None,
) -> AsyncIterator[dict[str, Any]]:
    rid = await enqueue_workflow_run(client, workflow_id, body)
    async for ev in iter_workflow_sse_as_legacy_ndjson_events(client, rid, timeout=sse_timeout):
        yield ev
