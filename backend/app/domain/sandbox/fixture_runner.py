"""Run fixture workflows when use_fixture is triggered."""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Optional

from sqlmodel import Session

from app.domain.sandbox.item_helpers import (
    ItemDefinitionDefaults,
    pickable_item_probe_summary,
    pickables_at_cell,
    resolved_item_type,
)
from app.domain.schemas.sandbox import (
    FIXTURE_ITEM_TYPE,
    FixtureActorContext,
    FixtureContext,
    FixtureInteractionInput,
    SandboxItem,
    SandboxState,
    CreatureState,
)
from app.domain.services.sandbox_definition_service import (
    FixtureDefinitionService,
    item_definition_probe_maps,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.workflow_executor.broadcast_message import append_broadcast_segments_from_run
from app.domain.workflow_executor.executor import WorkflowExecutor


class FixtureWorkflowMutations:
    """Collects world mutations during fixture workflow execution."""

    def __init__(self, state: SandboxState):
        self.state = state
        self.removed_ids: set[str] = set()
        self.spawned: list[SandboxItem] = []

    def remove_item_by_id(self, item_id: str) -> bool:
        for it in self.state.world.items:
            if it.id == item_id:
                self.removed_ids.add(item_id)
                self.state.world.items = [x for x in self.state.world.items if x.id != item_id]
                return True
        return False

    def spawn_item(self, item: SandboxItem) -> None:
        self.spawned.append(item)
        self.state.world.items.append(item)


def build_fixture_interaction_input(
    state: SandboxState,
    creature: CreatureState,
    fixture_item: SandboxItem,
    *,
    workflow_id: str | None = None,
    definition_labels: Mapping[str, str] | None = None,
    definition_defaults: Mapping[str, ItemDefinitionDefaults] | None = None,
) -> FixtureInteractionInput:
    cell_items = pickables_at_cell(
        state.world.items,
        fixture_item.position.x,
        fixture_item.position.y,
        definition_defaults,
    )
    summaries = [
        pickable_item_probe_summary(it, definition_labels, definition_defaults)
        for it in cell_items
    ]
    return FixtureInteractionInput(
        tick=state.tick,
        fixture=FixtureContext(
            id=fixture_item.id,
            definition_id=fixture_item.definition_id,
            label=fixture_item.label,
            position=fixture_item.position.model_copy(deep=True),
            workflow_id=workflow_id,
        ),
        actor=FixtureActorContext(
            id=creature.id,
            position=creature.position.model_copy(deep=True),
            facing=creature.facing,
        ),
        cell_items=summaries,
        world=state.world.model_copy(deep=True),
    )


async def run_fixture_workflow(
    session: Session,
    user_id: Optional[uuid.UUID],
    state: SandboxState,
    creature: CreatureState,
    fixture_item: SandboxItem,
    *,
    simulation_effects: Any | None = None,
) -> tuple[WorkflowRunResult | None, str | None]:
    if resolved_item_type(fixture_item) != FIXTURE_ITEM_TYPE:
        return None, "forward cell is not a fixture"
    def_id = fixture_item.definition_id
    workflow_id: str | None = None
    if def_id:
        try:
            row = FixtureDefinitionService(session, user_id).get(uuid.UUID(def_id))
        except ValueError:
            row = None
        if row:
            workflow_id = row.workflow_id
    if not workflow_id:
        return None, "fixture has no resolvable workflow_id"
    try:
        wf_uuid = uuid.UUID(workflow_id)
    except ValueError:
        return None, f"invalid workflow_id: {workflow_id}"
    wf = WorkflowDefinitionService(session, user_id).get_workflow(wf_uuid)
    if not wf:
        return None, f"workflow not found: {workflow_id}"
    probe_maps = item_definition_probe_maps(session, user_id)
    fx_input = build_fixture_interaction_input(
        state,
        creature,
        fixture_item,
        workflow_id=workflow_id,
        definition_labels=probe_maps.labels,
        definition_defaults=probe_maps.defaults,
    )
    mutations = FixtureWorkflowMutations(state)
    graph = wf.graph if isinstance(wf.graph, dict) else {}
    executor = WorkflowExecutor(session, user_id=user_id)
    try:
        run_result = await executor.run(
            wf,
            input_overrides={
                "sandbox_fixture": fx_input.model_dump(mode="json"),
                "_fixture_mutations": mutations,
            },
        )
        if simulation_effects is not None and hasattr(simulation_effects, "broadcast_segments"):
            fix_label = fixture_item.label or fixture_item.id
            append_broadcast_segments_from_run(
                simulation_effects.broadcast_segments,
                run_result,
                source=f"Fixture: {fix_label}",
            )
        return run_result, None
    except Exception as exc:
        return None, str(exc)
