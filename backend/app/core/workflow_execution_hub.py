"""In-process SSE fan-out for active workflow runs (single API process)."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field

SSE_KEEPALIVE_INTERVAL_SEC = 25.0


def format_sse_payload(event_name: str, payload: dict[str, object]) -> str:
    """One SSE message: optional event line + JSON data + blank terminator."""
    data_json = json.dumps(payload, separators=(",", ":"), default=str)
    return f"event: {event_name}\ndata: {data_json}\n\n"


def sse_comment_keepalive() -> str:
    return ": sse-keepalive\n\n"


@dataclass
class WorkflowRunSubscriber:
    """One connected GET .../events client."""

    queue: asyncio.Queue[str | None]


@dataclass
class WorkflowRunFanout:
    """Per-run broadcaster; callers await publish."""

    run_id: uuid.UUID
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _seq: int = 0
    subscribers: list[WorkflowRunSubscriber] = field(default_factory=list)

    async def subscribe(self, max_queue: int = 256) -> asyncio.Queue[str | None]:
        q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=max_queue)
        async with self._lock:
            self.subscribers.append(WorkflowRunSubscriber(queue=q))
        return q

    async def unsubscribe(self, q: asyncio.Queue[str | None]) -> None:
        async with self._lock:
            self.subscribers = [s for s in self.subscribers if s.queue is not q]

    async def bump_seq_floor(self, floor: int) -> None:
        """Raise the next assigned ``seq`` to at least ``floor`` (e.g. after DB ``last_event_seq``)."""
        async with self._lock:
            self._seq = max(self._seq, int(floor))

    async def replay_event_chunk(self, event_name: str, payload: dict[str, object]) -> str:
        """Assign the next sequential ``seq`` and return SSE text without fan-out."""
        async with self._lock:
            self._seq += 1
            seq = self._seq
            body = dict(payload)
            body["seq"] = seq
            return format_sse_payload(event_name, body)

    async def publish_raw(self, chunk: str) -> None:
        """Send preformatted SSE bytes (e.g. comment keepalive) to subscribers."""
        async with self._lock:
            subs = list(self.subscribers)
        for sub in subs:
            await sub.queue.put(chunk)

    async def publish(self, event_name: str, payload: dict[str, object]) -> int:
        """Assign monotonic seq, format SSE chunk, broadcast to subscribers."""
        async with self._lock:
            self._seq += 1
            seq = self._seq
            body = dict(payload)
            body["seq"] = seq
            chunk = format_sse_payload(event_name, body)
            subs = list(self.subscribers)
        for sub in subs:
            await sub.queue.put(chunk)
        return seq


class WorkflowExecutionHub:
    """Registry of fanouts for runs that still have subscribers or ongoing execution."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, WorkflowRunFanout] = {}
        self._runs_lock = asyncio.Lock()
        self._run_tasks: dict[uuid.UUID, asyncio.Task[object]] = {}
        self._run_tasks_lock = asyncio.Lock()

    async def get_or_create_fanout(self, run_id: uuid.UUID) -> WorkflowRunFanout:
        async with self._runs_lock:
            existing = self._runs.get(run_id)
            if existing is not None:
                return existing
            fanout = WorkflowRunFanout(run_id=run_id)
            self._runs[run_id] = fanout
            return fanout

    async def drop_fanout(self, run_id: uuid.UUID) -> None:
        async with self._runs_lock:
            dead = self._runs.pop(run_id, None)
        if dead is None:
            return
        for sub in list(dead.subscribers):
            await sub.queue.put(None)

    async def register_run_task(self, run_id: uuid.UUID, task: asyncio.Task[object]) -> None:
        async with self._run_tasks_lock:
            self._run_tasks[run_id] = task

    async def unregister_run_task(self, run_id: uuid.UUID) -> None:
        async with self._run_tasks_lock:
            self._run_tasks.pop(run_id, None)

    async def cancel_run_task(self, run_id: uuid.UUID) -> bool:
        """Return True if a non-done background task was canceled."""
        async with self._run_tasks_lock:
            t = self._run_tasks.get(run_id)
        if t is None or t.done():
            return False
        t.cancel()
        return True
