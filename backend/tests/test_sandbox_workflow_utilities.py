"""Workflow executor coverage for sandbox navigation utility nodes (no LLM)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.engine import initial_sandbox_state_clean
from app.domain.sandbox.fixture_runner import build_fixture_interaction_input
from app.domain.schemas.sandbox import (
    FIXTURE_ITEM_TYPE,
    CreatureState,
    GridCell,
    SandboxItem,
    SandboxTickInput,
)


def _tick_dict(*, x: int = 2, y: int = 2, facing: str = "N", items: list | None = None):
    st = initial_sandbox_state_clean()
    c = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=x, y=y),
        facing=facing,  # type: ignore[arg-type]
    )
    if items:
        for it in items:
            st.world.items.append(SandboxItem.model_validate(it))
    return SandboxTickInput(
        tick=1, creature=c, creatures=[c], world=st.world, recent_actions=[]
    ).model_dump(mode="json")


def _fixture_dict(*, actor_x: int = 4, actor_y: int = 3, facing: str = "N") -> dict:
    st = initial_sandbox_state_clean()
    creature = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=actor_x, y=actor_y),
        facing=facing,  # type: ignore[arg-type]
    )
    st.creatures = [creature]
    st.tick = 1
    fixture_item = SandboxItem(
        id="fx1",
        type=FIXTURE_ITEM_TYPE,
        definition_kind="fixture",
        position=GridCell(x=actor_x, y=actor_y - 1),
        label="Door",
    )
    st.world.items.append(fixture_item)
    return build_fixture_interaction_input(st, creature, fixture_item).model_dump(mode="json")


def _run_start_utility_with_overrides(
    client: TestClient,
    *,
    utility_type: str,
    input_overrides: dict,
    output_kind: str = "dictionary",
):
    u_id, stop_id = "n_util", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"sandbox {utility_type} override {uuid.uuid4().hex[:8]}",
            "graph": {
                "nodes": [
                    {
                        "id": "start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": utility_type,
                        "label": utility_type,
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": output_kind}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "start", "target": u_id, "source_handle": "trigger", "target_handle": "trigger"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"input_overrides": input_overrides},
    )
    assert run_res.status_code == 200
    result = run_res.json()
    u_res = next(r for r in result["node_results"] if r["node_id"] == u_id)
    return result, u_res


def _run_utility_graph(client: TestClient, *, utility_type: str, tick: dict, output_kind: str):
    d_id, u_id, stop_id = "n_dict", "n_util", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"sandbox {utility_type}",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": utility_type,
                        "label": utility_type,
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": output_kind}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": u_id, "source_handle": "output", "target_handle": "input"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next(r for r in result["node_results"] if r["node_id"] == u_id)
    return u_res


def _empty_probe_tail() -> dict:
    return {"stack_count": 0, "items": []}


def test_sandbox_get_position(client: TestClient):
    tick = _tick_dict(x=4, y=3)
    u_res = _run_utility_graph(client, utility_type="sandbox_get_position", tick=tick, output_kind="dictionary")
    assert u_res["output"]["data"] == {
        "x": 4,
        "y": 3,
        "kind": "empty",
        "region_label": None,
        **_empty_probe_tail(),
    }


def test_sandbox_get_position_includes_region_label(client: TestClient):
    tick = _tick_dict(
        x=2,
        y=2,
        items=[
            {
                "id": "r1",
                "type": "region",
                "position": {"x": 2, "y": 2},
                "color": "#3B82F6",
                "label": "Goal",
            },
        ],
    )
    u_res = _run_utility_graph(client, utility_type="sandbox_get_position", tick=tick, output_kind="dictionary")
    assert u_res["output"]["data"] == {
        "x": 2,
        "y": 2,
        "kind": "empty",
        "region_label": "Goal",
        **_empty_probe_tail(),
    }


def test_sandbox_get_position_from_fixture_override(client: TestClient):
    fx = _fixture_dict(actor_x=5, actor_y=2)
    _, u_res = _run_start_utility_with_overrides(
        client,
        utility_type="sandbox_get_position",
        input_overrides={"sandbox_fixture": fx},
    )
    assert u_res["status"] == "ok"
    assert u_res["output"]["data"] == {
        "x": 5,
        "y": 1,
        "kind": "fixture",
        "region_label": None,
        **_empty_probe_tail(),
    }


def test_sandbox_get_position_from_fixture_with_stacked_pickable(client: TestClient):
    item_def = client.post(
        "/api/v1/sandbox-definitions/items",
        json={
            "name": f"Key item {uuid.uuid4().hex[:8]}",
            "label": "Key",
            "pickable": True,
        },
    )
    assert item_def.status_code == 201, item_def.text
    def_id = item_def.json()["id"]

    st = initial_sandbox_state_clean()
    creature = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=4, y=4),
        facing="N",
    )
    st.creatures = [creature]
    st.tick = 1
    fixture_item = SandboxItem(
        id="fx1",
        type=FIXTURE_ITEM_TYPE,
        definition_kind="fixture",
        position=GridCell(x=4, y=3),
        label="Door",
    )
    key_item = SandboxItem(
        id="k1",
        type="food",
        definition_id=def_id,
        definition_kind="item",
        role="pickable",
        position=GridCell(x=4, y=3),
        energy=10,
    )
    st.world.items.extend([fixture_item, key_item])
    fx = build_fixture_interaction_input(st, creature, fixture_item).model_dump(mode="json")
    _, u_res = _run_start_utility_with_overrides(
        client,
        utility_type="sandbox_get_position",
        input_overrides={"sandbox_fixture": fx},
    )
    data = u_res["output"]["data"]
    assert data["x"] == 4 and data["y"] == 3
    assert data["kind"] == "fixture"
    assert data["stack_count"] == 1
    assert data["items"][0]["kind"] == "item"
    assert data["items"][0]["label"] == "Key"
    assert data["items"][0]["energy"] == 10


def test_sandbox_get_cell_items_from_fixture_with_stacked_pickable(client: TestClient):
    item_def = client.post(
        "/api/v1/sandbox-definitions/items",
        json={
            "name": f"Key item {uuid.uuid4().hex[:8]}",
            "label": "Key",
            "pickable": True,
        },
    )
    assert item_def.status_code == 201, item_def.text
    def_id = item_def.json()["id"]

    st = initial_sandbox_state_clean()
    creature = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=4, y=4),
        facing="N",
    )
    st.creatures = [creature]
    st.tick = 1
    fixture_item = SandboxItem(
        id="fx1",
        type=FIXTURE_ITEM_TYPE,
        definition_kind="fixture",
        position=GridCell(x=4, y=3),
        label="Door",
    )
    key_item = SandboxItem(
        id="k1",
        type="food",
        definition_id=def_id,
        definition_kind="item",
        role="pickable",
        position=GridCell(x=4, y=3),
        energy=10,
    )
    st.world.items.extend([fixture_item, key_item])
    fx = build_fixture_interaction_input(st, creature, fixture_item).model_dump(mode="json")
    _, u_res = _run_start_utility_with_overrides(
        client,
        utility_type="sandbox_get_cell_items",
        input_overrides={"sandbox_fixture": fx},
        output_kind="list",
    )
    items = u_res["output"]["data"]
    assert len(items) == 1
    assert items[0]["id"] == "k1"
    assert items[0]["definition_id"] == def_id
    assert items[0]["kind"] == "item"


@pytest.mark.asyncio
async def test_sandbox_remove_and_spawn_item_at_cell_with_mutations(db_session):
    from sqlmodel import select

    from app.domain.sandbox.fixture_runner import FixtureWorkflowMutations, build_fixture_interaction_input
    from app.domain.services.workflow_executor import WorkflowExecutor
    from app.persistence.tables import User, WorkflowDefinition

    user = db_session.exec(select(User)).first()
    assert user is not None

    reward_def_id = str(uuid.uuid4())
    st = initial_sandbox_state_clean()
    creature = CreatureState(
        id="c1",
        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
        position=GridCell(x=4, y=4),
        facing="N",
    )
    st.creatures = [creature]
    st.tick = 1
    fixture_item = SandboxItem(
        id="fx1",
        type=FIXTURE_ITEM_TYPE,
        definition_kind="fixture",
        position=GridCell(x=4, y=3),
        label="Door",
    )
    key_item = SandboxItem(
        id="k1",
        type="food",
        definition_id=str(uuid.uuid4()),
        definition_kind="item",
        role="pickable",
        position=GridCell(x=4, y=3),
        energy=10,
    )
    st.world.items.extend([fixture_item, key_item])
    fx = build_fixture_interaction_input(st, creature, fixture_item).model_dump(mode="json")
    mutations = FixtureWorkflowMutations(st)

    remove_id, spawn_id, stop_id = "n_remove", "n_spawn", "n_stop"
    wf_id = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(
            id=wf_id,
            user_id=user.id,
            name="fixture remove spawn",
            graph={
                "nodes": [
                    {
                        "id": "start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": remove_id,
                        "kind": "utility",
                        "utility_type": "sandbox_remove_item_at_cell",
                        "label": "Remove Item",
                        "data": {
                            "required_inputs": [
                                {"key": "item_id", "type": "string", "value": "k1"},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": spawn_id,
                        "kind": "utility",
                        "utility_type": "sandbox_spawn_item_at_cell",
                        "label": "Spawn Item",
                        "data": {
                            "required_inputs": [
                                {"key": "definition_id", "type": "string", "value": reward_def_id},
                                {"key": "target", "type": "string", "value": "self"},
                            ],
                        },
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 600, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "start", "target": remove_id, "source_handle": "trigger", "target_handle": "trigger"},
                    {"source": remove_id, "target": spawn_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": spawn_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        )
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_id)
    assert wf is not None

    ex = WorkflowExecutor(db_session, user.id)
    result = await ex.run(
        wf,
        input_overrides={
            "sandbox_fixture": fx,
            "_fixture_mutations": mutations,
        },
    )
    assert result.status == "ok"
    remove_res = next(r for r in result.node_results if r.node_id == remove_id)
    spawn_res = next(r for r in result.node_results if r.node_id == spawn_id)
    assert remove_res.output is not None
    assert spawn_res.output is not None
    remove_data = remove_res.output.data  # type: ignore[union-attr]
    spawn_data = spawn_res.output.data  # type: ignore[union-attr]
    assert remove_data["removed"] is True
    assert remove_data["item_id"] == "k1"
    assert spawn_data["position"] == {"x": 4, "y": 3}
    spawned_id = spawn_data["spawned_id"]
    item_ids = {it.id for it in st.world.items}
    assert "k1" not in item_ids
    assert spawned_id in item_ids
    spawned = next(it for it in st.world.items if it.id == spawned_id)
    assert spawned.definition_id == reward_def_id
    assert spawned.position.x == 4 and spawned.position.y == 3


def test_sandbox_get_position_from_sandbox_tick_override(client: TestClient):
    tick = _tick_dict(x=1, y=7)
    _, u_res = _run_start_utility_with_overrides(
        client,
        utility_type="sandbox_get_position",
        input_overrides={"sandbox_tick": tick},
    )
    assert u_res["status"] == "ok"
    assert u_res["output"]["data"]["x"] == 1
    assert u_res["output"]["data"]["y"] == 7


def test_tick_dict_from_fixture_dict_unit():
    from app.domain.sandbox.query import creature_position_from_tick_dict, tick_dict_from_fixture_dict

    fx = _fixture_dict(actor_x=3, actor_y=6, facing="E")
    tick = tick_dict_from_fixture_dict(fx)
    assert tick["creature"]["id"] == "c1"
    assert tick["creature"]["position"] == {"x": 3, "y": 6}
    cell = creature_position_from_tick_dict(tick)
    assert cell["x"] == 3
    assert cell["y"] == 6
    assert cell["stack_count"] == 0


def test_sandbox_get_facing(client: TestClient):
    tick = _tick_dict(facing="E")
    u_res = _run_utility_graph(client, utility_type="sandbox_get_facing", tick=tick, output_kind="string")
    assert u_res["output"]["text"] == "E"


def test_sandbox_get_nearby(client: TestClient):
    tick = _tick_dict(
        x=2,
        y=2,
        items=[{"id": "w1", "type": "wall", "position": {"x": 2, "y": 1}}],
    )
    u_res = _run_utility_graph(client, utility_type="sandbox_get_nearby", tick=tick, output_kind="list")
    cells = u_res["output"]["data"]
    assert len(cells) == 8
    assert cells[0]["kind"] == "wall"
    assert cells[0]["region_label"] is None


def test_sandbox_get_nearby_includes_region_label(client: TestClient):
    tick = _tick_dict(
        x=2,
        y=2,
        items=[
            {
                "id": "r1",
                "type": "region",
                "position": {"x": 2, "y": 1},
                "color": "#3B82F6",
                "label": "target",
            },
        ],
    )
    u_res = _run_utility_graph(client, utility_type="sandbox_get_nearby", tick=tick, output_kind="list")
    cells = u_res["output"]["data"]
    assert cells[0]["kind"] == "empty"
    assert cells[0]["region_label"] == "target"


def test_sandbox_move_forward_action(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_move_forward",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    assert u_res["output"]["data"]["action"] == "move_forward"


def test_sandbox_turn_left_action(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_turn_left",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    assert u_res["output"]["data"]["action"] == "turn_left"


def test_sandbox_turn_right_action(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_turn_right",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    assert u_res["output"]["data"]["action"] == "turn_right"


def test_sandbox_idle_action(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_idle",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    assert u_res["output"]["data"]["action"] == "idle"


def test_sandbox_pick_up_item_action(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_pick_up_item",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    assert u_res["output"]["data"]["action"] == "pick_up_item"


def test_sandbox_place_item_action_with_filter(client: TestClient):
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_place_item",
        tick=_tick_dict(),
        output_kind="dictionary",
    )
    data = u_res["output"]["data"]
    assert data["action"] == "place_item"
    assert data.get("item_type") is None


def test_sandbox_get_inventory(client: TestClient):
    tick = _tick_dict()
    tick["creature"]["inventory"] = [{"type": "ball", "color": "#3B82F6"}]
    u_res = _run_utility_graph(
        client,
        utility_type="sandbox_get_inventory",
        tick=tick,
        output_kind="list",
    )
    assert u_res["output"]["data"] == [{"type": "ball", "color": "#3B82F6"}]


def test_sandbox_tick_primitive(client: TestClient):
    tick = _tick_dict()
    wf_id = str(uuid.uuid4())
    d_id, p_id, stop_id = "start", "tick_prim", "stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox tick primitive",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": p_id,
                        "kind": "primitive",
                        "primitive_type": "sandbox_tick",
                        "label": "Tick Input",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": p_id, "source_handle": "output", "target_handle": "input"},
                    {"source": p_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    run_res = client.post(f"/api/v1/workflow-definitions/{workflow_res.json()['id']}/run")
    assert run_res.status_code == 200
    p_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == p_id)
    assert p_res["output"]["data"]["creature"]["facing"] == "N"


def _prompt_user_action_graph_nodes(*, u_id: str = "n_prompt", stop_id: str = "n_stop"):
    return [
        {
            "id": "start",
            "kind": "start",
            "label": "Start",
            "data": {
                "required_inputs": [
                    {"key": "sandbox_tick", "type": "dictionary", "value": None},
                ],
            },
            "position": {"x": 0, "y": 0},
        },
        {
            "id": u_id,
            "kind": "utility",
            "utility_type": "sandbox_prompt_user_action",
            "label": "Prompt for User Action",
            "data": {},
            "position": {"x": 200, "y": 0},
        },
        {
            "id": stop_id,
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
            "position": {"x": 400, "y": 0},
        },
    ]


def test_sandbox_prompt_user_action_emits_decision(client: TestClient):
    u_id, stop_id = "n_prompt", "n_stop"
    tick = _tick_dict()
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt user action",
            "graph": {
                "nodes": _prompt_user_action_graph_nodes(u_id=u_id, stop_id=stop_id),
                "edges": [
                    {
                        "source": "start",
                        "target": u_id,
                        "source_handle": "sandbox_tick",
                        "target_handle": "input",
                    },
                    {
                        "source": u_id,
                        "target": stop_id,
                        "source_handle": "output",
                        "target_handle": "output",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={
            "input_overrides": {
                "sandbox_tick": tick,
                "sandbox_user_action": {"action": "turn_left"},
            },
        },
    )
    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    u_res = next(r for r in result["node_results"] if r["node_id"] == u_id)
    assert u_res["status"] == "ok"
    data = u_res["output"]["data"]
    assert data["action"] == "turn_left"
    assert data["reason"] == "user: turn_left"
    assert u_res["details"]["user_action_source"] == "simulation_prompt"


def test_sandbox_prompt_user_action_missing_override_errors(client: TestClient):
    u_id, stop_id = "n_prompt", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt missing action",
            "graph": {
                "nodes": _prompt_user_action_graph_nodes(u_id=u_id, stop_id=stop_id),
                "edges": [
                    {
                        "source": u_id,
                        "target": stop_id,
                        "source_handle": "output",
                        "target_handle": "output",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={"input_overrides": {"sandbox_tick": _tick_dict()}},
    )
    assert run_res.status_code == 200
    u_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == u_id)
    assert u_res["status"] == "error"
    assert "simulation user action" in (u_res.get("error") or "").lower()


def test_sandbox_prompt_user_action_place_item_reason(client: TestClient):
    u_id, stop_id = "n_prompt", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt place",
            "graph": {
                "nodes": _prompt_user_action_graph_nodes(u_id=u_id, stop_id=stop_id),
                "edges": [
                    {
                        "source": u_id,
                        "target": stop_id,
                        "source_handle": "output",
                        "target_handle": "output",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={
            "input_overrides": {
                "sandbox_tick": _tick_dict(),
                "sandbox_user_action": {"action": "place_item", "item_type": "food"},
            },
        },
    )
    assert run_res.status_code == 200
    u_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == u_id)
    assert u_res["output"]["data"]["action"] == "place_item"
    assert u_res["output"]["data"]["item_type"] == "food"
    assert u_res["output"]["data"]["reason"] == "user: place_item:food"


def test_sandbox_prompt_user_action_place_item_with_inventory_index(client: TestClient):
    u_id, stop_id = "n_prompt", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt place index",
            "graph": {
                "nodes": _prompt_user_action_graph_nodes(u_id=u_id, stop_id=stop_id),
                "edges": [
                    {
                        "source": u_id,
                        "target": stop_id,
                        "source_handle": "output",
                        "target_handle": "output",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(
        f"/api/v1/workflow-definitions/{wf_id}/run",
        json={
            "input_overrides": {
                "sandbox_tick": _tick_dict(),
                "sandbox_user_action": {
                    "action": "place_item",
                    "item_type": "ball",
                    "inventory_index": 1,
                },
            },
        },
    )
    assert run_res.status_code == 200
    u_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == u_id)
    assert u_res["output"]["data"]["action"] == "place_item"
    assert u_res["output"]["data"]["item_type"] == "ball"
    assert u_res["output"]["data"]["inventory_index"] == 1
    assert u_res["output"]["data"]["reason"] == "user: place_item:ball@1"


def test_nearby_region_label_null_dictionary_value_by_key_errors_without_fallback(client: TestClient):
    """Sandbox nearby cells always include region_label; null values need dvbk fallback."""
    tick = _tick_dict(x=2, y=2)
    nearby_id, idx_id, dvbk_id, stop_id = "n_nearby", "n_idx", "n_dvbk", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "nearby region_label null dvbk",
            "graph": {
                "nodes": [
                    {
                        "id": "n_tick",
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": nearby_id,
                        "kind": "utility",
                        "utility_type": "sandbox_get_nearby",
                        "label": "Get nearby",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": idx_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Forward cell",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 0},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": dvbk_id,
                        "kind": "utility",
                        "utility_type": "dictionary_value_by_key",
                        "label": "region_label",
                        "data": {
                            "output_value_type": "string",
                            "required_inputs": [
                                {"key": "key", "type": "string", "value": "region_label"},
                                {"key": "dictionary", "type": "dictionary", "value": None},
                                {"key": "fallback", "type": "any", "value": None},
                            ],
                        },
                        "position": {"x": 600, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 800, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_tick", "target": nearby_id, "source_handle": "output", "target_handle": "input"},
                    {"source": nearby_id, "target": idx_id, "source_handle": "output", "target_handle": "list"},
                    {"source": idx_id, "target": dvbk_id, "source_handle": "output", "target_handle": "dictionary"},
                    {"source": dvbk_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    dvbk_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == dvbk_id)
    assert dvbk_res["status"] == "error"
    assert "region_label" in (dvbk_res.get("error") or "").lower()
    assert "null" in (dvbk_res.get("error") or "").lower()


def test_nearby_region_label_null_dictionary_value_by_key_uses_fallback(client: TestClient):
    tick = _tick_dict(x=2, y=2)
    nearby_id, idx_id, dvbk_id, stop_id = "n_nearby2", "n_idx2", "n_dvbk2", "n_stop2"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "nearby region_label fallback",
            "graph": {
                "nodes": [
                    {
                        "id": "n_tick",
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "tick",
                        "data": tick,
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": nearby_id,
                        "kind": "utility",
                        "utility_type": "sandbox_get_nearby",
                        "label": "Get nearby",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": idx_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "Forward cell",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 0},
                                {"key": "list", "type": "list", "value": None},
                            ]
                        },
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": dvbk_id,
                        "kind": "utility",
                        "utility_type": "dictionary_value_by_key",
                        "label": "region_label",
                        "data": {
                            "output_value_type": "string",
                            "fallback_value": "",
                            "required_inputs": [
                                {"key": "key", "type": "string", "value": "region_label"},
                                {"key": "dictionary", "type": "dictionary", "value": None},
                                {"key": "fallback", "type": "any", "value": ""},
                            ],
                        },
                        "position": {"x": 600, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 800, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_tick", "target": nearby_id, "source_handle": "output", "target_handle": "input"},
                    {"source": nearby_id, "target": idx_id, "source_handle": "output", "target_handle": "list"},
                    {"source": idx_id, "target": dvbk_id, "source_handle": "output", "target_handle": "dictionary"},
                    {"source": dvbk_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    dvbk_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == dvbk_id)
    assert dvbk_res["status"] == "ok"
    assert dvbk_res["output"]["text"] == ""


def test_sandbox_force_simulation_pause_requires_simulation_context(client: TestClient):
    u_id, stop_id = "n_pause", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox force pause",
            "graph": {
                "nodes": [
                    {
                        "id": "start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": u_id,
                        "kind": "utility",
                        "utility_type": "sandbox_force_simulation_pause",
                        "label": "Force Simulation Pause",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "start", "target": u_id, "source_handle": "trigger", "target_handle": "trigger"},
                    {"source": u_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    u_res = next(r for r in run_res.json()["node_results"] if r["node_id"] == u_id)
    assert u_res["status"] == "error"
    assert "simulation" in (u_res.get("error") or "").lower()

