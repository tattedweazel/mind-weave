"""TTS model registry: admin mutates; any authenticated user lists ready models for workflows."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.api.deps import get_current_user, require_admin
from app.persistence.db import get_session
from app.persistence.tables import TtsModelArtifact, User, utc_now
from app.providers.tts_bridge import TtsBridgeError, pull_model

router = APIRouter()


class TtsModelSource(BaseModel):
    kind: Literal["huggingface_repo"] = "huggingface_repo"
    repo_id: str = Field(..., min_length=1, max_length=256)
    revision: str | None = None


class TtsModelCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)
    engine: str = Field(..., min_length=1, max_length=64)
    source: TtsModelSource


class TtsModelRead(BaseModel):
    id: uuid.UUID
    display_name: str
    engine: str
    source: dict[str, Any]
    local_key: str
    status: str
    error_message: str | None
    created_at: Any
    updated_at: Any


def _truncate_err(msg: str, max_len: int = 2000) -> str:
    s = (msg or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _artifact_to_read(row: TtsModelArtifact) -> TtsModelRead:
    return TtsModelRead(
        id=row.id,
        display_name=row.display_name,
        engine=row.engine,
        source=dict(row.source or {}),
        local_key=row.local_key,
        status=row.status,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/tts-models", response_model=list[TtsModelRead])
def list_ready_tts_models(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(TtsModelArtifact).where(col(TtsModelArtifact.status) == "ready").order_by(col(TtsModelArtifact.display_name))
    ).all()
    return [_artifact_to_read(r) for r in rows]


@router.get("/tts-models/registry", response_model=list[TtsModelRead])
def list_all_tts_models_admin(
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    rows = session.exec(select(TtsModelArtifact).order_by(col(TtsModelArtifact.created_at))).all()
    return [_artifact_to_read(r) for r in rows]


@router.post("/tts-models", response_model=TtsModelRead, status_code=status.HTTP_201_CREATED)
async def create_tts_model_admin(
    body: TtsModelCreate,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    eng = body.engine.strip()
    if eng not in ("qwen_torch", "qwen_mlx"):
        raise HTTPException(status_code=400, detail="Unsupported engine")
    row = TtsModelArtifact(
        display_name=body.display_name.strip(),
        engine=eng,
        source=body.source.model_dump(mode="json"),
        local_key="",
        status="pending",
        error_message=None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    try:
        local_key = await pull_model(eng, str(row.id), row.source)
    except TtsBridgeError as e:
        row.status = "failed"
        row.error_message = _truncate_err(str(e))
        row.updated_at = utc_now()
        session.add(row)
        session.commit()
        session.refresh(row)
        raise HTTPException(status_code=502, detail=str(e)) from e

    row.local_key = local_key
    row.status = "ready"
    row.error_message = None
    row.updated_at = utc_now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _artifact_to_read(row)


@router.post("/tts-models/{artifact_id}/pull", response_model=TtsModelRead)
async def pull_tts_model_admin(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    row = session.get(TtsModelArtifact, artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown TTS model")
    row.status = "pending"
    row.error_message = None
    row.updated_at = utc_now()
    session.add(row)
    session.commit()

    try:
        local_key = await pull_model(row.engine, str(row.id), dict(row.source or {}))
    except TtsBridgeError as e:
        row.status = "failed"
        row.error_message = _truncate_err(str(e))
        row.updated_at = utc_now()
        session.add(row)
        session.commit()
        session.refresh(row)
        raise HTTPException(status_code=502, detail=str(e)) from e

    row.local_key = local_key
    row.status = "ready"
    row.error_message = None
    row.updated_at = utc_now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _artifact_to_read(row)


@router.delete("/tts-models/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tts_model_admin(
    artifact_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    row = session.get(TtsModelArtifact, artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown TTS model")
    session.delete(row)
    session.commit()
    return None
