"""Sandbox simulation domain types (mirror shared/sandbox_canonical.schema.json)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

DecisionAction = Literal["move_forward", "turn_left", "turn_right", "idle"]
Facing = Literal["N", "E", "S", "W"]
NearbyCellKind = Literal["empty", "wall", "food", "creature", "out_of_bounds"]
ItemType = Literal["food", "wall"]
InteractionType = Literal[
    "cell_click",
    "item_click",
    "place_item",
    "remove_item",
    "place_creature",
    "remove_creature",
]

SOLID_ITEM_TYPES = frozenset({"wall"})
DEFAULT_FACING: Facing = "N"


class GridCell(BaseModel):
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]


class NearbyCell(BaseModel):
    x: int
    y: int
    kind: NearbyCellKind


class SandboxItem(BaseModel):
    id: str = Field(min_length=1)
    type: ItemType
    position: GridCell
    energy: Optional[int] = Field(default=None, ge=0)


class DecisionIntent(BaseModel):
    action: DecisionAction
    reason: Optional[str] = None


class CreatureState(BaseModel):
    id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    name: Optional[str] = None
    position: GridCell
    facing: Facing = DEFAULT_FACING


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


class BoardDefinition(BaseModel):
    """Persisted JSON inside SandboxBoard.body."""

    schema_version: str = "2.1.0"
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
    item_type: ItemType


class RemoveItemEvent(BaseModel):
    type: Literal["remove_item"] = "remove_item"
    cell: GridCell


class PlaceCreatureEvent(BaseModel):
    type: Literal["place_creature"] = "place_creature"
    cell: GridCell
    workflow_id: str = Field(min_length=1)
    name: Optional[str] = None


class RemoveCreatureEvent(BaseModel):
    type: Literal["remove_creature"] = "remove_creature"
    cell: GridCell


SandboxInteractionEvent = Union[
    CellClickEvent,
    ItemClickEvent,
    PlaceItemEvent,
    RemoveItemEvent,
    PlaceCreatureEvent,
    RemoveCreatureEvent,
]


class SandboxDocumentEnvelope(BaseModel):
    """Persisted JSON inside Document.body for a sandbox session."""

    schema_version: str = "2.1.0"
    board_id: Optional[str] = None
    sandbox: SandboxState
    playback: dict[str, Any] = Field(default_factory=dict)
    state_version: int = 0
    last_errors: dict[str, Optional[str]] = Field(default_factory=dict)


class SandboxPlaybackState(BaseModel):
    paused: bool = True
    tick_rate_ms: int = Field(default=1000, ge=200, le=60_000)
