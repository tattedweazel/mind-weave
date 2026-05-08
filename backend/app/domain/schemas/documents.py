"""Document API models."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentListItem(BaseModel):
    """Lightweight response for document list endpoints (excludes heavy ``body`` field)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    description: str = ""
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    """Request body for creating a new Document."""

    name: str = Field(min_length=1)
    description: str = ""
    body: str = ""


class DocumentUpdate(BaseModel):
    """Request body for updating an existing Document (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    body: Optional[str] = None
