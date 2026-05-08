"""System palette (app-wide theme) API models."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.domain.system_palette_defaults import default_system_theme_colors_copy


class SystemPaletteCreate(BaseModel):
    """Request body for creating a user-owned system palette."""

    name: str = Field(min_length=1)
    colors: Dict[str, Any] = Field(default_factory=default_system_theme_colors_copy)


class SystemPaletteUpdate(BaseModel):
    """Request body for updating a user-owned system palette."""

    name: Optional[str] = Field(default=None, min_length=1)
    colors: Optional[Dict[str, Any]] = None
