"""Pure helpers for sandbox workflow utilities and tests (no I/O).

Mirrors geometry used in ``engine`` / ``starter_behavior`` so composable workflows
stay consistent with simulation semantics.
"""

from __future__ import annotations

from typing import Any

from app.domain.schemas.sandbox import GridCell, ItemType, SandboxItem, SandboxTickInput


def manhattan(a: GridCell, b: GridCell) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def is_nearby8(pet: GridCell, cell: GridCell) -> bool:
    dx = abs(pet.x - cell.x)
    dy = abs(pet.y - cell.y)
    return dx <= 1 and dy <= 1 and (dx + dy) > 0


def tick_dict_to_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ``world.items`` as JSON-like dicts from a tick-shaped dict."""
    world = raw.get("world")
    if not isinstance(world, dict):
        return []
    items = world.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    return out


def filter_items_by_type(items: list[dict[str, Any]], item_type: str) -> list[dict[str, Any]]:
    """Filter serialized items by ``type`` field (e.g. ``food``)."""
    t = (item_type or "").strip()
    if not t:
        return []
    return [it for it in items if isinstance(it, dict) and it.get("type") == t]


def parse_tick(raw: dict[str, Any]) -> SandboxTickInput:
    """Validate a tick dict (from Start / overrides) as ``SandboxTickInput``."""
    return SandboxTickInput.model_validate(raw)


def item_type_literal(raw: str) -> ItemType:
    """Return a validated ``ItemType`` or raise."""
    v = (raw or "").strip()
    if v == "food":
        return "food"
    raise ValueError(f"unsupported item type: {raw!r} (V1 only supports 'food')")


def sandbox_item_from_dict(raw: dict[str, Any]) -> SandboxItem:
    return SandboxItem.model_validate(raw)


def pet_hunger_from_tick_dict(raw: dict[str, Any]) -> int:
    """``pet.hunger`` from a tick-shaped dict (validated)."""
    return parse_tick(raw).pet.hunger


def pet_energy_from_tick_dict(raw: dict[str, Any]) -> int:
    """``pet.energy`` from a tick-shaped dict (validated)."""
    return parse_tick(raw).pet.energy


def pet_cell_dict_from_tick_dict(raw: dict[str, Any]) -> dict[str, int]:
    """``pet.position`` as ``GridCell`` JSON (``x``, ``y``) from a validated tick dict."""
    return parse_tick(raw).pet.position.model_dump(mode="json")


def first_nearby_food_item_dicts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """First food item in ``world.items`` order that is adjacent to the pet (starter_behavior order)."""
    tick = parse_tick(raw)
    pet = tick.pet.position
    for it in tick.world.items:
        if it.type == "food" and is_nearby8(pet, it.position):
            return [it.model_dump(mode="json")]
    return []


def world_grid_dimensions_from_tick(raw: dict[str, Any]) -> dict[str, int]:
    """``width`` / ``height`` from validated tick ``world.grid``."""
    tick = parse_tick(raw)
    return {"width": tick.world.grid.width, "height": tick.world.grid.height}


def nearest_item_dicts_by_type(raw_tick: dict[str, Any], item_type: str) -> list[dict[str, Any]]:
    """Items of ``item_type`` minimizing Manhattan distance from pet; ties: first in ``world.items`` order.

    ``item_type`` may be ``"all"`` to consider every item in ``world.items`` (same distance/tie rules).
    """
    t = (item_type or "").strip().lower()
    if not t:
        return []
    tick = parse_tick(raw_tick)
    pet = tick.pet.position
    best: list[dict[str, Any]] = []
    best_d: int | None = None
    if t == "all":
        for it in tick.world.items:
            d = manhattan(pet, it.position)
            if best_d is None or d < best_d:
                best_d = d
                best = [it.model_dump(mode="json")]
            # equal distance: keep earlier item in iteration order
        return best
    item_type_literal(t)
    for it in tick.world.items:
        if it.type != t:
            continue
        d = manhattan(pet, it.position)
        if best_d is None or d < best_d:
            best_d = d
            best = [it.model_dump(mode="json")]
        # equal distance: keep earlier item in iteration order
    return best


def first_food_world_order_item_dicts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """First food item in ``world.items`` iteration order (``foods[0]`` in starter seek)."""
    tick = parse_tick(raw)
    for it in tick.world.items:
        if it.type == "food":
            return [it.model_dump(mode="json")]
    return []


def available_cells_from_tick_dict(raw: dict[str, Any]) -> list[dict[str, int]]:
    """Cells inside ``world.grid`` not occupied by the pet or any item; row-major ``(y``, then ``x)`` order."""
    tick = parse_tick(raw)
    w, h = tick.world.grid.width, tick.world.grid.height
    occupied: set[tuple[int, int]] = {(tick.pet.position.x, tick.pet.position.y)}
    for it in tick.world.items:
        occupied.add((it.position.x, it.position.y))
    out: list[dict[str, int]] = []
    for y in range(h):
        for x in range(w):
            if (x, y) not in occupied:
                out.append({"x": x, "y": y})
    return out


def grid_cell_from_jsonable(raw: Any) -> GridCell:
    """Coerce a JSON-like dict (``x`` / ``y``) to ``GridCell``."""
    if not isinstance(raw, dict):
        raise ValueError("expected a JSON object for grid cell")
    return GridCell.model_validate(raw)
