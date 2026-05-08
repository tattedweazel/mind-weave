"""Debug STT proxy (authenticated) — same path as the workflow pipeline uses for transcription."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.config import settings
from app.persistence.tables import User
from app.providers.stt_bridge import SttBridgeError, transcribe_audio_bytes

router = APIRouter()


@router.post("/stt/transcribe", tags=["stt"])
async def transcribe_debug(
    file: UploadFile = File(...),
    task: str = Form("transcribe"),
    language: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Proxy multipart audio to the STT bridge; useful for operator checks without a workflow run."""
    _ = current_user
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(raw) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="audio too large")
    name = (file.filename or "audio.webm").split("/")[-1]
    ctype = (file.content_type or "application/octet-stream").split(";")[0].strip() or "application/octet-stream"
    try:
        return await transcribe_audio_bytes(
            raw,
            task=task,
            language=language,
            filename=name,
            content_type=ctype,
        )
    except SttBridgeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
