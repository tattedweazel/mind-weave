"""Sandbox simulation domain types (mirror shared/sandbox_canonical.schema.json)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

DecisionAction = Literal["move_to", "wander", "eat_nearby", "sleep", "idle"]
IntentStatus = Literal["in_progress", "complete", "failed"]
ItemType = Literal["food"]
InteractionType = Literal["cell_click", "item_click", "place_item", "remove_item"]


class GridCell(BaseModel):
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]


class SandboxItem(BaseModel):
    id: str = Field(min_length=1)
    type: ItemType
    position: GridCell
    energy: Optional[int] = Field(default=None, ge=0)


class DecisionIntent(BaseModel):
    action: DecisionAction
    target_item_id: Optional[str] = Field(default=None, min_length=1)
    target_cell: Optional[GridCell] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _action_consistency(self) -> DecisionIntent:
        a = self.action
        tid, tc = self.target_item_id, self.target_cell
        if a == "move_to":
            has_item = tid is not None and tid != ""
            has_cell = tc is not None
            if has_item == has_cell:
                raise ValueError("move_to requires exactly one of target_item_id or target_cell")
        elif a == "eat_nearby":
            if tc is not None:
                raise ValueError("eat_nearby requires target_cell null")
        elif a in ("wander", "sleep", "idle"):
            if tid is not None or tc is not None:
                raise ValueError(f"{a} requires null targets")
        return self


class PetIntent(BaseModel):
    action: DecisionAction
    status: IntentStatus
    target_item_id: Optional[str] = Field(default=None, min_length=1)
    target_cell: Optional[GridCell] = None
    reason: Optional[str] = None
    retry_count: Annotated[int, Field(ge=0, le=3)] = 0


class PetState(BaseModel):
    hunger: Annotated[int, Field(ge=0, le=100)]
    energy: Annotated[int, Field(ge=0, le=100)]
    mood: Annotated[int, Field(ge=0, le=100)]
    position: GridCell
    intent: Optional[PetIntent] = None


class WorldGrid(BaseModel):
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]


class WorldState(BaseModel):
    grid: WorldGrid
    items: list[SandboxItem] = Field(default_factory=list)


class RecentAction(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    action: DecisionAction
    reason: Optional[str] = None


class SandboxState(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    pet: PetState
    world: WorldState
    recent_actions: list[RecentAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cap_recent(self) -> SandboxState:
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]
        return self


class SandboxTickInput(BaseModel):
    tick: Annotated[int, Field(ge=0)]
    pet: PetState
    world: WorldState
    recent_actions: list[RecentAction] = Field(default_factory=list)


class CellClickEvent(BaseModel):
    type: Literal["cell_click"] = "cell_click"
    cell: GridCell


class ItemClickEvent(BaseModel):
    type: Literal["item_click"] = "item_click"
    item_id: str = Field(min_length=1)


class PlaceItemEvent(BaseModel):
    """Explicit place-item interaction (Wizard: Place → item type). Extends with more `item_type` values later."""

    type: Literal["place_item"] = "place_item"
    cell: GridCell
    item_type: ItemType


class RemoveItemEvent(BaseModel):
    """Remove any sandbox item at the given cell (V1: food only)."""

    type: Literal["remove_item"] = "remove_item"
    cell: GridCell


SandboxInteractionEvent = Union[CellClickEvent, ItemClickEvent, PlaceItemEvent, RemoveItemEvent]


class SandboxDocumentEnvelope(BaseModel):
    """Persisted JSON inside Document.body for a sandbox session."""

    schema_version: str = "1.0.0"
    workflow_id: str
    sandbox: SandboxState
    playback: dict[str, Any] = Field(default_factory=dict)
    state_version: int = 0
    last_error: Optional[str] = None


class SandboxPlaybackState(BaseModel):
    """Optional playback fields inside envelope.playback."""

    paused: bool = True
    tick_rate_ms: int = Field(default=1000, ge=200, le=60_000)
