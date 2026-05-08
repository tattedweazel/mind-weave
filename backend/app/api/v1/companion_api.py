"""Companion and memory APIs."""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.workspace_workflow_allowlist import validate_enabled_workflow_ids
from app.core.config import settings
from app.domain.schemas.workspace_api import (
    CompanionRead,
    CompanionUpdate,
    MemoryApproveBody,
    MemoryEntryRead,
)
from app.domain.services.companion_service import CompanionService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter(prefix="/companion", tags=["companion"])


def _ensure_workspace_enabled() -> None:
    if not getattr(settings, "WORKSPACE_ENABLED", True):
        raise HTTPException(status_code=404, detail="Workspace is disabled")


@router.get("/", response_model=CompanionRead)
def get_companion(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    row = CompanionService(session, current_user.id).get_or_create_companion()
    return CompanionRead.model_validate(row)


@router.put("/", response_model=CompanionRead)
def update_companion(
    data: CompanionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    svc = CompanionService(session, current_user.id)
    patch = data.model_dump(exclude_unset=True)
    if "enabled_workflow_ids" in patch:
        validate_enabled_workflow_ids(session, current_user.id, patch["enabled_workflow_ids"])
    row = svc.apply_companion_patch(patch)
    return CompanionRead.model_validate(row)


@router.get("/memory", response_model=List[MemoryEntryRead])
def list_memory(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    approval_status: str | None = None,
):
    _ensure_workspace_enabled()
    rows = CompanionService(session, current_user.id).list_memory_entries(approval_status=approval_status)
    return [MemoryEntryRead.model_validate(r) for r in rows]


@router.post("/memory/{memory_id}/decision", response_model=MemoryEntryRead)
def memory_decision(
    memory_id: uuid.UUID,
    body: MemoryApproveBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    approved = body.decision == "approved"
    row = CompanionService(session, current_user.id).set_memory_approval(memory_id, approved=approved)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found.")
    return MemoryEntryRead.model_validate(row)
