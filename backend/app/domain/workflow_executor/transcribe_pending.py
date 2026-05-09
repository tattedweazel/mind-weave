"""In-memory registry so workflow runs (`GET …/events` / executor) can await browser-uploaded audio for STT nodes.

Single-process only; multiple API workers require a shared store (not in MVP).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

# (run_id, node_id, for_loop_id_norm, iteration) -> Future[TranscribeUpload]
_pending: dict[tuple[uuid.UUID, str, str, int], asyncio.Future["TranscribeUpload"]] = {}


@dataclass(frozen=True)
class TranscribeUpload:
    data: bytes
    filename: str = "audio.webm"
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class TranscribeWaitKey:
    run_id: uuid.UUID
    node_id: str
    for_loop_id: Optional[str]
    iteration: int


def _norm_loop(fid: Optional[str]) -> str:
    return (fid or "").strip()


def register_transcribe_wait(key: TranscribeWaitKey) -> asyncio.Future[TranscribeUpload]:
    loop = asyncio.get_running_loop()
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    if k in _pending:
        raise RuntimeError(f"duplicate transcribe wait for {k}")
    fut: asyncio.Future[TranscribeUpload] = loop.create_future()
    _pending[k] = fut
    return fut


def complete_transcribe_wait(
    key: TranscribeWaitKey,
    data: bytes,
    *,
    filename: str = "audio.webm",
    content_type: str = "application/octet-stream",
) -> bool:
    fut = take_transcribe_wait(key)
    if fut is None:
        return False
    return complete_taken_transcribe_wait(fut, data, filename=filename, content_type=content_type)


def take_transcribe_wait(key: TranscribeWaitKey) -> asyncio.Future[TranscribeUpload] | None:
    """Reserve a pending wait without completing it yet.

    HTTP upload routes use this so they can return the 204 response before
    resuming potentially long STT work on the streaming response.
    """
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    fut = _pending.pop(k, None)
    if fut is None:
        return None
    if fut.done():
        return None
    return fut


def complete_taken_transcribe_wait(
    fut: asyncio.Future[TranscribeUpload],
    data: bytes,
    *,
    filename: str = "audio.webm",
    content_type: str = "application/octet-stream",
) -> bool:
    """Complete a wait previously reserved with ``take_transcribe_wait``."""
    if fut.done():
        return False
    fut.set_result(TranscribeUpload(data=data, filename=filename, content_type=content_type))
    return True


def cancel_transcribe_wait(key: TranscribeWaitKey) -> None:
    k = (key.run_id, key.node_id, _norm_loop(key.for_loop_id), int(key.iteration))
    fut = _pending.pop(k, None)
    if fut is not None and not fut.done():
        fut.cancel()
