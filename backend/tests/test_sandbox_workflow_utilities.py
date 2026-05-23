"""Workflow executor coverage for sandbox navigation utility nodes (no LLM)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.engine import initial_sandbox_state_clean
from app.domain.schemas.sandbox import CreatureState, GridCell, SandboxItem, SandboxTickInput


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


def test_sandbox_get_position(client: TestClient):
    tick = _tick_dict(x=4, y=3)
    u_res = _run_utility_graph(client, utility_type="sandbox_get_position", tick=tick, output_kind="dictionary")
    assert u_res["output"]["data"] == {"x": 4, "y": 3}


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
                        "label": "Tick input",
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
