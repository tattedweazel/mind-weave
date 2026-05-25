"""Run region trigger workflows when overlap events fire."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlmodel import Session

from app.domain.sandbox.region_triggers import RegionTriggerEvent, region_item_for_event
from app.domain.schemas.sandbox import (
    FixtureActorContext,
    RegionContext,
    RegionTriggerInput,
    SandboxState,
    SimulationEffects,
    CreatureState,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.workflow_executor.broadcast_message import append_broadcast_segments_from_run
from app.domain.workflow_executor.executor import WorkflowExecutor


def build_region_trigger_input(
    state: SandboxState,
    creature: CreatureState,
    event: RegionTriggerEvent,
) -> RegionTriggerInput:
    region = region_item_for_event(state, event)
    if region is None:
        raise ValueError(f"region not found: {event.region_id}")
    return RegionTriggerInput(
        tick=state.tick,
        mode=event.mode,
        region=RegionContext(
            id=region.id,
            label=region.label,
            position=region.position.model_copy(deep=True),
            definition_id=region.definition_id,
        ),
        actor=FixtureActorContext(
            id=creature.id,
            position=creature.position.model_copy(deep=True),
            facing=creature.facing,
        ),
        trigger_inputs=dict(event.inputs or {}),
        world=state.world.model_copy(deep=True),
    )


async def run_region_trigger_workflow(
    session: Session,
    user_id: Optional[uuid.UUID],
    state: SandboxState,
    creature: CreatureState,
    event: RegionTriggerEvent,
    effects: SimulationEffects,
) -> tuple[WorkflowRunResult | None, str | None]:
    try:
        wf_uuid = uuid.UUID(event.workflow_id)
    except ValueError:
        return None, f"invalid workflow_id: {event.workflow_id}"

    wf = WorkflowDefinitionService(session, user_id).get_workflow(wf_uuid)
    if not wf:
        return None, f"workflow not found: {event.workflow_id}"

    try:
        region_input = build_region_trigger_input(state, creature, event)
    except ValueError as exc:
        return None, str(exc)

    graph = wf.graph if isinstance(wf.graph, dict) else {}
    executor = WorkflowExecutor(session, user_id=user_id)
    input_overrides: dict[str, Any] = {
        "sandbox_region": region_input.model_dump(mode="json"),
        "_simulation_effects": effects,
        **dict(event.inputs or {}),
    }
    try:
        run_result = await executor.run(
            wf,
            input_overrides=input_overrides,
        )
        region_label = region_input.region.label or region_input.region.id
        append_broadcast_segments_from_run(
            effects.broadcast_segments,
            run_result,
            source=f"Region trigger: {region_label}",
        )
        return run_result, None
    except Exception as exc:
        return None, str(exc)
