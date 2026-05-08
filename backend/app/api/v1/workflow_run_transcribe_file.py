"""POST an audio file for a running workflow Transcribe File node.

Runtime upload route for the provider-abstracted ``transcribe_file`` skill. Mirrors
``workflow_run_audio_file_input`` byte-for-byte aside from the URL path so the SPA can
route Audio File Input vs Transcribe File uploads to distinct endpoints — which matters
when a single workflow contains both.
"""

from __future__ import annotations

import uuid
from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.logging import logger
from app.domain.audio_file_validation import AudioFileValidationError, validate_audio_upload
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeWaitKey,
    complete_taken_transcribe_wait,
    take_transcribe_wait,
)
from app.persistence.db import get_session
from app.persistence.tables import User, WorkflowRun

router = APIRouter()


@router.post(
    "/workflow-runs/{run_id}/transcribe-file-input",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_transcribe_file_input_for_run(
    run_id: uuid.UUID,
    node_id: str = Form(..., min_length=1),
    for_loop_id: Optional[str] = Form(None),
    for_loop_iteration: int = Form(0),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Deliver a selected audio file to unblock a ``transcribe_file`` node in run_stream."""
    t0 = perf_counter()
    run = session.get(WorkflowRun, run_id)
    if not run or run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.status or "") != "running":
        raise HTTPException(status_code=400, detail="Run is not active")

    logger.info("transcribe_file upload started run_id=%s node_id=%s filename=%s", run_id, node_id, file.filename)
    raw = await file.read()
    try:
        validated = validate_audio_upload(raw, filename=file.filename, content_type=file.content_type)
    except AudioFileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
            detail="No pending transcribe_file step for this run/node (wrong node, loop context, or already delivered)",
        )

    delivered = complete_taken_transcribe_wait(
        fut,
        raw,
        filename=validated.filename,
        content_type=validated.mime_type,
    )
    if not delivered:
        logger.warning("transcribe_file upload delivery failed run_id=%s node_id=%s", run_id, node_id)
        raise HTTPException(
            status_code=409,
            detail="Transcribe file step is no longer waiting for this upload",
        )
    logger.info(
        "transcribe_file upload delivered run_id=%s node_id=%s bytes=%s elapsed_ms=%.1f",
        run_id,
        node_id,
        validated.size_bytes,
        (perf_counter() - t0) * 1000,
    )
    return None
