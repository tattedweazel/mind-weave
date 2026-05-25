"""Tests for board item normalization."""

from __future__ import annotations

from app.domain.sandbox.board_normalization import (
    normalize_board_definition,
    normalize_board_definition_data,
    normalize_board_item,
    normalize_board_item_dict,
)
from app.domain.sandbox.item_helpers import ItemDefinitionDefaults
from app.domain.schemas.sandbox import BoardDefinition, GridCell, SandboxItem, WorldGrid


def test_normalize_board_item_strips_color_when_energy_present():
    raw = {
        "id": "milk1",
        "definition_id": "item-def-milk",
        "definition_kind": "item",
        "role": "pickable",
        "position": {"x": 1, "y": 1},
        "energy": 25,
        "color": "#FFFFFF",
    }
    normalized = normalize_board_item_dict(raw)
    item = SandboxItem.model_validate(normalized)
    assert item.energy == 25
    assert item.color is None
    assert item.type == "food"


def test_normalize_board_item_hydrates_color_from_definition_defaults():
    item = SandboxItem(
        id="milk1",
        definition_id="item-def-milk",
        definition_kind="item",
        role="pickable",
        position=GridCell(x=1, y=1),
    )
    defaults = {
        "item-def-milk": ItemDefinitionDefaults(
            default_color="#FFFFFF",
            custom_metadata={"energy": 25},
        ),
    }
    normalized = normalize_board_item(item, defaults)
    assert normalized.energy is None
    assert normalized.color == "#FFFFFF"
    assert normalized.type == "ball"


def test_normalize_board_item_stays_generic_without_defaults():
    item = SandboxItem(
        id="recipe1",
        definition_id="item-def-recipe",
        definition_kind="item",
        role="pickable",
        position=GridCell(x=1, y=1),
    )
    defaults = {
        "item-def-recipe": ItemDefinitionDefaults(
            custom_metadata={"ingredients": ["milk", "chai"]},
            pickable=False,
        ),
    }
    normalized = normalize_board_item(item, defaults)
    assert normalized.energy is None
    assert normalized.color is None
    assert normalized.type is None


def test_normalize_board_definition_applies_to_all_items():
    board_data = {
        "schema_version": "2.5.0",
        "grid": {"width": 4, "height": 4},
        "items": [
            {
                "id": "milk1",
                "definition_id": "item-def-milk",
                "definition_kind": "item",
                "role": "pickable",
                "position": {"x": 1, "y": 1},
                "energy": 25,
                "color": "#FFFFFF",
            },
        ],
        "creatures": [],
    }
    normalized = BoardDefinition.model_validate(normalize_board_definition_data(board_data))
    assert normalized.items[0].energy == 25
    assert normalized.items[0].color is None
