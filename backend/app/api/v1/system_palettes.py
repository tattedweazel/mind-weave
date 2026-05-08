"""
System palettes API
===================
App-wide UI themes (light/dark semantic tokens). Built-ins are readable by all; mutations are user-owned only.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas import SystemPaletteCreate, SystemPaletteUpdate
from app.domain.services.system_palette_service import SystemPaletteService
from app.persistence.db import get_session
from app.persistence.tables import SystemPalette, User

router = APIRouter()


@router.get("/", response_model=List[SystemPalette])
def list_system_palettes(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return SystemPaletteService(session, current_user.id).list_system_palettes()


@router.post("/", response_model=SystemPalette, status_code=status.HTTP_201_CREATED)
def create_system_palette(
    data: SystemPaletteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return SystemPaletteService(session, current_user.id).create_system_palette(data)


@router.get("/by-slug/{slug}", response_model=SystemPalette)
def get_system_palette_by_slug(
    slug: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = SystemPaletteService(session, current_user.id).get_builtin_system_palette_by_slug(slug)
    if not row:
        raise HTTPException(status_code=404, detail="System theme not found.")
    return row


@router.get("/{id}", response_model=SystemPalette)
def get_system_palette(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = SystemPaletteService(session, current_user.id).get_system_palette(id)
    if not row:
        raise HTTPException(status_code=404, detail="System theme not found.")
    return row


@router.put("/{id}", response_model=SystemPalette)
def update_system_palette(
    id: uuid.UUID,
    data: SystemPaletteUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = SystemPaletteService(session, current_user.id).update_system_palette(id, data)
    if not row:
        raise HTTPException(status_code=404, detail="System theme not found.")
    return row


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_palette(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    ok = SystemPaletteService(session, current_user.id).delete_system_palette(id)
    if not ok:
        raise HTTPException(status_code=404, detail="System theme not found.")
