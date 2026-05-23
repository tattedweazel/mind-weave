"""Sandbox simulation domain types (mirror shared/sandbox_canonical.schema.json)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

DecisionAction = Literal[
    "move_forward",
    "turn_left",
    "turn_right",
    "idle",
    "pick_up_item",
    "place_item",
]
Facing = Literal["N", "E", "S", "W"]
NearbyCellKind = Literal["empty", "wall", "food", "ball", "creature", "out_of_bounds"]
ItemType = Literal["food", "wall", "region", "ball"]
PlaceableItemType = Literal["food", "wall", "ball"]
InventoryItemType = Literal["ball", "food"]
PlaceItemFilterType = Literal["ball", "food"]
RegionTriggerMode = Literal["enter", "exit", "while_inside", "on_enter_once"]
InteractionType = Literal[
    "cell_click",
    "item_click",
    "place_item",
    "remove_item",
    "place_creature",
    "remove_creature",
    "place_region",
    "remove_region",
]

SOLID_ITEM_TYPES = frozenset({"wall"})
BLOCKING_ITEM_TYPES = frozenset({"food", "wall", "ball"})
PICKABLE_ITEM_TYPES = frozenset({"food", "ball"})
REGION_ITEM_TYPE = "region"
BALL_ITEM_TYPE = "ball"
DEFAULT_FACING: Facing = "N"
DEFAULT_REGION_COLOR = "#3B82F6"
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SANDBOX_SCHEMA_VERSION = "2.3.0"


def normalize_hex_color(raw: str) -> str:
    """Normalize #RGB or #RRGGBB to uppercase #RRGGBB."""
    s = raw.strip()
    if not s.startswith("#"):
        raise ValueError("color must be a hex string starting with #")
    if len(s) == 4:
        r, g, b = s[1], s[2], s[3]
        s = f"#{r}{r}{g}{g}{b}{b}"
    if not _HEX_COLOR_RE.match(s):
        raise ValueError("color must be #RRGGBB hex")
    return s.upper()


def default_region_trigger() -> RegionTriggerConfig:
    return RegionTriggerConfig()


class GridCell(BaseModel):
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]


class NearbyCell(BaseModel):
    x: int
    y: int
    kind: NearbyCellKind


class RegionTriggerConfig(BaseModel):
    enabled: bool = False
    mode: Optional[RegionTriggerMode] = None
    workflow_id: Optional[str] = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class InventoryItem(BaseModel):
    type: InventoryItemType
    color: Optional[str] = None
    energy: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_fields(self) -> InventoryItem:
        if self.type == BALL_ITEM_TYPE:
            if not self.color:
                raise ValueError("ball inventory items require color")
            self.color = normalize_hex_color(self.color)
            if self.energy is not None:
                raise ValueError("energy is not valid for ball inventory items")
        elif self.type == "food":
            if self.energy is None:
                raise ValueError("food inventory items require energy")
            if self.color is not None:
                raise ValueError("color is not valid for food inventory items")
        return self


class SandboxItem(BaseModel):
    id: str = Field(min_length=1)
    type: ItemType
    position: GridCell
    energy: Optional[int] = Field(default=None, ge=0)
    color: Optional[str] = None
    trigger: Optional[RegionTriggerConfig] = None

    @model_validator(mode="after")
    def _validate_item_fields(self) -> SandboxItem:
        if self.type == REGION_ITEM_TYPE:
            if not self.color:
                raise ValueError("region items require color")
            self.color = normalize_hex_color(self.color)
            if self.trigger is None:
                self.trigger = default_region_trigger()
        elif self.type == BALL_ITEM_TYPE:
            if not self.color:
                raise ValueError("ball items require color")
            self.color = normalize_hex_color(self.color)
            if self.energy is not None or self.trigger is not None:
                raise ValueError("ball items cannot have energy or trigger")
        elif self.type == "food":
            if self.color is not None or self.trigger is not None:
                raise ValueError("color and trigger are not valid for food items")
        elif self.type == "wall":
            if self.color is not None or self.trigger is not None or self.energy is not None:
                raise ValueError("wall items cannot have color, trigger, or energy")
        return self


class DecisionIntent(BaseModel):
    action: DecisionAction
    reason: Optional[str] = None
    item_type: Optional[PlaceItemFilterType] = None


