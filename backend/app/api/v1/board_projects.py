"""
Board Projects API
==================
CRUD for per-user board folders (Projects). The **Shared** folder is reserved
and created automatically.

  GET    /api/v1/board-projects/        — list folders + board counts
  POST   /api/v1/board-projects/        — create
  PATCH  /api/v1/board-projects/{id}     — rename / reorder
  DELETE /api/v1/board-projects/{id}     — delete folder (non-empty requires delete_boards=true)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas.board_projects import BoardProjectCreate, BoardProjectRead, BoardProjectUpdate
from app.domain.services.board_project_service import BoardProjectService
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter()


def _to_read(svc: BoardProjectService, row) -> BoardProjectRead:
    return BoardProjectRead(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        sort_order=row.sort_order,
        board_count=svc.count_boards(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=List[BoardProjectRead])
def list_board_projects(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List board project folders for the current user (includes Shared)."""
    svc = BoardProjectService(session, current_user.id)
    rows = svc.list_projects()
    return [_to_read(svc, p) for p in rows]


@router.post("/", response_model=BoardProjectRead, status_code=status.HTTP_201_CREATED)
def create_board_project(
    data: BoardProjectCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new board project folder."""
    svc = BoardProjectService(session, current_user.id)
    try:
        row = svc.create_project(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_read(svc, row)


@router.patch("/{id}", response_model=BoardProjectRead)
def update_board_project(
    id: uuid.UUID,
    data: BoardProjectUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Rename or reorder a board project folder."""
    svc = BoardProjectService(session, current_user.id)
    try:
        row = svc.update_project(id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_read(svc, row)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board_project(
    id: uuid.UUID,
    delete_boards: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a folder. Non-empty folders require ``delete_boards=true`` to cascade-delete boards."""
    svc = BoardProjectService(session, current_user.id)
    try:
        ok = svc.delete_project(id, delete_boards=delete_boards)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("Project is not empty"):
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return None
