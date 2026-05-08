"""Palette API models."""

from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.domain.palette_defaults import default_palette_colors_copy


class PaletteCreate(BaseModel):
    """Request body for creating a new Palette."""

    name: str = Field(min_length=1)
    colors: Dict[str, str] = Field(default_factory=default_palette_colors_copy)


class PaletteUpdate(BaseModel):
    """Request body for updating an existing Palette (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    colors: Optional[Dict[str, str]] = None
