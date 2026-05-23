"""Tests for sandbox schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.schemas.sandbox import (
    BoardCreaturePlacement,
    CreatureState,
    InventoryItem,
    PlaceCreatureEvent,
    PlaceItemEvent,
    PlaceRegionEvent,
    SandboxItem,
    default_region_trigger,
    normalize_hex_color,
)
from app.domain.user_settings import MAX_SANDBOX_FAVORITE_COLORS, normalize_sandbox_favorite_colors


def test_normalize_hex_color_rgb_shorthand():
    assert normalize_hex_color("#f00") == "#FF0000"


def test_normalize_hex_color_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_hex_color("red")


def test_region_item_requires_color():
    with pytest.raises(ValidationError):
        SandboxItem(id="r1", type="region", position={"x": 0, "y": 0})


def test_food_item_rejects_color():
    with pytest.raises(ValidationError):
        SandboxItem(id="f1", type="food", position={"x": 0, "y": 0}, energy=1, color="#FF0000")


def test_ball_item_requires_color():
    with pytest.raises(ValidationError):
        SandboxItem(id="b1", type="ball", position={"x": 0, "y": 0})


def test_ball_item_accepts_color():
    item = SandboxItem(id="b1", type="ball", position={"x": 0, "y": 0}, color="#abc")
    assert item.color == "#AABBCC"


def test_place_item_ball_requires_color():
    with pytest.raises(ValidationError):
        PlaceItemEvent(cell={"x": 0, "y": 0}, item_type="ball")


def test_inventory_ball_and_food():
    ball = InventoryItem(type="ball", color="#FF0000")
    assert ball.color == "#FF0000"
    food = InventoryItem(type="food", energy=12)
    assert food.energy == 12


def test_creature_inventory_round_trip():
    c = CreatureState(
        id="c1",
        workflow_id="wf-1",
        position={"x": 0, "y": 0},
        inventory=[InventoryItem(type="ball", color="#3B82F6")],
    )
    assert len(c.inventory) == 1
    assert c.inventory[0].type == "ball"


def test_place_region_event_normalizes_color():
    ev = PlaceRegionEvent(cell={"x": 1, "y": 2}, color="#abc")
    assert ev.color == "#AABBCC"


def test_place_creature_event_normalizes_color():
    ev = PlaceCreatureEvent(
        cell={"x": 1, "y": 2},
        workflow_id="wf-1",
        color="#abc",
    )
    assert ev.color == "#AABBCC"


def test_creature_state_normalizes_color():
    c = CreatureState(
        id="c1",
        workflow_id="wf-1",
        position={"x": 0, "y": 0},
        color="#f00",
    )
    assert c.color == "#FF0000"


def test_board_creature_placement_normalizes_color():
    bp = BoardCreaturePlacement(
        id="c1",
        workflow_id="wf-1",
        position={"x": 0, "y": 0},
        color="#abc",
    )
    assert bp.color == "#AABBCC"


def test_default_region_trigger_disabled():
    trig = default_region_trigger()
    assert trig.enabled is False
    assert trig.mode is None


def test_normalize_sandbox_favorite_colors_dedupes():
    assert normalize_sandbox_favorite_colors(["#3B82F6", "#3b82f6"]) == ["#3B82F6"]


def test_normalize_sandbox_favorite_colors_max():
    colors = [f"#{i:06x}" for i in range(MAX_SANDBOX_FAVORITE_COLORS + 3)]
    with pytest.raises(ValueError):
        normalize_sandbox_favorite_colors(colors)
