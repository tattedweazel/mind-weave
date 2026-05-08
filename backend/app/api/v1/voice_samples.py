"""
Voice Samples API
=================
User-owned reference clips for Qwen3-TTS voice clone (Base model at workflow run time).
Voice Design preview uses a ready VoiceDesign artifact; persistence stores WAV + ref_text.
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas.voice_samples import (
    VoiceDesignPreviewRequest,
    VoiceDesignPreviewResponse,
    VoiceSampleCreate,
    VoiceSampleDetail,
    VoiceSampleListItem,
)
from app.domain.services.voice_sample_service import VoiceSampleService
from app.persistence.db import get_session
from app.persistence.tables import TtsModelArtifact, User
from app.providers.tts_bridge import TtsBridgeError, synthesize_wav

router = APIRouter()


def _ready_design_artifact(session: Session, design_model_id: uuid.UUID) -> TtsModelArtifact:
    art = session.get(TtsModelArtifact, design_model_id)
    if art is None:
        raise HTTPException(status_code=404, detail="TTS model not found.")
    if art.status != "ready" or not (art.local_key or "").strip():
        raise HTTPException(status_code=400, detail=f"TTS model is not ready (status={art.status}).")
    return art


@router.get("/", response_model=list[VoiceSampleListItem])
def list_voice_samples(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = VoiceSampleService(session, current_user.id).list_samples()
    return [VoiceSampleListItem.model_validate(r) for r in rows]


@router.post("/preview-design", response_model=VoiceDesignPreviewResponse)
async def preview_voice_design(
    body: VoiceDesignPreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # auth only
    art = _ready_design_artifact(session, body.design_model_id)
    opts: dict = {
        "language": (body.language or "English").strip() or "English",
        "instruct": (body.instruct or "").strip() or "Speak clearly.",
    }
    try:
        wav = await synthesize_wav(art.engine, art.local_key, body.text.strip(), opts)
    except TtsBridgeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    b64 = base64.b64encode(wav).decode("ascii")
    return VoiceDesignPreviewResponse(mime_type="audio/wav", audio_base64=b64)


@router.post("/", response_model=VoiceSampleDetail, status_code=status.HTTP_201_CREATED)
def create_voice_sample(
    data: VoiceSampleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = VoiceSampleService(session, current_user.id)
    try:
        row = svc.create(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return VoiceSampleDetail.model_validate(row)


@router.get("/{sample_id}", response_model=VoiceSampleDetail)
def get_voice_sample(
    sample_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = VoiceSampleService(session, current_user.id).get(sample_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Voice sample not found.")
    return VoiceSampleDetail.model_validate(row)


@router.get("/{sample_id}/audio")
def get_voice_sample_audio(
    sample_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = VoiceSampleService(session, current_user.id).get(sample_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Voice sample not found.")
    return Response(content=row.ref_audio, media_type="audio/wav")


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice_sample(
    sample_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    ok = VoiceSampleService(session, current_user.id).delete(sample_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Voice sample not found.")
