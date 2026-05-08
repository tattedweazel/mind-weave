"""Persona API models."""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PersonaListItem(BaseModel):
    """Lightweight response for persona list endpoints (excludes heavy ``system_prompt`` field)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    type: str
    description: str
    default_model: Optional[str] = None
    is_default: bool = False
    creativity: float = 0.2
    suppress_lm_thinking: bool = False
    created_at: datetime
    updated_at: datetime


class PersonaCreate(BaseModel):
    """Request body for creating a new Persona."""

    name: str = Field(min_length=1)
    type: Literal["custom", "system"] = "custom"
    description: str
    system_prompt: str
    default_model: Optional[str] = None
    is_default: bool = False
    creativity: float = 0.2
    suppress_lm_thinking: bool = False


class PersonaUpdate(BaseModel):
    """Request body for updating an existing Persona (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    type: Optional[Literal["custom", "system"]] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    default_model: Optional[str] = None
    is_default: Optional[bool] = None
    creativity: Optional[float] = None
    suppress_lm_thinking: Optional[bool] = None
