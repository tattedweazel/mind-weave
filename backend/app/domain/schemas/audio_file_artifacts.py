"""Pydantic schemas for user-owned workflow audio file artifacts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AudioFileArtifactRead(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
