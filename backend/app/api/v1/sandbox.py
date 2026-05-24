"""Sandbox simulation API (document-backed sessions, server-side ticks)."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.domain.schemas.sandbox import BoardDefinition
from app.domain.services.board_service import BoardService
from app.domain.services.sandbox_service import SandboxService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class SandboxSessionCreate(BaseModel):
    board_id: Optional[uuid.UUID] = None


class SandboxTickBody(BaseModel):
    interactions: List[dict[str, Any]] = Field(default_factory=list)
    state_version: int = Field(ge=0)
    creature_user_actions: Optional[dict[str, dict[str, Any]]] = Field(
        default=None,
        description="Per-creature DecisionIntent payloads for sandbox_prompt_user_action brains",
    )


class SandboxApplyInteractionsBody(BaseModel):
    interactions: List[dict[str, Any]] = Field(default_factory=list)
    state_version: int = Field(ge=0)


class SandboxResizeGridBody(BaseModel):
    width: int
    height: int
    state_version: int = Field(ge=0)


class SandboxSaveBoardBody(BaseModel):
    mode: str = Field(description="'save_as_new' or 'update_source'")
    name: Optional[str] = None
    project_id: Optional[uuid.UUID] = None


class BoardCreateBody(BaseModel):
    name: str
    description: str = ""
    definition: Optional[dict[str, Any]] = None
    project_id: Optional[uuid.UUID] = None


class BoardUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    definition: Optional[dict[str, Any]] = None
    project_id: Optional[uuid.UUID] = None


class BoardDuplicateBody(BaseModel):
    name: Optional[str] = None


def _ensure_sandbox_enabled() -> None:
    if not getattr(settings, "SANDBOX_ENABLED", True):
        raise HTTPException(status_code=404, detail="Sandbox is disabled")


def _board_to_json(row) -> dict[str, Any]:
    import json

    from app.domain.sandbox.empty_board_seed import parse_board_body

    defn = parse_board_body(row.body)
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "is_system": row.is_system,
        "project_id": str(row.project_id) if row.project_id else None,
        "definition": defn.model_dump(mode="json"),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/boards", response_model=dict[str, Any])
async def list_sandbox_boards(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    rows = svc.list_boards()
    return {"boards": [_board_to_json(r) for r in rows]}


@router.post("/boards", response_model=dict[str, Any])
async def create_sandbox_board(
    body: BoardCreateBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    defn = None
    if body.definition is not None:
        try:
            defn = BoardDefinition.model_validate(body.definition)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = svc.create_board(
        name=body.name,
        description=body.description,
        definition=defn,
        project_id=body.project_id,
    )
    return _board_to_json(row)


@router.get("/boards/{board_id}", response_model=dict[str, Any])
async def get_sandbox_board(
    board_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    row = svc.get_board(board_id)
    if not row:
        raise HTTPException(status_code=404, detail="Board not found")
    return _board_to_json(row)


@router.patch("/boards/{board_id}", response_model=dict[str, Any])
async def update_sandbox_board(
    board_id: uuid.UUID,
    body: BoardUpdateBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    defn = None
    if body.definition is not None:
        try:
            defn = BoardDefinition.model_validate(body.definition)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = svc.update_board(
        board_id,
        name=body.name,
        description=body.description,
        definition=defn,
        project_id=body.project_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Board not found or not editable")
    return _board_to_json(row)


@router.delete("/boards/{board_id}", response_model=dict[str, bool])
async def delete_sandbox_board(
    board_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    ok = svc.delete_board(board_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Board not found or not deletable")
    return {"ok": True}


@router.post("/boards/{board_id}/duplicate", response_model=dict[str, Any])
async def duplicate_sandbox_board(
    board_id: uuid.UUID,
    body: BoardDuplicateBody | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = BoardService(session, current_user.id)
    row = svc.duplicate_board(board_id, name=body.name if body else None)
    if not row:
        raise HTTPException(status_code=404, detail="Board not found")
    return _board_to_json(row)


@router.post("/sessions", response_model=dict[str, Any])
async def create_sandbox_session(
    body: SandboxSessionCreate | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        doc, env = svc.create_session(body.board_id if body else None)
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


@router.post("/sessions/{document_id}/save-board", response_model=dict[str, Any])
async def save_sandbox_session_as_board(
    document_id: uuid.UUID,
    body: SandboxSaveBoardBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        row = svc.save_session_as_board(
            document_id,
            mode=body.mode,
            name=body.name,
            project_id=body.project_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    return _board_to_json(row)


@router.post("/sessions/{document_id}/interactions", response_model=dict[str, Any])
async def apply_sandbox_interactions(
    document_id: uuid.UUID,
    body: SandboxApplyInteractionsBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_sandbox_enabled()
    svc = SandboxService(session, current_user.id)
    try:
        env, ok = svc.apply_interactions(
            document_id,
            interactions=body.interactions,
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
        env, ok, last_runs = await svc.run_tick(
            document_id,
            interactions=body.interactions,
            client_version=body.state_version,
            creature_user_actions=body.creature_user_actions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=409, detail="state_version mismatch")
    payload: dict[str, Any] = {"envelope": env.model_dump(mode="json")}
    payload["last_workflow_runs"] = {
        cid: (run.model_dump(mode="json") if run is not None else None)
        for cid, run in last_runs.items()
    }
    return payload
