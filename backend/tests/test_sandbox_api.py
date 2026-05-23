"""Sandbox HTTP API tests."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID, STARTER_SANDBOX_WORKFLOW_ID
from app.domain.schemas.sandbox import BoardCreaturePlacement, BoardDefinition, GridCell, WorldGrid
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
