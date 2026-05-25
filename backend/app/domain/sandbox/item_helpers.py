"""Resolve sandbox item behavior from definition fields and legacy type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.domain.schemas.sandbox import (
    BALL_ITEM_TYPE,
    FIXTURE_ITEM_TYPE,
    PICKABLE_ITEM_TYPES,
    REGION_ITEM_TYPE,
    SOLID_ITEM_TYPES,
    SandboxItem,
)


def resolved_item_type(it: SandboxItem) -> str:
    """Return sensory/behavior type string for an item."""
    if it.type is not None:
        return it.type
    kind = it.definition_kind
    if kind == "terrain":
        return "wall"
    if kind == "fixture":
        return FIXTURE_ITEM_TYPE
    if kind == "region":
        return REGION_ITEM_TYPE
    if kind == "item":
        slug = (it.builtin_slug or "").lower()
        if "ball" in slug or it.color is not None:
            return BALL_ITEM_TYPE
        return "food"
    return "food"


@dataclass(frozen=True)
class ItemDefinitionDefaults:
    default_energy: int | None = None
    default_color: str | None = None


@dataclass(frozen=True)
class ItemDefinitionProbeMaps:
    labels: dict[str, str]
    defaults: dict[str, ItemDefinitionDefaults]


def probe_item_kind(it: SandboxItem) -> str:
    """Sensory kind for cell-probe item summaries (definition-backed items report ``item``)."""
    if it.definition_kind == "item" and it.definition_id:
        return "item"
    return resolved_item_type(it)


def resolved_pickable_energy(
    it: SandboxItem,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> int | None:
    if it.energy is not None:
        return it.energy
    def_id = it.definition_id
    if def_id and definition_defaults and def_id in definition_defaults:
        return definition_defaults[def_id].default_energy
    return None


def resolved_pickable_color(
    it: SandboxItem,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> str | None:
    if it.color is not None:
        return it.color
    def_id = it.definition_id
    if def_id and definition_defaults and def_id in definition_defaults:
        return definition_defaults[def_id].default_color
    return None


def is_solid_item(it: SandboxItem) -> bool:
    if it.role == "solid":
        return True
    t = resolved_item_type(it)
    return t in SOLID_ITEM_TYPES


def is_pickable_item(it: SandboxItem) -> bool:
    if it.role == "pickable":
        return True
    t = resolved_item_type(it)
    return t in PICKABLE_ITEM_TYPES


def is_region_item(it: SandboxItem) -> bool:
    return resolved_item_type(it) == REGION_ITEM_TYPE


def items_at_cell(items: list[SandboxItem], x: int, y: int) -> list[SandboxItem]:
    return [it for it in items if it.position.x == x and it.position.y == y]


def solid_at_cell(items: list[SandboxItem], x: int, y: int) -> SandboxItem | None:
    for it in items_at_cell(items, x, y):
        if is_solid_item(it):
            return it
    return None


def pickables_at_cell(items: list[SandboxItem], x: int, y: int) -> list[SandboxItem]:
    return [it for it in items_at_cell(items, x, y) if is_pickable_item(it)]


def region_at_cell(items: list[SandboxItem], x: int, y: int) -> SandboxItem | None:
    for it in items_at_cell(items, x, y):
        if is_region_item(it):
            return it
    return None


def resolve_pickable_display_label(
    it: SandboxItem,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> str:
    """Display label for cell-probe pickable summaries (mirrors frontend describeRemovableCellItem)."""
    if it.label and it.label.strip():
        return it.label.strip()
    def_id = it.definition_id
    if def_id and definition_labels and def_id in definition_labels:
        return definition_labels[def_id]
    t = resolved_item_type(it)
    energy = resolved_pickable_energy(it, definition_defaults)
    color = resolved_pickable_color(it, definition_defaults)
    if t == "food":
        return f"Food ({energy})" if energy is not None else "Food"
    if t == BALL_ITEM_TYPE:
        return f"Ball ({color})" if color else "Ball"
    return t


def pickable_item_probe_summary(
    it: SandboxItem,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> dict[str, Any]:
    return {
        "id": it.id,
        "kind": probe_item_kind(it),
        "definition_id": it.definition_id,
        "energy": resolved_pickable_energy(it, definition_defaults),
        "color": resolved_pickable_color(it, definition_defaults),
        "label": resolve_pickable_display_label(
            it, definition_labels, definition_defaults
        ),
    }


def cell_pickables_probe_summary(
    items: list[SandboxItem],
    x: int,
    y: int,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    pickables = pickables_at_cell(items, x, y)
    summaries = [
        pickable_item_probe_summary(it, definition_labels, definition_defaults)
        for it in pickables
    ]
    return len(pickables), summaries
