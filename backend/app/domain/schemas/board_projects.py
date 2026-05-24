"""Board project (folder) API models."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BoardProjectCreate(BaseModel):
    """Request body for creating a board project folder."""

    name: str = Field(min_length=1, max_length=200)
    sort_order: Optional[int] = None


class BoardProjectUpdate(BaseModel):
    """Request body for updating a board project folder."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sort_order: Optional[int] = None


class BoardProjectRead(BaseModel):
    """Response body for a persisted board project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    sort_order: int
    board_count: int = 0
    created_at: datetime
    updated_at: datetime
