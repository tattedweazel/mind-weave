"""
Palettes API
============
CRUD endpoints for Palettes.

  GET    /api/v1/palettes/       — list all Palettes visible to the current user
  POST   /api/v1/palettes/       — create a Palette
  GET    /api/v1/palettes/by-slug/{slug} — get system preset by slug
  GET    /api/v1/palettes/{id}   — get by ID
  PUT    /api/v1/palettes/{id}   — update
  DELETE /api/v1/palettes/{id}   — delete (user-owned only)
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas import PaletteCreate, PaletteUpdate
from app.domain.services.palette_service import PaletteService
from app.persistence.db import get_session
from app.persistence.tables import Palette, User

router = APIRouter()


@router.get("/", response_model=List[Palette])
def list_palettes(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all Palettes visible to the current user (user-owned + system-level)."""
    return PaletteService(session, current_user.id).list_palettes()


@router.post("/", response_model=Palette, status_code=status.HTTP_201_CREATED)
def create_palette(
    data: PaletteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Palette."""
    return PaletteService(session, current_user.id).create_palette(data)


@router.get("/by-slug/{slug}", response_model=Palette)
def get_palette_by_slug(
    slug: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a built-in system palette by its stable slug (e.g. default, slate)."""
    palette = PaletteService(session, current_user.id).get_system_palette_by_slug(slug)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return palette


@router.get("/{id}", response_model=Palette)
def get_palette(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single Palette by ID."""
    palette = PaletteService(session, current_user.id).get_palette(id)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return palette


@router.put("/{id}", response_model=Palette)
def update_palette(
    id: uuid.UUID,
    data: PaletteUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user-owned Palette."""
    palette = PaletteService(session, current_user.id).update_palette(id, data)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return palette


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_palette(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a user-owned Palette."""
    success = PaletteService(session, current_user.id).delete_palette(id)
    if not success:
        raise HTTPException(status_code=404, detail="Palette not found.")
