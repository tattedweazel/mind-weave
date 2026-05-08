"""Sandbox simulation API (document-backed sessions, server-side ticks)."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.domain.services.sandbox_service import SandboxService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class SandboxSessionCreate(BaseModel):
    workflow_id: Optional[uuid.UUID] = None


class SandboxTickBody(BaseModel):
    interactions: List[dict[str, Any]] = Field(default_factory=list)
    state_version: int = Field(ge=0)
    workflow_id: Optional[uuid.UUID] = None


class SandboxResizeGridBody(BaseModel):
    width: int
    height: int
    state_version: int = Field(ge=0)


def _ensure_sandbox_enabled() -> None:
    if not getattr(settings, "SANDBOX_ENABLED", True):
        raise HTTPException(status_code=404, detail="Sandbox is disabled")


@router.post("/sessions", response_model=dict[str, Any])
async def create_sandbox_session(
    body: SandboxSessionCreate | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        doc, env = svc.create_session(body.workflow_id if body else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "document_id": str(doc.id),
        "envelope": env.model_dump(mode="json"),
    }


@router.get("/sessions/{document_id}", response_model=dict[str, Any])
async def get_sandbox_session(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    env = svc.get_envelope(document_id)
    if not env:
        raise HTTPException(status_code=404, detail="Sandbox session not found")
    return {"envelope": env.model_dump(mode="json")}


@router.post("/sessions/{document_id}/grid", response_model=dict[str, Any])
async def resize_sandbox_grid(
    document_id: uuid.UUID,
    body: SandboxResizeGridBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Resize the simulation grid. Requires playback paused and matching ``state_version``."""
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        env, ok = svc.resize_grid(
            document_id,
            width=body.width,
            height=body.height,
            client_version=body.state_version,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    if not ok:
        raise HTTPException(status_code=409, detail="state_version mismatch")
    return {"envelope": env.model_dump(mode="json")}


@router.post("/sessions/{document_id}/tick", response_model=dict[str, Any])
async def tick_sandbox_session(
    document_id: uuid.UUID,
    body: SandboxTickBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        env, ok, last_run = await svc.run_tick(
            document_id,
            interactions=body.interactions,
            client_version=body.state_version,
            workflow_id_override=body.workflow_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=409, detail="state_version mismatch")
    payload: dict[str, Any] = {"envelope": env.model_dump(mode="json")}
    if last_run is not None:
        payload["last_workflow_run"] = last_run.model_dump(mode="json")
    else:
        payload["last_workflow_run"] = None
    return payload


@router.get("/starter-workflow-id", response_model=dict[str, str])
async def get_starter_workflow_id(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    return {"workflow_id": str(svc.get_starter_workflow_id())}
