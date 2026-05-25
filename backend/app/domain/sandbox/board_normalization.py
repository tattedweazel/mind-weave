"""Normalize board item instances for definition-backed pickables."""

from __future__ import annotations

from typing import Any, Mapping

from app.domain.sandbox.constants import DEFAULT_FOOD_ENERGY
from app.domain.sandbox.item_helpers import (
    ItemDefinitionDefaults,
    resolved_pickable_color,
    resolved_pickable_energy,
)
from app.domain.schemas.sandbox import BALL_ITEM_TYPE, BoardDefinition, SandboxItem


def normalize_board_item_dict(
    raw: dict[str, Any],
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    """Normalize a raw board item dict before SandboxItem validation."""
    if raw.get("definition_kind") != "item" or raw.get("role") != "pickable":
        return raw

    item = SandboxItem.model_construct(**raw)
    normalized = normalize_board_item(item, definition_defaults)
    return normalized.model_dump(mode="json", exclude_none=False)


def normalize_board_definition_data(
    data: dict[str, Any],
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    """Normalize board JSON before BoardDefinition validation."""
    out = dict(data)
    items = out.get("items") or []
    out["items"] = [normalize_board_item_dict(it, definition_defaults) for it in items]
    return out


def normalize_board_item(
    item: SandboxItem,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> SandboxItem:
    """Materialize instance fields for definition-backed pickables."""
    if item.definition_kind != "item" or item.role != "pickable":
        return item

    energy = resolved_pickable_energy(item, definition_defaults)
    if energy is not None:
        return item.model_copy(update={"energy": energy, "color": None, "type": "food"})

    color = resolved_pickable_color(item, definition_defaults)
    if color is not None:
        return item.model_copy(update={"color": color, "energy": None, "type": BALL_ITEM_TYPE})

    return item.model_copy(
        update={"energy": DEFAULT_FOOD_ENERGY, "color": None, "type": "food"},
    )


def normalize_board_definition(
    definition: BoardDefinition,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> BoardDefinition:
    """Normalize all board items (strip invalid color+energy pairs, hydrate defaults)."""
    return definition.model_copy(
        update={
            "items": [
                normalize_board_item(item, definition_defaults) for item in definition.items
            ],
        },
    )
