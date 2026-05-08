"""FastAPI STT bridge (faster-whisper)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from stt_bridge.config import settings
from stt_bridge.engine import transcribe_bytes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mind Weave STT Bridge", version="0.1.0")

api_key_header = APIKeyHeader(name="X-STT-Bridge-Token", auto_error=False)


def verify_token(x_stt_bridge_token: str | None = Depends(api_key_header)) -> None:
    expected = (settings.STT_BRIDGE_TOKEN or "").strip()
    if not expected:
        return
    if (x_stt_bridge_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-STT-Bridge-Token")


class TranscribeResponse(BaseModel):
    text: str
    segments: list[dict[str, Any]]
    language: str | None = None
    duration_seconds: float | None = None
    model: str


class HealthResponse(BaseModel):
    status: str
    mock: bool
    model: str
    cache_dir: str


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        mock=bool(settings.STT_BRIDGE_MOCK),
        model=settings.STT_MODEL,
        cache_dir=str(settings.STT_CACHE_DIR.resolve()),
    )


@app.post("/v1/transcribe", response_model=TranscribeResponse, dependencies=[Depends(verify_token)])
async def transcribe(
    file: UploadFile = File(...),
    task: str = Form("transcribe"),
    language: str | None = Form(None),
):
    raw = await file.read()
    if not raw or len(raw) == 0:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(raw) > settings.STT_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="audio too large")

    task_clean = (task or "transcribe").strip().lower()
    if task_clean not in ("transcribe", "translate"):
        raise HTTPException(status_code=400, detail="task must be transcribe or translate")
    lang = (language or "").strip() or None

    try:
        result = transcribe_bytes(raw, task=task_clean, language=lang)
    except Exception as e:
        logger.exception("transcribe failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not (result.text or "").strip() and not result.segments:
        raise HTTPException(status_code=400, detail="empty or silent audio")

    return TranscribeResponse(
        text=result.text,
        segments=result.segments,
        language=result.language,
        duration_seconds=result.duration_seconds,
        model=settings.STT_MODEL,
    )
