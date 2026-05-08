"""POST audio for a running workflow (transcribe_audio node)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeWaitKey,
    complete_taken_transcribe_wait,
    take_transcribe_wait,
)
from app.persistence.db import get_session
from app.persistence.tables import User, WorkflowRun

router = APIRouter()


@router.post(
    "/workflow-runs/{run_id}/transcribe-audio",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_transcribe_audio_for_run(
    run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    node_id: str = Form(..., min_length=1),
    for_loop_id: Optional[str] = Form(None),
    for_loop_iteration: int = Form(0),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Deliver recorded audio to unblock the matching ``transcribe_audio`` node in run_stream."""
    run = session.get(WorkflowRun, run_id)
    if not run or run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.status or "") != "running":
        raise HTTPException(status_code=400, detail="Run is not active")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(raw) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="audio too large")

    key = TranscribeWaitKey(
        run_id=run_id,
        node_id=node_id,
        for_loop_id=(for_loop_id or "").strip() or None,
        iteration=int(for_loop_iteration),
    )
    fut = take_transcribe_wait(key)
    if fut is None:
        raise HTTPException(
            status_code=409,
            detail="No pending transcribe step for this run/node (wrong node, loop context, or already delivered)",
        )

    async def deliver_upload_after_response() -> None:
        complete_taken_transcribe_wait(
            fut,
            raw,
            filename=(file.filename or "recording.webm"),
            content_type=(file.content_type or "application/octet-stream"),
        )

    background_tasks.add_task(deliver_upload_after_response)
    return None
