"""Serve and create user-scoped image artifacts (``url_snapshot_artifacts``)."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.services.url_snapshot_cache_service import create_artifact
from app.domain.workflow_executor.image_artifact_ingest import ImageIngestError, validate_and_measure_image_bytes
from app.persistence.db import get_session
from app.persistence.tables import UrlSnapshotArtifact, User

router = APIRouter()


@router.get(
    "/url-snapshot-artifacts/{artifact_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
    summary="Get a user-owned URL snapshot image (workflow capture output)",
)
def get_url_snapshot_artifact(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    row = session.get(UrlSnapshotArtifact, artifact_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found.")
    return Response(
        content=row.image_bytes,
        media_type=row.mime_type or "image/png",
    )


@router.post(
    "/url-snapshot-artifacts",
    summary="Upload an image and store a workflow image artifact (PNG, JPEG, or WebP)",
)
async def create_url_snapshot_artifact(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    data = await file.read()
    try:
        mime, w, h = validate_and_measure_image_bytes(data)
    except ImageIngestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    art = create_artifact(
        session,
        current_user.id,
        data,
        w,
        h,
        final_url="",
        mime_type=mime,
    )
    session.commit()
    session.refresh(art)
    return {
        "artifact_id": str(art.id),
        "mime_type": art.mime_type,
        "width": int(art.width),
        "height": int(art.height),
    }
