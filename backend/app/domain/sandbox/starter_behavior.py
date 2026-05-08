"""Priority logic from starter_behavior_workflow.md (deterministic)."""

from __future__ import annotations

from app.domain.sandbox.constants import (
    STARTER_ENERGY_SLEEP_THRESHOLD,
    STARTER_HUNGER_SEEK_THRESHOLD,
)
from app.domain.schemas.sandbox import DecisionIntent, GridCell, SandboxTickInput


def _is_nearby8(pet: GridCell, cell: GridCell) -> bool:
    dx = abs(pet.x - cell.x)
    dy = abs(pet.y - cell.y)
    return dx <= 1 and dy <= 1 and (dx + dy) > 0


def starter_behavior_decision(inp: SandboxTickInput) -> DecisionIntent:
    """Return next ``DecisionIntent`` for the starter pet brain."""
    pet = inp.pet
    world = inp.world
    hunger_seek_threshold = STARTER_HUNGER_SEEK_THRESHOLD
    energy_sleep_threshold = STARTER_ENERGY_SLEEP_THRESHOLD

    # 1) Continue in-progress intent
    if pet.intent is not None and pet.intent.status == "in_progress":
        return DecisionIntent(
            action=pet.intent.action,
            target_item_id=pet.intent.target_item_id,
            target_cell=pet.intent.target_cell,
            reason="continue_intent",
        )

    # 2) Eat nearby food
    for it in world.items:
        if it.type == "food" and _is_nearby8(pet.position, it.position):
            return DecisionIntent(
                action="eat_nearby",
                target_item_id=it.id,
                target_cell=None,
                reason="nearby_food",
            )

    # 3) Seek food if hungry
    if pet.hunger > hunger_seek_threshold:
        foods = [x for x in world.items if x.type == "food"]
        if foods:
            return DecisionIntent(
                action="move_to",
                target_item_id=foods[0].id,
                target_cell=None,
                reason="seek_food",
            )

    # 4) Sleep if low energy
    if pet.energy < energy_sleep_threshold:
        return DecisionIntent(action="sleep", target_item_id=None, target_cell=None, reason="low_energy")

    # 5) Wander
    return DecisionIntent(action="wander", target_item_id=None, target_cell=None, reason="wander")
