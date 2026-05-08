"""
Structures API
==============
CRUD endpoints for Structures.

  GET    /api/v1/structures/       — list all Structures visible to the current user
  POST   /api/v1/structures/       — create a Structure
  GET    /api/v1/structures/{id}   — get by ID
  PUT    /api/v1/structures/{id}   — update
  DELETE /api/v1/structures/{id}   — delete (user-owned only)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas import StructureCreate, StructureUpdate
from app.domain.services.structure_service import StructureService
from app.persistence.db import get_session
from app.persistence.tables import Structure, User

router = APIRouter()


@router.get("/", response_model=List[Structure])
def list_structures(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all Structures visible to the current user (user-owned + system-level)."""
    return StructureService(session, current_user.id).list_structures()


@router.post("/", response_model=Structure, status_code=status.HTTP_201_CREATED)
def create_structure(
    data: StructureCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Structure. Name must be unique."""
    svc = StructureService(session, current_user.id)
    if svc.get_structure_by_name(data.name):
        raise HTTPException(status_code=400, detail="A Structure with that name already exists.")
    return svc.create_structure(data)


@router.get("/{id}", response_model=Structure)
def get_structure(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single Structure by ID."""
    structure = StructureService(session, current_user.id).get_structure(id)
    if not structure:
        raise HTTPException(status_code=404, detail="Structure not found.")
    return structure


@router.put("/{id}", response_model=Structure)
def update_structure(
    id: uuid.UUID,
    data: StructureUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user-owned Structure."""
    svc = StructureService(session, current_user.id)
    if data.name:
        existing = svc.get_structure_by_name(data.name)
        if existing and existing.id != id:
            raise HTTPException(status_code=400, detail="A Structure with that name already exists.")
    structure = svc.update_structure(id, data)
    if not structure:
        raise HTTPException(status_code=404, detail="Structure not found.")
    return structure


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_structure(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a user-owned Structure."""
    success = StructureService(session, current_user.id).delete_structure(id)
    if not success:
        raise HTTPException(status_code=404, detail="Structure not found.")