class CreatureState(BaseModel):
    id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    name: Optional[str] = None
    position: GridCell
    facing: Facing = DEFAULT_FACING
    color: Optional[str] = None
    inventory: list[InventoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_color(self) -> CreatureState:
        if self.color is not None:
            self.color = normalize_hex_color(self.color)
        return self


class WorldGrid(BaseModel):
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]


class WorldState(BaseModel):
    grid: WorldGrid
    items: list[SandboxItem] = Field(default_factory=list)


class RecentAction(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    creature_id: Optional[str] = None
    action: DecisionAction
    reason: Optional[str] = None


class SandboxState(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    creatures: list[CreatureState] = Field(default_factory=list)
    world: WorldState
    recent_actions: list[RecentAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cap_recent(self) -> SandboxState:
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]
        return self


class SandboxTickInput(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    creature: CreatureState
    creatures: list[CreatureState] = Field(default_factory=list)
    world: WorldState
    recent_actions: list[RecentAction] = Field(default_factory=list)


class BoardCreaturePlacement(BaseModel):
    id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    name: Optional[str] = None
    position: GridCell
    facing: Facing = DEFAULT_FACING
    color: Optional[str] = None
    inventory: list[InventoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_color(self) -> BoardCreaturePlacement:
        if self.color is not None:
            self.color = normalize_hex_color(self.color)
        return self


class BoardDefinition(BaseModel):
    """Persisted JSON inside SandboxBoard.body."""

    schema_version: str = SANDBOX_SCHEMA_VERSION
    grid: WorldGrid
    items: list[SandboxItem] = Field(default_factory=list)
    creatures: list[BoardCreaturePlacement] = Field(default_factory=list)


class CellClickEvent(BaseModel):
    type: Literal["cell_click"] = "cell_click"
    cell: GridCell


class ItemClickEvent(BaseModel):
    type: Literal["item_click"] = "item_click"
    item_id: str = Field(min_length=1)


class PlaceItemEvent(BaseModel):
    type: Literal["place_item"] = "place_item"
    cell: GridCell
    item_type: PlaceableItemType
    color: Optional[str] = None

    @model_validator(mode="after")
    def _validate_place_item(self) -> PlaceItemEvent:
        if self.item_type == BALL_ITEM_TYPE:
            if not self.color:
                raise ValueError("ball placement requires color")
            self.color = normalize_hex_color(self.color)
        elif self.color is not None:
            raise ValueError("color is only valid when placing a ball")
        return self


class RemoveItemEvent(BaseModel):
    type: Literal["remove_item"] = "remove_item"
    cell: GridCell


class PlaceCreatureEvent(BaseModel):
    type: Literal["place_creature"] = "place_creature"
    cell: GridCell
    workflow_id: str = Field(min_length=1)
    name: Optional[str] = None
    facing: Facing = DEFAULT_FACING
    color: str = Field(min_length=1)

    @model_validator(mode="after")
    def _normalize_color(self) -> PlaceCreatureEvent:
        self.color = normalize_hex_color(self.color)
        return self


class RemoveCreatureEvent(BaseModel):
    type: Literal["remove_creature"] = "remove_creature"
    cell: GridCell


class PlaceRegionEvent(BaseModel):
    type: Literal["place_region"] = "place_region"
    cell: GridCell
    color: str = Field(min_length=1)

    @model_validator(mode="after")
    def _normalize_color(self) -> PlaceRegionEvent:
        self.color = normalize_hex_color(self.color)
        return self


class RemoveRegionEvent(BaseModel):
    type: Literal["remove_region"] = "remove_region"
    cell: GridCell


SandboxInteractionEvent = Union[
    CellClickEvent,
    ItemClickEvent,
    PlaceItemEvent,
    RemoveItemEvent,
    PlaceCreatureEvent,
    RemoveCreatureEvent,
    PlaceRegionEvent,
    RemoveRegionEvent,
]


class SandboxDocumentEnvelope(BaseModel):
    """Persisted JSON inside Document.body for a sandbox session."""

    schema_version: str = SANDBOX_SCHEMA_VERSION
    board_id: Optional[str] = None
    sandbox: SandboxState
    playback: dict[str, Any] = Field(default_factory=dict)
    state_version: int = 0
    last_errors: dict[str, Optional[str]] = Field(default_factory=dict)


class SandboxPlaybackState(BaseModel):
    paused: bool = True
    tick_rate_ms: int = Field(default=1000, ge=200, le=60_000)
