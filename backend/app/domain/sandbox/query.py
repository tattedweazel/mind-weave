"""Pure helpers for sandbox workflow utilities and tests (no I/O)."""

from __future__ import annotations

from typing import Any, Mapping

from app.domain.schemas.sandbox import (
    BALL_ITEM_TYPE,
    CreatureState,
    DecisionIntent,
    Facing,
    FIXTURE_ITEM_TYPE,
    GridCell,
    NearbyCell,
    NearbyCellKind,
    PlaceItemFilterType,
    REGION_ITEM_TYPE,
    SandboxTickInput,
    WorldState,
)
from app.domain.sandbox.item_helpers import (
    ItemDefinitionDefaults,
    cell_pickables_probe_summary,
    is_region_item,
    is_solid_item,
    items_at_cell,
    region_at_cell,
    resolved_item_type,
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


def tick_dict_from_fixture_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Build a ``SandboxTickInput``-compatible dict from ``FixtureInteractionInput``."""
    from app.domain.schemas.sandbox import FixtureInteractionInput

    fx = FixtureInteractionInput.model_validate(raw)
    wf_id = fx.fixture.workflow_id or "fixture-context"
    creature = CreatureState(
        id=fx.actor.id,
        workflow_id=wf_id,
        position=fx.actor.position.model_copy(deep=True),
        facing=fx.actor.facing,
    )
    tick_in = SandboxTickInput(
        tick=fx.tick,
        creature=creature,
        creatures=[creature],
        world=fx.world.model_copy(deep=True),
        recent_actions=[],
    )
    return tick_in.model_dump(mode="json")


def cell_probe_at(
    x: int,
    y: int,
    width: int,
    height: int,
    world: WorldState,
    creatures: list[CreatureState],
    *,
    exclude_creature_id: str | None = None,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    kind = _cell_kind(x, y, width, height, world, creatures, exclude_creature_id)
    region_label = _region_label_at_cell(x, y, world)
    stack_count, item_summaries = cell_pickables_probe_summary(
        world.items, x, y, definition_labels, definition_defaults
    )
    return {
        "x": x,
        "y": y,
        "kind": kind,
        "region_label": region_label,
        "stack_count": stack_count,
        "items": item_summaries,
    }


def creature_position_from_tick_dict(
    raw: dict[str, Any],
    *,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    tick = parse_tick(raw)
    pos = tick.creature.position
    return cell_probe_at(
        pos.x,
        pos.y,
        tick.world.grid.width,
        tick.world.grid.height,
        tick.world,
        tick.creatures,
        exclude_creature_id=tick.creature.id,
        definition_labels=definition_labels,
        definition_defaults=definition_defaults,
    )


def fixture_cell_probe_from_fixture_dict(
    raw: dict[str, Any],
    *,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    """Probe the fixture cell (where stacked pickables live) from ``FixtureInteractionInput``."""
    from app.domain.schemas.sandbox import FixtureInteractionInput

    fx = FixtureInteractionInput.model_validate(raw)
    pos = fx.fixture.position
    tick = parse_tick(tick_dict_from_fixture_dict(raw))
    return cell_probe_at(
        pos.x,
        pos.y,
        fx.world.grid.width,
        fx.world.grid.height,
        fx.world,
        tick.creatures,
        exclude_creature_id=None,
        definition_labels=definition_labels,
        definition_defaults=definition_defaults,
    )


def creature_facing_from_tick_dict(raw: dict[str, Any]) -> str:
    return parse_tick(raw).creature.facing


def nearby_cells_from_tick_dict(
    raw: dict[str, Any],
    *,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> list[dict[str, Any]]:
    tick = parse_tick(raw)
    cells = nearby_cells_clockwise(
        tick.creature.facing,
        tick.creature.position,
        tick.world.grid.width,
        tick.world.grid.height,
        tick.world,
        tick.creatures,
        exclude_creature_id=tick.creature.id,
        definition_labels=definition_labels,
        definition_defaults=definition_defaults,
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
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> list[NearbyCell]:
    start = _FACING_START_INDEX[facing]
    ordered_offsets = _NEIGHBOR_OFFSETS_N[start:] + _NEIGHBOR_OFFSETS_N[:start]
    out: list[NearbyCell] = []
    for dx, dy in ordered_offsets:
        x, y = position.x + dx, position.y + dy
        probe = cell_probe_at(
            x,
            y,
            width,
            height,
            world,
            creatures,
            exclude_creature_id=exclude_creature_id,
            definition_labels=definition_labels,
            definition_defaults=definition_defaults,
        )
        out.append(NearbyCell.model_validate(probe))
    return out


def _region_label_at_cell(x: int, y: int, world: WorldState) -> str | None:
    reg = region_at_cell(world.items, x, y)
    if reg is None:
        return None
    return reg.label if reg.label is not None else ""


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
    cell_items = items_at_cell(world.items, x, y)
    for it in cell_items:
        if is_region_item(it):
            continue
        t = resolved_item_type(it)
        if t == FIXTURE_ITEM_TYPE:
            return "fixture"
        if is_solid_item(it):
            return "wall"
        if t == BALL_ITEM_TYPE:
            return "ball"
        if t == "food":
            return "food"
    return "empty"


def inventory_from_tick_dict(raw: dict[str, Any]) -> list[dict[str, Any]]:
    tick = parse_tick(raw)
    return [
        entry.model_dump(mode="json", exclude_none=True) for entry in tick.creature.inventory
    ]


def grid_cell_from_jsonable(raw: Any) -> GridCell:
    if not isinstance(raw, dict):
        raise ValueError("expected a JSON object for grid cell")
    return GridCell.model_validate(raw)


def navigation_action_dict(
    action: str,
    reason: str | None = None,
    *,
    item_type: PlaceItemFilterType | None = None,
    inventory_index: int | None = None,
) -> dict[str, Any]:
    intent = DecisionIntent(
        action=action,  # type: ignore[arg-type]
        reason=reason,
        item_type=item_type,
        inventory_index=inventory_index,
    )
    return intent.model_dump(mode="json", exclude_none=True)
