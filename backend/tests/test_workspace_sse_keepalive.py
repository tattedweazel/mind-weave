"""SSE keepalive lines during long Workspace interpret/compose awaits."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.services.workspace_runtime_service import iter_sse_keepalive_lines_while_task_pending


@pytest.mark.asyncio
async def test_iter_sse_keepalive_emits_while_task_runs():
    gate = asyncio.Event()

    async def slow_work() -> int:
        await gate.wait()
        return 42

    task = asyncio.create_task(slow_work())
    lines: list[str] = []

    async def collect() -> None:
        async for line in iter_sse_keepalive_lines_while_task_pending(task, interval_sec=0.05):
            lines.append(line)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0.18)
    gate.set()
    await asyncio.wait_for(collector, timeout=2.0)
    assert task.result() == 42
    assert lines
    assert all(": sse-keepalive" in ln for ln in lines)
