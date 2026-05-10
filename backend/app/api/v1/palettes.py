"""
Palettes API
============
CRUD endpoints for Palettes.

  GET    /api/v1/palettes/       — list all Palettes visible to the current user
  POST   /api/v1/palettes/       — create a Palette
  POST   /api/v1/palettes/validate — normalize/import preview (+ strip unknown keys)
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
from app.domain.schemas.palettes import (
    PaletteColorsValidateBody,
    PalettePublic,
    PaletteValidateResult,
    build_palette_validate_result,
)
from app.domain.services.palette_service import PaletteService
from app.domain.workflow_palette_validate import coerce_validate_palette_import
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter()


def _raise_palette_value_error(exc: ValueError) -> None:
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/", response_model=List[PalettePublic])
def list_palettes(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all Palettes visible to the current user (user-owned + system-level)."""
    rows = PaletteService(session, current_user.id).list_palettes()
    return [PaletteService.palette_public(row) for row in rows]


@router.post("/validate", response_model=PaletteValidateResult)
def validate_palette_import(
    data: PaletteColorsValidateBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Normalize palette JSON from imports: unknown keys strip with warnings; invalid CSS → 422.
    Persisted palettes still require strict payloads on POST/PUT.
    """
    _ = session, current_user
    try:
        sanitized, warns = coerce_validate_palette_import(data.colors or {})
        result = build_palette_validate_result(sanitized)
    except ValueError as exc:
        _raise_palette_value_error(exc)

    merged_warns = sorted(set(result.warnings + warns))
    return PaletteValidateResult(
        colors=result.colors,
        entries=result.entries,
        effective_colors=result.effective_colors,
        warnings=merged_warns,
    )


@router.post("/", response_model=PalettePublic, status_code=status.HTTP_201_CREATED)
def create_palette(
    data: PaletteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Palette."""
    try:
        row = PaletteService(session, current_user.id).create_palette(data)
    except ValueError as exc:
        _raise_palette_value_error(exc)
    return PaletteService.palette_public(row)


@router.get("/by-slug/{slug}", response_model=PalettePublic)
def get_palette_by_slug(
    slug: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a built-in system palette by its stable slug (e.g. default, slate)."""
    palette = PaletteService(session, current_user.id).get_system_palette_by_slug(slug)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return PaletteService.palette_public(palette)


@router.get("/{id}", response_model=PalettePublic)
def get_palette(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single Palette by ID."""
    palette = PaletteService(session, current_user.id).get_palette(id)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return PaletteService.palette_public(palette)


@router.put("/{id}", response_model=PalettePublic)
def update_palette(
    id: uuid.UUID,
    data: PaletteUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user-owned Palette."""
    try:
        palette = PaletteService(session, current_user.id).update_palette(id, data)
    except ValueError as exc:
        _raise_palette_value_error(exc)
    if not palette:
        raise HTTPException(status_code=404, detail="Palette not found.")
    return PaletteService.palette_public(palette)


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
