"""Pydantic schemas for Voice Sample CRUD and Voice Design preview."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VoiceSampleListItem(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VoiceSampleDetail(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    ref_text: str
    instruct: str
    design_model_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VoiceSampleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    ref_text: str = Field(..., min_length=1)
    language: str = Field(default="English", max_length=64)
    instruct: str = Field(default="", max_length=50_000)
    design_model_id: Optional[uuid.UUID] = None
    audio_base64: str = Field(..., min_length=1, description="WAV bytes as standard base64")


class VoiceDesignPreviewRequest(BaseModel):
    design_model_id: uuid.UUID
    text: str = Field(..., min_length=1)
    language: str = Field(default="English", max_length=64)
    instruct: str = Field(default="", max_length=50_000)


class VoiceDesignPreviewResponse(BaseModel):
    mime_type: str = "audio/wav"
    audio_base64: str
