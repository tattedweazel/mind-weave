"""Pydantic schemas for Sandbox definition resources."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.domain.schemas.sandbox import (
    Facing,
    InventoryItem,
    RegionTriggerConfig,
    default_region_trigger,
    normalize_hex_color,
)

DefinitionShape = Literal["circle", "square", "rect"]


class ItemDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    default_color: Optional[str] = None
    shape: DefinitionShape = "circle"
    pickable: bool = True

    @model_validator(mode="after")
    def _normalize(self) -> ItemDefinitionCreate:
        if self.default_color is not None:
            self.default_color = normalize_hex_color(self.default_color)
        if not isinstance(self.custom_metadata, dict):
            raise ValueError("custom_metadata must be an object")
        return self


class ItemDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = Field(default=None, min_length=1)
    custom_metadata: Optional[dict[str, Any]] = None
    default_color: Optional[str] = None
    shape: Optional[DefinitionShape] = None
    pickable: Optional[bool] = None

    @model_validator(mode="after")
    def _normalize(self) -> ItemDefinitionUpdate:
        if self.default_color is not None:
            self.default_color = normalize_hex_color(self.default_color)
        if self.custom_metadata is not None and not isinstance(self.custom_metadata, dict):
            raise ValueError("custom_metadata must be an object")
        return self


class TerrainDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    default_color: Optional[str] = None
    shape: DefinitionShape = "rect"

    @model_validator(mode="after")
    def _normalize_color(self) -> TerrainDefinitionCreate:
        if self.default_color is not None:
            self.default_color = normalize_hex_color(self.default_color)
        return self


class TerrainDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = Field(default=None, min_length=1)
    default_color: Optional[str] = None
    shape: Optional[DefinitionShape] = None

    @model_validator(mode="after")
    def _normalize_color(self) -> TerrainDefinitionUpdate:
        if self.default_color is not None:
            self.default_color = normalize_hex_color(self.default_color)
        return self


class FixtureDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    color: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_color(self) -> FixtureDefinitionCreate:
        if self.color is not None:
            self.color = normalize_hex_color(self.color)
        return self


class FixtureDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = Field(default=None, min_length=1)
    workflow_id: Optional[str] = Field(default=None, min_length=1)
    color: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_color(self) -> FixtureDefinitionUpdate:
        if self.color is not None:
            self.color = normalize_hex_color(self.color)
        return self


class CreatureDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    default_color: str = Field(min_length=1)
    default_facing: Facing = "N"
    default_inventory: list[InventoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_color(self) -> CreatureDefinitionCreate:
        self.default_color = normalize_hex_color(self.default_color)
        return self


class CreatureDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = Field(default=None, min_length=1)
    workflow_id: Optional[str] = Field(default=None, min_length=1)
    default_color: Optional[str] = Field(default=None, min_length=1)
    default_facing: Optional[Facing] = None
    default_inventory: Optional[list[InventoryItem]] = None

    @model_validator(mode="after")
    def _normalize_color(self) -> CreatureDefinitionUpdate:
        if self.default_color is not None:
            self.default_color = normalize_hex_color(self.default_color)
        return self


class RegionDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    color: str = Field(min_length=1)
    trigger: RegionTriggerConfig

    @model_validator(mode="after")
    def _normalize(self) -> RegionDefinitionCreate:
        self.color = normalize_hex_color(self.color)
        return self


class RegionDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = Field(default=None, min_length=1)
    color: Optional[str] = Field(default=None, min_length=1)
    trigger: Optional[RegionTriggerConfig] = None

    @model_validator(mode="after")
    def _normalize(self) -> RegionDefinitionUpdate:
        if self.color is not None:
            self.color = normalize_hex_color(self.color)
        return self


class ItemDefinitionRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    label: str
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    default_color: Optional[str] = None
    shape: DefinitionShape = "circle"
    pickable: bool = True
    is_system: bool = False
    builtin_slug: Optional[str] = None


class TerrainDefinitionRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    label: str
    default_color: Optional[str] = None
    shape: DefinitionShape = "rect"
    is_system: bool = False
    builtin_slug: Optional[str] = None


class FixtureDefinitionRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    label: str
    workflow_id: str
    color: Optional[str] = None
    is_system: bool = False
    builtin_slug: Optional[str] = None


class CreatureDefinitionRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    label: str
    workflow_id: str
    default_color: str
    default_facing: Facing = "N"
    default_inventory: list[InventoryItem] = Field(default_factory=list)
    is_system: bool = False
    builtin_slug: Optional[str] = None


class RegionDefinitionRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    label: str
    color: str
    trigger: RegionTriggerConfig
    is_system: bool = False
    builtin_slug: Optional[str] = None


# Stable builtin slugs for migration
BUILTIN_FOOD_SLUG = "builtin-food"
BUILTIN_BALL_SLUG = "builtin-ball"
BUILTIN_WALL_SLUG = "builtin-wall"

# Stable UUIDs for seeded definitions (used in migration)
BUILTIN_FOOD_ID = "a1000000-0000-4000-8000-000000000001"
BUILTIN_BALL_ID = "a1000000-0000-4000-8000-000000000002"
BUILTIN_WALL_ID = "a1000000-0000-4000-8000-000000000003"

DefinitionKind = Literal["item", "terrain", "fixture", "region"]
ItemRole = Literal["pickable", "solid"]
