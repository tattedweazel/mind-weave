"""
Workflow Projects API
=====================
CRUD for per-user workflow folders (Projects). The **Shared** folder is reserved
and created automatically.

  GET    /api/v1/workflow-projects/        — list folders + workflow counts
  POST   /api/v1/workflow-projects/        — create
  PATCH  /api/v1/workflow-projects/{id}     — rename / reorder
  DELETE /api/v1/workflow-projects/{id}     — delete (workflows move to Shared)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas import WorkflowProjectCreate, WorkflowProjectRead, WorkflowProjectUpdate
from app.domain.services.workflow_project_service import WorkflowProjectService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter()


def _to_read(svc: WorkflowProjectService, row) -> WorkflowProjectRead:
    return WorkflowProjectRead(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        sort_order=row.sort_order,
        workflow_count=svc.count_workflows(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=List[WorkflowProjectRead])
def list_workflow_projects(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List workflow project folders for the current user (includes Shared)."""
    svc = WorkflowProjectService(session, current_user.id)
    rows = svc.list_projects()
    return [_to_read(svc, p) for p in rows]


@router.post("/", response_model=WorkflowProjectRead, status_code=status.HTTP_201_CREATED)
def create_workflow_project(
    data: WorkflowProjectCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new project folder."""
    svc = WorkflowProjectService(session, current_user.id)
    try:
        row = svc.create_project(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_read(svc, row)


@router.patch("/{id}", response_model=WorkflowProjectRead)
def update_workflow_project(
    id: uuid.UUID,
    data: WorkflowProjectUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Rename or reorder a project folder."""
    svc = WorkflowProjectService(session, current_user.id)
    try:
        row = svc.update_project(id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_read(svc, row)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_project(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a folder; workflows inside are moved to Shared."""
    svc = WorkflowProjectService(session, current_user.id)
    try:
        ok = svc.delete_project(id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return None
