"""
Personas API
============
CRUD endpoints for Personas.

  GET    /api/v1/personas/       — list all Personas visible to the current user
  POST   /api/v1/personas/       — create a Persona
  GET    /api/v1/personas/{id}   — get by ID
  PUT    /api/v1/personas/{id}   — update
  DELETE /api/v1/personas/{id}   — delete (user-owned only)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas import PersonaCreate, PersonaListItem, PersonaUpdate
from app.domain.services.persona_service import PersonaService
from app.persistence.db import get_session
from app.persistence.tables import Persona, User

router = APIRouter()


@router.get("/", response_model=List[PersonaListItem])
def list_personas(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all Personas visible to the current user (slim, without system_prompt)."""
    return PersonaService(session, current_user.id).list_personas()


@router.post("/", response_model=Persona, status_code=status.HTTP_201_CREATED)
def create_persona(
    data: PersonaCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Persona. Name must be unique."""
    svc = PersonaService(session, current_user.id)
    if svc.get_persona_by_name(data.name):
        raise HTTPException(status_code=400, detail="A Persona with that name already exists.")
    return svc.create_persona(data)


@router.get("/{id}", response_model=Persona)
def get_persona(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single Persona by ID."""
    persona = PersonaService(session, current_user.id).get_persona(id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found.")
    return persona


@router.put("/{id}", response_model=Persona)
def update_persona(
    id: uuid.UUID,
    data: PersonaUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user-owned Persona."""
    svc = PersonaService(session, current_user.id)
    if data.name:
        existing = svc.get_persona_by_name(data.name)
        if existing and existing.id != id:
            raise HTTPException(status_code=400, detail="A Persona with that name already exists.")
    persona = svc.update_persona(id, data)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found.")
    return persona


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_persona(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a user-owned Persona."""
    success = PersonaService(session, current_user.id).delete_persona(id)
    if not success:
        raise HTTPException(status_code=404, detail="Persona not found.")
