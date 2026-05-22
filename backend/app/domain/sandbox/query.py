"""Pure helpers for sandbox workflow utilities and tests (no I/O)."""

from __future__ import annotations

from typing import Any

from app.domain.schemas.sandbox import (
    CreatureState,
    DecisionIntent,
    Facing,
    GridCell,
    NearbyCell,
    NearbyCellKind,
    REGION_ITEM_TYPE,
    SandboxTickInput,
    SOLID_ITEM_TYPES,
    WorldState,
)

# Clockwise ring starting at forward when facing North (N, NE, E, SE, S, SW, W, NW).
_NEIGHBOR_OFFSETS_N: list[tuple[int, int]] = [
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
]

_FACING_START_INDEX: dict[Facing, int] = {"N": 0, "E": 2, "S": 4, "W": 6}


def parse_tick(raw: dict[str, Any]) -> SandboxTickInput:
    return SandboxTickInput.model_validate(raw)


def creature_position_from_tick_dict(raw: dict[str, Any]) -> dict[str, int]:
    return parse_tick(raw).creature.position.model_dump(mode="json")


def creature_facing_from_tick_dict(raw: dict[str, Any]) -> str:
    return parse_tick(raw).creature.facing


def nearby_cells_from_tick_dict(raw: dict[str, Any]) -> list[dict[str, Any]]:
    tick = parse_tick(raw)
    cells = nearby_cells_clockwise(
        tick.creature.facing,
        tick.creature.position,
        tick.world.grid.width,
        tick.world.grid.height,
        tick.world,
        tick.creatures,
        exclude_creature_id=tick.creature.id,
    )
    return [c.model_dump(mode="json") for c in cells]


def nearby_cells_clockwise(
    facing: Facing,
    position: GridCell,
    width: int,
    height: int,
    world: WorldState,
    creatures: list[CreatureState],
    *,
    exclude_creature_id: str | None = None,
) -> list[NearbyCell]:
    start = _FACING_START_INDEX[facing]
    ordered_offsets = _NEIGHBOR_OFFSETS_N[start:] + _NEIGHBOR_OFFSETS_N[:start]
    out: list[NearbyCell] = []
    for dx, dy in ordered_offsets:
        x, y = position.x + dx, position.y + dy
        kind = _cell_kind(x, y, width, height, world, creatures, exclude_creature_id)
        out.append(NearbyCell(x=x, y=y, kind=kind))
    return out


def _cell_kind(
    x: int,
    y: int,
    width: int,
    height: int,
    world: WorldState,
    creatures: list[CreatureState],
    exclude_creature_id: str | None,
) -> NearbyCellKind:
    if x < 0 or y < 0 or x >= width or y >= height:
        return "out_of_bounds"
    for c in creatures:
        if exclude_creature_id and c.id == exclude_creature_id:
            continue
        if c.position.x == x and c.position.y == y:
            return "creature"
    for it in world.items:
        if it.position.x == x and it.position.y == y:
            if it.type == REGION_ITEM_TYPE:
                continue
            if it.type in SOLID_ITEM_TYPES:
                return "wall"
            if it.type == "food":
                return "food"
    return "empty"


def grid_cell_from_jsonable(raw: Any) -> GridCell:
    if not isinstance(raw, dict):
        raise ValueError("expected a JSON object for grid cell")
    return GridCell.model_validate(raw)


def navigation_action_dict(action: str, reason: str | None = None) -> dict[str, Any]:
    intent = DecisionIntent(action=action, reason=reason)  # type: ignore[arg-type]
    return intent.model_dump(mode="json")
