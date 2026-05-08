"""User-owned audio file artifacts for the Audio File Input workflow skill."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.audio_file_validation import AudioFileValidationError, validate_audio_upload
from app.domain.schemas.audio_file_artifacts import AudioFileArtifactRead
from app.domain.services.audio_file_artifact_service import AudioFileArtifactService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter()


@router.get("/", response_model=list[AudioFileArtifactRead])
def list_audio_file_artifacts(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = AudioFileArtifactService(session, current_user.id).list_artifacts()
    return [AudioFileArtifactRead.model_validate(r) for r in rows]


@router.post("/", response_model=AudioFileArtifactRead, status_code=status.HTTP_201_CREATED)
async def create_audio_file_artifact(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    try:
        validated = validate_audio_upload(raw, filename=file.filename, content_type=file.content_type)
    except AudioFileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    row = AudioFileArtifactService(session, current_user.id).create(raw, validated)
    return AudioFileArtifactRead.model_validate(row)


@router.get("/{artifact_id}", response_model=AudioFileArtifactRead)
def get_audio_file_artifact(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = AudioFileArtifactService(session, current_user.id).get(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return AudioFileArtifactRead.model_validate(row)


@router.get("/{artifact_id}/audio")
def get_audio_file_artifact_audio(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = AudioFileArtifactService(session, current_user.id).get(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return Response(content=row.audio_bytes, media_type=row.mime_type or "application/octet-stream")


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audio_file_artifact(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    ok = AudioFileArtifactService(session, current_user.id).delete(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Audio file not found.")
