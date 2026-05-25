"""Sandbox HTTP API tests."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID, STARTER_SANDBOX_WORKFLOW_ID
from app.domain.schemas.sandbox import (
    BoardCreaturePlacement,
    BoardDefinition,
    GridCell,
    RegionTriggerConfig,
    SandboxItem,
    WorldGrid,
)
from app.persistence.tables import User, WorkflowDefinition
from tests.conftest import engine


def _board_with_creature(client: TestClient) -> str:
    r = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Test board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
                        position=GridCell(x=4, y=4),
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_sandbox_boards_crud(client: TestClient):
    r = client.get("/api/v1/sandbox/boards")
    assert r.status_code == 200
    boards = r.json()["boards"]
    assert any(b["name"] == "Empty Board" for b in boards)

    board_id = _board_with_creature(client)
    g = client.get(f"/api/v1/sandbox/boards/{board_id}")
    assert g.status_code == 200
    assert len(g.json()["definition"]["creatures"]) == 1

    dup = client.post(f"/api/v1/sandbox/boards/{board_id}/duplicate", json={"name": "Copy"})
    assert dup.status_code == 200
    assert dup.json()["name"] == "Copy"

    d = client.delete(f"/api/v1/sandbox/boards/{board_id}")
    assert d.status_code == 200


def test_sandbox_board_rename(client: TestClient):
    board_id = _board_with_creature(client)

    renamed = client.patch(f"/api/v1/sandbox/boards/{board_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    unchanged = client.patch(f"/api/v1/sandbox/boards/{board_id}", json={"name": "   "})
    assert unchanged.status_code == 200
    assert unchanged.json()["name"] == "Renamed"

    system_patch = client.patch(
        f"/api/v1/sandbox/boards/{EMPTY_SANDBOX_BOARD_ID}",
        json={"name": "Nope"},
    )
    assert system_patch.status_code == 404


def test_sandbox_session_create_and_tick(client: TestClient):
    board_id = _board_with_creature(client)
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert r.status_code == 200
    data = r.json()
    doc_id = data["document_id"]
    v0 = data["envelope"]["state_version"]
    assert data["envelope"]["board_id"] == board_id
    assert len(data["envelope"]["sandbox"]["creatures"]) == 1

    t = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert t.status_code == 200
    body = t.json()
    env = body["envelope"]
    assert env["state_version"] == v0 + 1
    assert env["sandbox"]["tick"] >= 1
    runs = body.get("last_workflow_runs") or {}
    assert len(runs) == 1
    creature_id = env["sandbox"]["creatures"][0]["id"]
    assert runs[creature_id] is not None
    assert runs[creature_id]["status"] == "ok"
    last_errors = env.get("last_errors") or {}
    assert last_errors.get(creature_id) is None
    assert env["sandbox"]["creatures"][0]["position"]["y"] == 3


def test_sandbox_session_from_empty_board(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    assert r.status_code == 200
    env = r.json()["envelope"]
    assert env["sandbox"]["creatures"] == []


def test_sandbox_place_creature_via_tick(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]

    t = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={
            "interactions": [
                {
                    "type": "place_creature",
                    "cell": {"x": 2, "y": 2},
                    "workflow_id": str(STARTER_SANDBOX_WORKFLOW_ID),
                    "color": "#3B82F6",
                }
            ],
            "state_version": v0,
        },
    )
    assert t.status_code == 200
    assert len(t.json()["envelope"]["sandbox"]["creatures"]) == 1


def test_sandbox_place_creature_via_tick(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]

    t = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={
            "interactions": [
                {
                    "type": "place_creature",
                    "cell": {"x": 2, "y": 2},
                    "workflow_id": str(STARTER_SANDBOX_WORKFLOW_ID),
                    "color": "#3B82F6",
                }
            ],
            "state_version": v0,
        },
    )
    assert t.status_code == 200
    assert len(t.json()["envelope"]["sandbox"]["creatures"]) == 1


def test_sandbox_apply_interactions_without_tick(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]
    assert r.json()["envelope"]["sandbox"]["tick"] == 0

    applied = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/interactions",
        json={
            "interactions": [
                {
                    "type": "place_creature",
                    "cell": {"x": 2, "y": 2},
                    "workflow_id": str(STARTER_SANDBOX_WORKFLOW_ID),
                    "facing": "E",
                    "color": "#FF0000",
                }
            ],
            "state_version": v0,
        },
    )
    assert applied.status_code == 200
    env = applied.json()["envelope"]
    assert env["state_version"] == v0 + 1
    assert env["sandbox"]["tick"] == 0
    assert len(env["sandbox"]["creatures"]) == 1
    assert env["sandbox"]["creatures"][0]["facing"] == "E"
    assert env["sandbox"]["creatures"][0]["color"] == "#FF0000"
    assert "last_workflow_runs" not in applied.json()


def test_sandbox_apply_interactions_rejects_when_not_paused(client: TestClient, db_session):
    import json

    from app.domain.document_json import deterministic_json_dumps
    from app.persistence.tables import Document

    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = uuid.UUID(r.json()["document_id"])
    v0 = r.json()["envelope"]["state_version"]

    doc = db_session.get(Document, doc_id)
    assert doc is not None
    env = json.loads(doc.body)
    env["playback"] = {**(env.get("playback") or {}), "paused": False}
    doc.body = deterministic_json_dumps(env)
    db_session.add(doc)
    db_session.commit()

    r2 = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/interactions",
        json={
            "interactions": [
                {
                    "type": "place_item",
                    "cell": {"x": 1, "y": 1},
                    "item_type": "wall",
                }
            ],
            "state_version": v0,
        },
    )
    assert r2.status_code == 422


def test_sandbox_save_session_as_board(client: TestClient):
    board_id = _board_with_creature(client)
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]

    client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={
            "interactions": [{"type": "place_item", "cell": {"x": 1, "y": 1}, "item_type": "wall"}],
            "state_version": v0,
        },
    )
    v1 = client.get(f"/api/v1/sandbox/sessions/{doc_id}").json()["envelope"]["state_version"]

    saved = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/save-board",
        json={"mode": "save_as_new", "name": "Saved layout"},
    )
    assert saved.status_code == 200
    assert saved.json()["name"] == "Saved layout"
    assert any(it["type"] == "wall" for it in saved.json()["definition"]["items"])


def test_sandbox_resize_grid_paused_only_and_version(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    assert r.status_code == 200
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]

    bad = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 12, "height": 10, "state_version": v0 + 9},
    )
    assert bad.status_code == 409

    ok = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 12, "height": 10, "state_version": v0},
    )
    assert ok.status_code == 200
    env = ok.json()["envelope"]
    assert env["sandbox"]["world"]["grid"]["width"] == 12


def test_sandbox_place_and_remove_region(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]

    placed = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/interactions",
        json={
            "interactions": [
                {"type": "place_region", "cell": {"x": 2, "y": 2}, "color": "#AABBCC"},
            ],
            "state_version": v0,
        },
    )
    assert placed.status_code == 200
    items = placed.json()["envelope"]["sandbox"]["world"]["items"]
    assert any(it["type"] == "region" and it["color"] == "#AABBCC" for it in items)
    v1 = placed.json()["envelope"]["state_version"]

    removed = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/interactions",
        json={
            "interactions": [{"type": "remove_region", "cell": {"x": 2, "y": 2}}],
            "state_version": v1,
        },
    )
    assert removed.status_code == 200
    assert not any(it["type"] == "region" for it in removed.json()["envelope"]["sandbox"]["world"]["items"])


def test_sandbox_resize_grid_rejects_when_not_paused(client: TestClient, db_session):
    import json

    from app.domain.document_json import deterministic_json_dumps
    from app.persistence.tables import Document

    r = client.post("/api/v1/sandbox/sessions", json={"board_id": str(EMPTY_SANDBOX_BOARD_ID)})
    doc_id = uuid.UUID(r.json()["document_id"])
    v0 = r.json()["envelope"]["state_version"]

    doc = db_session.get(Document, doc_id)
    assert doc is not None
    env = json.loads(doc.body)
    env["playback"] = {**(env.get("playback") or {}), "paused": False}
    doc.body = deterministic_json_dumps(env)
    db_session.add(doc)
    db_session.commit()

    r2 = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 10, "height": 10, "state_version": v0},
    )
    assert r2.status_code == 422


def _prompt_user_action_graph(*, u_id: str = "n_prompt", stop_id: str = "n_stop"):
    return {
        "nodes": [
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
        ],
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
    }


def _board_with_prompt_creature(client: TestClient, workflow_id: str) -> str:
    r = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Prompt brain board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c-prompt",
                        workflow_id=workflow_id,
                        position=GridCell(x=4, y=4),
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_sandbox_tick_with_creature_user_actions(client: TestClient):
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt user action session",
            "graph": _prompt_user_action_graph(),
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    board_id = _board_with_prompt_creature(client, wf_id)
    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert session_res.status_code == 200
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]
    creature_id = session_res.json()["envelope"]["sandbox"]["creatures"][0]["id"]
    assert creature_id == "c-prompt"

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={
            "interactions": [],
            "state_version": v0,
            "creature_user_actions": {creature_id: {"action": "move_forward"}},
        },
    )
    assert tick_res.status_code == 200, tick_res.text
    body = tick_res.json()
    env = body["envelope"]
    assert env["state_version"] == v0 + 1
    assert env["sandbox"]["creatures"][0]["position"]["y"] == 3
    runs = body.get("last_workflow_runs") or {}
    assert runs[creature_id]["status"] == "ok"
    assert env.get("last_errors", {}).get(creature_id) is None


def test_sandbox_tick_creature_user_actions_place_item(client: TestClient):
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt place item session",
            "graph": _prompt_user_action_graph(),
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    board_id = _board_with_prompt_creature(client, wf_id)
    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]
    creature_id = session_res.json()["envelope"]["sandbox"]["creatures"][0]["id"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={
            "interactions": [],
            "state_version": v0,
            "creature_user_actions": {
                creature_id: {"action": "place_item", "item_type": "food"},
            },
        },
    )
    assert tick_res.status_code == 200, tick_res.text
    runs = tick_res.json().get("last_workflow_runs") or {}
    assert runs[creature_id]["status"] == "ok"


def test_sandbox_tick_prompt_brain_missing_user_action_records_error(client: TestClient):
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "sandbox prompt missing action session",
            "graph": _prompt_user_action_graph(),
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    board_id = _board_with_prompt_creature(client, wf_id)
    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]
    creature_id = session_res.json()["envelope"]["sandbox"]["creatures"][0]["id"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    env = tick_res.json()["envelope"]
    assert env.get("last_errors", {}).get(creature_id) is not None
    runs = tick_res.json().get("last_workflow_runs") or {}
    assert runs[creature_id] is None


def _create_force_pause_workflow(client: TestClient) -> str:
    u_id, stop_id = "n_pause", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"force pause {uuid.uuid4().hex[:8]}",
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
    assert workflow_res.status_code == 201, workflow_res.text
    return workflow_res.json()["id"]


def test_region_enter_trigger_force_pause(client: TestClient):
    pause_wf_id = _create_force_pause_workflow(client)
    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Goal board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
                        position=GridCell(x=4, y=4),
                    )
                ],
                items=[
                    SandboxItem(
                        id="goal",
                        type="region",
                        position=GridCell(x=4, y=3),
                        color="#00FF00",
                        label="Goal",
                        trigger=RegionTriggerConfig(
                            enabled=True,
                            mode="enter",
                            workflow_id=pause_wf_id,
                            inputs={},
                        ),
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    board_id = board_res.json()["id"]

    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert session_res.status_code == 200
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    body = tick_res.json()
    assert body.get("simulation_effects", {}).get("force_pause") is True
    env = body["envelope"]
    assert env.get("playback", {}).get("paused") is True
    assert env["sandbox"]["creatures"][0]["position"] == {"x": 4, "y": 3}
    assert env.get("last_region_trigger_errors") == []


def _create_minimal_stop_workflow(client: TestClient, *, name: str) -> str:
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": name,
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
                        "id": "stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "start", "target": "stop", "source_handle": "trigger", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201, workflow_res.text
    return workflow_res.json()["id"]


def _create_use_fixture_brain_workflow(client: TestClient) -> str:
    d_id, stop_id = "n_intent", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"use fixture brain {uuid.uuid4().hex[:8]}",
            "graph": {
                "nodes": [
                    {
                        "id": d_id,
                        "kind": "primitive",
                        "primitive_type": "dictionary",
                        "label": "Intent",
                        "data": {"action": "use_fixture"},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": d_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201, workflow_res.text
    return workflow_res.json()["id"]


def test_fixture_workflow_nested_run_in_tick_response(client: TestClient):
    fixture_wf_id = _create_minimal_stop_workflow(client, name=f"fixture wf {uuid.uuid4().hex[:8]}")
    brain_wf_id = _create_use_fixture_brain_workflow(client)
    fixture_def = client.post(
        "/api/v1/sandbox-definitions/fixtures",
        json={
            "name": f"Door {uuid.uuid4().hex[:8]}",
            "label": "Door",
            "workflow_id": fixture_wf_id,
        },
    )
    assert fixture_def.status_code == 201, fixture_def.text
    fixture_def_id = fixture_def.json()["id"]

    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Fixture board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=brain_wf_id,
                        position=GridCell(x=4, y=4),
                        facing="N",
                    )
                ],
                items=[
                    SandboxItem(
                        id="fx1",
                        type="fixture",
                        definition_kind="fixture",
                        definition_id=fixture_def_id,
                        position=GridCell(x=4, y=3),
                        label="Door",
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    board_id = board_res.json()["id"]

    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert session_res.status_code == 200
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    body = tick_res.json()
    nested = body.get("nested_workflow_runs") or []
    assert len(nested) == 1
    assert nested[0]["meta"]["kind"] == "fixture"
    assert nested[0]["meta"]["creature_id"] == "c1"
    assert nested[0]["meta"]["fixture_id"] == "fx1"
    assert nested[0]["run"]["node_results"]
    env = body["envelope"]
    assert env.get("last_errors", {}).get("c1") in (None, "")
    assert env.get("last_fixture_errors", {}).get("c1") in (None, "")


def _create_fixture_get_position_workflow(client: TestClient) -> str:
    gp_id, stop_id = "n_gp", "n_stop"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"fixture get position {uuid.uuid4().hex[:8]}",
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
                        "id": gp_id,
                        "kind": "utility",
                        "utility_type": "sandbox_get_position",
                        "label": "Get Position",
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
                    {"source": "start", "target": gp_id, "source_handle": "trigger", "target_handle": "trigger"},
                    {"source": gp_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201, workflow_res.text
    return workflow_res.json()["id"]


def test_fixture_workflow_get_position_via_use_fixture(client: TestClient):
    fixture_wf_id = _create_fixture_get_position_workflow(client)
    brain_wf_id = _create_use_fixture_brain_workflow(client)
    fixture_def = client.post(
        "/api/v1/sandbox-definitions/fixtures",
        json={
            "name": f"Position door {uuid.uuid4().hex[:8]}",
            "label": "Position door",
            "workflow_id": fixture_wf_id,
        },
    )
    assert fixture_def.status_code == 201, fixture_def.text
    fixture_def_id = fixture_def.json()["id"]

    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Fixture get position board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=brain_wf_id,
                        position=GridCell(x=4, y=4),
                        facing="N",
                    )
                ],
                items=[
                    SandboxItem(
                        id="fx1",
                        type="fixture",
                        definition_kind="fixture",
                        definition_id=fixture_def_id,
                        position=GridCell(x=4, y=3),
                        label="Position door",
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    board_id = board_res.json()["id"]

    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert session_res.status_code == 200
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    body = tick_res.json()
    nested = body.get("nested_workflow_runs") or []
    assert len(nested) == 1
    gp_res = next(
        r for r in nested[0]["run"]["node_results"] if r.get("node_id") == "n_gp"
    )
    assert gp_res["status"] == "ok"
    assert gp_res["output"]["data"] == {
        "x": 4,
        "y": 3,
        "kind": "fixture",
        "region_label": None,
        "stack_count": 0,
        "items": [],
    }
    env = body["envelope"]
    assert env.get("last_fixture_errors", {}).get("c1") in (None, "")


def _create_fixture_key_swap_workflow(client: TestClient, *, reward_definition_id: str) -> str:
    gci_id, idx_id, dvbk_id, remove_id, spawn_id, stop_id = (
        "n_gci",
        "n_idx",
        "n_dvbk",
        "n_remove",
        "n_spawn",
        "n_stop",
    )
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": f"fixture key swap {uuid.uuid4().hex[:8]}",
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
                        "id": gci_id,
                        "kind": "utility",
                        "utility_type": "sandbox_get_cell_items",
                        "label": "Get Cell Items",
                        "data": {},
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": idx_id,
                        "kind": "utility",
                        "utility_type": "list_item_by_index",
                        "label": "First item",
                        "data": {
                            "required_inputs": [
                                {"key": "index", "type": "int", "value": 0},
                                {"key": "list", "type": "list", "value": None},
                            ],
                        },
                        "position": {"x": 400, "y": 0},
                    },
                    {
                        "id": dvbk_id,
                        "kind": "utility",
                        "utility_type": "dictionary_value_by_key",
                        "label": "Item id",
                        "data": {
                            "output_value_type": "string",
                            "required_inputs": [
                                {"key": "key", "type": "string", "value": "id"},
                                {"key": "dictionary", "type": "dictionary", "value": None},
                                {"key": "fallback", "type": "any", "value": None},
                            ],
                        },
                        "position": {"x": 600, "y": 0},
                    },
                    {
                        "id": remove_id,
                        "kind": "utility",
                        "utility_type": "sandbox_remove_item_at_cell",
                        "label": "Remove Item",
                        "data": {
                            "required_inputs": [
                                {"key": "item_id", "type": "string", "value": None},
                            ],
                        },
                        "position": {"x": 800, "y": 0},
                    },
                    {
                        "id": spawn_id,
                        "kind": "utility",
                        "utility_type": "sandbox_spawn_item_at_cell",
                        "label": "Spawn Item",
                        "data": {
                            "required_inputs": [
                                {"key": "definition_id", "type": "string", "value": reward_definition_id},
                                {"key": "target", "type": "string", "value": "self"},
                            ],
                        },
                        "position": {"x": 1000, "y": 0},
                    },
                    {
                        "id": stop_id,
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                        "position": {"x": 1200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "start", "target": gci_id, "source_handle": "trigger", "target_handle": "trigger"},
                    {"source": gci_id, "target": idx_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": gci_id, "target": idx_id, "source_handle": "output", "target_handle": "list"},
                    {"source": idx_id, "target": dvbk_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": idx_id, "target": dvbk_id, "source_handle": "output", "target_handle": "dictionary"},
                    {"source": dvbk_id, "target": remove_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": dvbk_id, "target": remove_id, "source_handle": "output", "target_handle": "item_id"},
                    {"source": remove_id, "target": spawn_id, "source_handle": "signal_out", "target_handle": "trigger"},
                    {"source": spawn_id, "target": stop_id, "source_handle": "output", "target_handle": "output"},
                ],
            },
        },
    )
    assert workflow_res.status_code == 201, workflow_res.text
    return workflow_res.json()["id"]


def test_fixture_workflow_remove_and_spawn_via_use_fixture(client: TestClient):
    key_def = client.post(
        "/api/v1/sandbox-definitions/items",
        json={
            "name": f"Key {uuid.uuid4().hex[:8]}",
            "label": "Key",
            "pickable": True,
        },
    )
    assert key_def.status_code == 201, key_def.text
    key_def_id = key_def.json()["id"]

    reward_def = client.post(
        "/api/v1/sandbox-definitions/items",
        json={
            "name": f"Reward {uuid.uuid4().hex[:8]}",
            "label": "Reward",
            "pickable": True,
        },
    )
    assert reward_def.status_code == 201, reward_def.text
    reward_def_id = reward_def.json()["id"]

    fixture_wf_id = _create_fixture_key_swap_workflow(client, reward_definition_id=reward_def_id)
    brain_wf_id = _create_use_fixture_brain_workflow(client)
    fixture_def = client.post(
        "/api/v1/sandbox-definitions/fixtures",
        json={
            "name": f"Key door {uuid.uuid4().hex[:8]}",
            "label": "Key door",
            "workflow_id": fixture_wf_id,
        },
    )
    assert fixture_def.status_code == 201, fixture_def.text
    fixture_def_id = fixture_def.json()["id"]

    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Fixture key swap board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=brain_wf_id,
                        position=GridCell(x=4, y=4),
                        facing="N",
                    )
                ],
                items=[
                    SandboxItem(
                        id="fx1",
                        type="fixture",
                        definition_kind="fixture",
                        definition_id=fixture_def_id,
                        position=GridCell(x=4, y=3),
                        label="Key door",
                    ),
                    SandboxItem(
                        id="k1",
                        type="food",
                        definition_id=key_def_id,
                        definition_kind="item",
                        role="pickable",
                        position=GridCell(x=4, y=3),
                        energy=10,
                    ),
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    board_id = board_res.json()["id"]

    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_id})
    assert session_res.status_code == 200
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    body = tick_res.json()
    nested = body.get("nested_workflow_runs") or []
    assert len(nested) == 1
    assert nested[0]["meta"]["kind"] == "fixture"
    remove_res = next(
        r for r in nested[0]["run"]["node_results"] if r.get("node_id") == "n_remove"
    )
    spawn_res = next(
        r for r in nested[0]["run"]["node_results"] if r.get("node_id") == "n_spawn"
    )
    assert remove_res["status"] == "ok"
    assert remove_res["output"]["data"]["removed"] is True
    assert remove_res["output"]["data"]["item_id"] == "k1"
    assert spawn_res["status"] == "ok"
    assert spawn_res["output"]["data"]["position"] == {"x": 4, "y": 3}

    items = body["envelope"]["sandbox"]["world"]["items"]
    pickables_at_fixture = [
        it
        for it in items
        if it.get("position") == {"x": 4, "y": 3}
        and it.get("role") == "pickable"
    ]
    assert len(pickables_at_fixture) == 1
    assert pickables_at_fixture[0]["definition_id"] == reward_def_id
    assert not any(it.get("id") == "k1" for it in items)
    env = body["envelope"]
    assert env.get("last_fixture_errors", {}).get("c1") in (None, "")


def test_fixture_error_does_not_overwrite_brain_error(client: TestClient):
    brain_wf_id = _create_use_fixture_brain_workflow(client)
    fixture_wf_id = _create_minimal_stop_workflow(client, name=f"fixture wf {uuid.uuid4().hex[:8]}")
    fixture_def = client.post(
        "/api/v1/sandbox-definitions/fixtures",
        json={
            "name": f"Broken {uuid.uuid4().hex[:8]}",
            "label": "Broken",
            "workflow_id": fixture_wf_id,
        },
    )
    assert fixture_def.status_code == 201, fixture_def.text
    fixture_def_id = fixture_def.json()["id"]
    deleted = client.delete(f"/api/v1/workflow-definitions/{fixture_wf_id}")
    assert deleted.status_code in (200, 204), deleted.text

    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Broken fixture board",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=brain_wf_id,
                        position=GridCell(x=4, y=4),
                        facing="N",
                    )
                ],
                items=[
                    SandboxItem(
                        id="fx1",
                        type="fixture",
                        definition_kind="fixture",
                        definition_id=fixture_def_id,
                        position=GridCell(x=4, y=3),
                        label="Broken",
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_res.json()["id"]})
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    env = tick_res.json()["envelope"]
    assert env.get("last_errors", {}).get("c1") in (None, "")
    assert env.get("last_fixture_errors", {}).get("c1")
    assert "workflow not found" in env["last_fixture_errors"]["c1"]


def test_region_enter_trigger_nested_run_in_tick_response(client: TestClient):
    pause_wf_id = _create_force_pause_workflow(client)
    board_res = client.post(
        "/api/v1/sandbox/boards",
        json={
            "name": "Goal board nested",
            "definition": BoardDefinition(
                grid=WorldGrid(width=8, height=8),
                creatures=[
                    BoardCreaturePlacement(
                        id="c1",
                        workflow_id=str(STARTER_SANDBOX_WORKFLOW_ID),
                        position=GridCell(x=4, y=4),
                    )
                ],
                items=[
                    SandboxItem(
                        id="goal",
                        type="region",
                        position=GridCell(x=4, y=3),
                        color="#00FF00",
                        label="Goal",
                        trigger=RegionTriggerConfig(
                            enabled=True,
                            mode="enter",
                            workflow_id=pause_wf_id,
                            inputs={},
                        ),
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    assert board_res.status_code == 200, board_res.text
    session_res = client.post("/api/v1/sandbox/sessions", json={"board_id": board_res.json()["id"]})
    doc_id = session_res.json()["document_id"]
    v0 = session_res.json()["envelope"]["state_version"]

    tick_res = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert tick_res.status_code == 200, tick_res.text
    nested = tick_res.json().get("nested_workflow_runs") or []
    assert len(nested) == 1
    assert nested[0]["meta"]["kind"] == "region_trigger"
    assert nested[0]["meta"]["creature_id"] == "c1"
    assert nested[0]["meta"]["trigger_mode"] == "enter"
    assert nested[0]["run"]["node_results"]

