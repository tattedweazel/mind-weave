"""Palette API models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain.palette_defaults import default_palette_colors_copy
from app.domain.workflow_palette_resolve import workflow_palette_computed_payload


class PaletteCreate(BaseModel):
    """Request body for creating a new Palette."""

    name: str = Field(min_length=1)
    colors: Dict[str, str] = Field(default_factory=default_palette_colors_copy)


class PaletteUpdate(BaseModel):
    """Request body for updating an existing Palette (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    colors: Optional[Dict[str, str]] = None


class WorkflowPaletteEntryOut(BaseModel):
    """One resolved workflow palette tile (manifest key + persisted coloring)."""

    key: str
    label: str
    kind: str
    effective_color: str


class PalettePublic(BaseModel):
    """Persisted palette row plus manifest-derived projections."""

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    slug: Optional[str] = None
    colors: Dict[str, str]
    created_at: datetime
    updated_at: datetime

    entries: List[WorkflowPaletteEntryOut]
    effective_colors: Dict[str, str]
    warnings: List[str]


def build_palette_public(
    *,
    id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    name: str,
    slug: Optional[str],
    colors: Dict[str, str],
    created_at: datetime,
    updated_at: datetime,
) -> PalettePublic:
    entries_blob, ecs, warns = workflow_palette_computed_payload(colors)
    entries = [
        WorkflowPaletteEntryOut(
            key=row["key"],
            label=row["label"],
            kind=row["kind"],
            effective_color=row["effective_color"],
        )
        for row in entries_blob
    ]

    return PalettePublic(
        id=id,
        user_id=user_id,
        name=name,
        slug=slug,
        colors=dict(colors),
        created_at=created_at,
        updated_at=updated_at,
        entries=entries,
        effective_colors=ecs,
        warnings=sorted(set(warns)),
    )


class PaletteColorsValidateBody(BaseModel):
    """Body for `/palettes/validate` preview — unknown keys strip with warnings."""

    colors: Dict[str, str] = Field(default_factory=dict)


class PaletteValidateResult(BaseModel):
    """Validated / normalized projection without persisting a row."""

    colors: Dict[str, str]
    entries: List[WorkflowPaletteEntryOut]
    effective_colors: Dict[str, str]
    warnings: List[str]


def build_palette_validate_result(colors: Dict[str, str]) -> PaletteValidateResult:
    entries_blob, ecs, warns = workflow_palette_computed_payload(colors)
    entries = [
        WorkflowPaletteEntryOut(
            key=row["key"],
            label=row["label"],
            kind=row["kind"],
            effective_color=row["effective_color"],
        )
        for row in entries_blob
    ]
    return PaletteValidateResult(
        colors=dict(colors),
        entries=entries,
        effective_colors=ecs,
        warnings=sorted(set(warns)),
    )
