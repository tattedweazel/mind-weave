"""Workflow project (folder) API models."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowProjectCreate(BaseModel):
    """Request body for creating a workflow project folder."""

    name: str = Field(min_length=1, max_length=200)
    sort_order: Optional[int] = None


class WorkflowProjectUpdate(BaseModel):
    """Request body for updating a workflow project folder."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sort_order: Optional[int] = None


class WorkflowProjectRead(BaseModel):
    """Response body for a persisted workflow project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    sort_order: int
    workflow_count: int = 0
    created_at: datetime
    updated_at: datetime
