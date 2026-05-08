"""Workflow definition API models."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .graph_nodes import GraphEdge


class WorkflowGraph(BaseModel):
    """The validated graph structure stored inside a WorkflowDefinition."""

    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    schema_version: Optional[int] = Field(
        default=None,
        description="Graph shape version for migrations; omitted or null means legacy implicit v1.",
    )


class WorkflowDefinitionCreate(BaseModel):
    """Request body for creating a new WorkflowDefinition."""

    name: str = Field(min_length=1)
    description: Optional[str] = None
    palette_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    expose_as_custom_skill: bool = False
    graph: Dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})


class WorkflowDefinitionUpdate(BaseModel):
    """Request body for updating a WorkflowDefinition (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    palette_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    expose_as_custom_skill: Optional[bool] = None
    graph: Optional[Dict[str, Any]] = None


class WorkflowDefinitionListItem(BaseModel):
    """Lightweight response for workflow list endpoints (excludes heavy ``graph`` field)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    palette_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    expose_as_custom_skill: bool = False
    is_system: bool = False
    builtin_slug: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowDefinitionRead(BaseModel):
    """Response body for a persisted WorkflowDefinition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    palette_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    expose_as_custom_skill: bool = False
    is_system: bool = False
    builtin_slug: Optional[str] = None
    graph: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
