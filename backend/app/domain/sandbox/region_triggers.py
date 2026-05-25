"""Region trigger overlap evaluation and event dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.domain.schemas.sandbox import (
    CreatureState,
    GridCell,
    RegionTriggerConfig,
    RegionTriggerMode,
    RegionTriggerSessionState,
    SandboxItem,
    SandboxState,
    default_region_trigger,
)
from app.domain.sandbox.item_helpers import region_at_cell


@dataclass(frozen=True)
class RegionTriggerEvent:
    creature_id: str
    region_id: str
    mode: RegionTriggerMode
    workflow_id: str
    inputs: dict[str, Any]
    region_item: SandboxItem


def _trigger_for_region(region: SandboxItem) -> RegionTriggerConfig:
    return region.trigger or default_region_trigger()


def _event_if_enabled(
    *,
    creature_id: str,
    region: SandboxItem,
    mode: RegionTriggerMode,
) -> RegionTriggerEvent | None:
    trigger = _trigger_for_region(region)
    if not trigger.enabled or trigger.mode != mode or not trigger.workflow_id:
        return None
    return RegionTriggerEvent(
        creature_id=creature_id,
        region_id=region.id,
        mode=mode,
        workflow_id=trigger.workflow_id,
        inputs=dict(trigger.inputs or {}),
        region_item=region,
    )


def evaluate_transition_triggers(
    state: SandboxState,
    *,
    creature: CreatureState,
    previous_position: GridCell,
    session_state: RegionTriggerSessionState,
) -> tuple[list[RegionTriggerEvent], RegionTriggerSessionState]:
    """Evaluate enter, exit, and on_enter_once triggers after a creature moves."""
    prev_region = region_at_cell(state.world.items, previous_position.x, previous_position.y)
    curr_region = region_at_cell(state.world.items, creature.position.x, creature.position.y)
    prev_id = prev_region.id if prev_region else None
    curr_id = curr_region.id if curr_region else None

    events: list[RegionTriggerEvent] = []
    next_session = session_state.model_copy(deep=True)

    if prev_region is not None and prev_id != curr_id:
        ev = _event_if_enabled(creature_id=creature.id, region=prev_region, mode="exit")
        if ev is not None:
            events.append(ev)

    if curr_region is not None and curr_id != prev_id:
        ev = _event_if_enabled(creature_id=creature.id, region=curr_region, mode="enter")
        if ev is not None:
            events.append(ev)

        once_ev = _event_if_enabled(creature_id=creature.id, region=curr_region, mode="on_enter_once")
        if once_ev is not None:
            fired = set(next_session.enter_once_fired.get(creature.id, []))
            if curr_region.id not in fired:
                events.append(once_ev)
                fired.add(curr_region.id)
                next_session.enter_once_fired[creature.id] = sorted(fired)

    return events, next_session


def evaluate_while_inside_triggers(
    state: SandboxState,
    *,
    session_state: RegionTriggerSessionState,
) -> list[RegionTriggerEvent]:
    """Evaluate while_inside triggers for every creature at end of tick."""
    _ = session_state
    events: list[RegionTriggerEvent] = []
    for creature in state.creatures:
        region = region_at_cell(state.world.items, creature.position.x, creature.position.y)
        if region is None:
            continue
        ev = _event_if_enabled(creature_id=creature.id, region=region, mode="while_inside")
        if ev is not None:
            events.append(ev)
    return events


def region_item_for_event(state: SandboxState, event: RegionTriggerEvent) -> Optional[SandboxItem]:
    for it in state.world.items:
        if it.id == event.region_id:
            return it
    return event.region_item
