"""Pure sandbox query helpers (no I/O)."""

import pytest

from app.domain.sandbox.query import (
    available_cells_from_tick_dict,
    filter_items_by_type,
    first_food_world_order_item_dicts,
    first_nearby_food_item_dicts,
    grid_cell_from_jsonable,
    is_nearby8,
    item_type_literal,
    manhattan,
    nearest_item_dicts_by_type,
    pet_cell_dict_from_tick_dict,
    pet_energy_from_tick_dict,
    pet_hunger_from_tick_dict,
    tick_dict_to_items,
    world_grid_dimensions_from_tick,
)
from app.domain.schemas.sandbox import GridCell


def test_manhattan():
    assert manhattan(GridCell(x=0, y=0), GridCell(x=3, y=4)) == 7


def test_is_nearby8_adjacent_not_self():
    pet = GridCell(x=1, y=1)
    assert is_nearby8(pet, GridCell(x=1, y=0)) is True
    assert is_nearby8(pet, GridCell(x=1, y=1)) is False


def test_tick_dict_to_items():
    raw = {
        "tick": 1,
        "pet": {"hunger": 1, "energy": 1, "mood": 1, "position": {"x": 0, "y": 0}},
        "world": {
            "grid": {"width": 3, "height": 3},
            "items": [{"id": "a", "type": "food", "position": {"x": 1, "y": 1}}],
        },
        "recent_actions": [],
    }
    items = tick_dict_to_items(raw)
    assert len(items) == 1
    assert items[0]["id"] == "a"


def test_filter_items_by_type():
    items = [{"id": "1", "type": "food"}, {"id": "2", "type": "food"}]
    assert len(filter_items_by_type(items, "food")) == 2
    assert filter_items_by_type(items, "other") == []


def test_item_type_literal_food_only():
    assert item_type_literal("food") == "food"


def test_item_type_literal_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported"):
        item_type_literal("water")


def _minimal_tick(
    *,
    pet_pos: dict,
    items: list,
    hunger: int = 50,
    energy: int = 50,
) -> dict:
    return {
        "tick": 1,
        "pet": {"hunger": hunger, "energy": energy, "mood": 1, "position": pet_pos},
        "world": {"grid": {"width": 5, "height": 5}, "items": items},
        "recent_actions": [],
    }


def test_pet_cell_dict_from_tick():
    raw = _minimal_tick(pet_pos={"x": 3, "y": 2}, items=[], hunger=1, energy=1)
    cell = pet_cell_dict_from_tick_dict(raw)
    assert cell == {"x": 3, "y": 2}
    assert cell == raw["pet"]["position"]


def test_pet_hunger_energy_from_tick():
    raw = _minimal_tick(pet_pos={"x": 0, "y": 0}, items=[], hunger=42, energy=7)
    assert pet_hunger_from_tick_dict(raw) == 42
    assert pet_energy_from_tick_dict(raw) == 7


def test_first_food_world_order_respects_items_order():
    raw = _minimal_tick(
        pet_pos={"x": 0, "y": 0},
        items=[
            {"id": "x", "type": "food", "position": {"x": 2, "y": 2}},
            {"id": "y", "type": "food", "position": {"x": 1, "y": 1}},
        ],
    )
    got = first_food_world_order_item_dicts(raw)
    assert len(got) == 1
    assert got[0]["id"] == "x"


def test_first_nearby_food_skips_non_adjacent_then_picks_first_in_order():
    raw = _minimal_tick(
        pet_pos={"x": 1, "y": 1},
        items=[
            {"id": "far", "type": "food", "position": {"x": 4, "y": 4}},
            {"id": "near", "type": "food", "position": {"x": 1, "y": 0}},
        ],
    )
    got = first_nearby_food_item_dicts(raw)
    assert [g["id"] for g in got] == ["near"]


def test_first_nearby_food_empty_when_no_adjacent_food():
    raw = _minimal_tick(
        pet_pos={"x": 0, "y": 0},
        items=[{"id": "f", "type": "food", "position": {"x": 2, "y": 0}}],
    )
    assert first_nearby_food_item_dicts(raw) == []


def test_grid_cell_from_jsonable():
    c = grid_cell_from_jsonable({"x": 3, "y": 4})
    assert c.x == 3 and c.y == 4


def test_available_cells_pet_only_2x2():
    raw = _minimal_tick(pet_pos={"x": 0, "y": 0}, items=[])
    raw["world"]["grid"] = {"width": 2, "height": 2}
    cells = available_cells_from_tick_dict(raw)
    assert cells == [{"x": 1, "y": 0}, {"x": 0, "y": 1}, {"x": 1, "y": 1}]


def test_available_cells_excludes_item_positions():
    raw = _minimal_tick(
        pet_pos={"x": 1, "y": 1},
        items=[{"id": "f", "type": "food", "position": {"x": 2, "y": 2}, "energy": 10}],
    )
    raw["world"]["grid"] = {"width": 3, "height": 3}
    cells = available_cells_from_tick_dict(raw)
    occupied = {(c["x"], c["y"]) for c in cells}
    assert (1, 1) not in occupied
    assert (2, 2) not in occupied
    assert len(cells) == 9 - 2


def test_grid_cell_from_jsonable_rejects_non_object():
    with pytest.raises(ValueError, match="expected"):
        grid_cell_from_jsonable([])


def test_world_grid_dimensions_from_tick():
    raw = _minimal_tick(pet_pos={"x": 0, "y": 0}, items=[])
    assert world_grid_dimensions_from_tick(raw) == {"width": 5, "height": 5}


def test_nearest_item_by_type_min_manhattan_tie_break_order():
    raw = _minimal_tick(
        pet_pos={"x": 1, "y": 1},
        items=[
            {"id": "a", "type": "food", "position": {"x": 3, "y": 1}},
            {"id": "b", "type": "food", "position": {"x": 2, "y": 1}},
        ],
    )
    got = nearest_item_dicts_by_type(raw, "food")
    assert [g["id"] for g in got] == ["b"]
    raw2 = _minimal_tick(
        pet_pos={"x": 0, "y": 0},
        items=[
            {"id": "first", "type": "food", "position": {"x": 2, "y": 0}},
            {"id": "second", "type": "food", "position": {"x": 0, "y": 2}},
        ],
    )
    got2 = nearest_item_dicts_by_type(raw2, "food")
    assert [g["id"] for g in got2] == ["first"]


def test_nearest_item_by_type_all_picks_min_distance():
    raw = _minimal_tick(
        pet_pos={"x": 0, "y": 0},
        items=[
            {"id": "far", "type": "food", "position": {"x": 10, "y": 0}},
            {"id": "win", "type": "food", "position": {"x": 0, "y": 1}},
        ],
    )
    got_all = nearest_item_dicts_by_type(raw, "all")
    got_food = nearest_item_dicts_by_type(raw, "food")
    assert got_all == got_food
    assert [g["id"] for g in got_all] == ["win"]
