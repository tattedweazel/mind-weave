"""In-memory registry so streaming workflow runs can await Broadcast Message acknowledgements.

Single-process only; multiple API workers require a shared store (not in MVP).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

# (run_id, node_id, for_loop_id_norm, iteration) -> Future[None]
_pending: dict[tuple[uuid.UUID, str, str, int], asyncio.Future[None]] = {}


@dataclass(frozen=True)
class BroadcastAckWaitKey:
    run_id: uuid.UUID
    node_id: str
    for_loop_id: Optional[str]
    iteration: int


def _norm_loop(fid: Optional[str]) -> str:
    return (fid or "").strip()


def register_broadcast_ack_wait(key: BroadcastAckWaitKey) -> asyncio.Future[None]:
    loop = asyncio.get_running_loop()
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    if k in _pending:
        raise RuntimeError(f"duplicate broadcast ack wait for {k}")
    fut: asyncio.Future[None] = loop.create_future()
    _pending[k] = fut
    return fut


def take_broadcast_ack_wait(key: BroadcastAckWaitKey) -> asyncio.Future[None] | None:
    """Reserve a pending wait without completing it yet."""
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    fut = _pending.pop(k, None)
    if fut is None:
        return None
    if fut.done():
        return None
    return fut


def complete_taken_broadcast_ack_wait(fut: asyncio.Future[None]) -> bool:
    """Complete a wait previously reserved with ``take_broadcast_ack_wait``."""
    if fut.done():
        return False
    fut.set_result(None)
    return True


def cancel_broadcast_ack_wait(key: BroadcastAckWaitKey) -> None:
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    fut = _pending.pop(k, None)
    if fut is not None and not fut.done():
        fut.cancel()
