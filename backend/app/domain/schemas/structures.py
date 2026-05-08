"""Structure API models."""

import json
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class StructureCreate(BaseModel):
    """Request body for creating a new Structure."""

    name: str = Field(min_length=1)
    description: str = ""
    json_schema: str = Field(min_length=1)

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, v: str) -> str:
        """Ensure json_schema is valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"json_schema must be valid JSON: {e}") from e
        return v


class StructureUpdate(BaseModel):
    """Request body for updating an existing Structure (all fields optional)."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    json_schema: Optional[str] = None

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, v: Optional[str]) -> Optional[str]:
        """Ensure json_schema is valid JSON when provided."""
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"json_schema must be valid JSON: {e}") from e
        return v
