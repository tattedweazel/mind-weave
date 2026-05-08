"""Sandbox HTTP API tests."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.starter_workflow_seed import STARTER_SANDBOX_WORKFLOW_GRAPH
from app.persistence.tables import User, WorkflowDefinition
from tests.conftest import engine


def test_sandbox_session_create_and_tick(client: TestClient):
    """Create session, run tick, state_version advances."""
    r = client.post("/api/v1/sandbox/sessions", json={})
    assert r.status_code == 200
    data = r.json()
    doc_id = data["document_id"]
    v0 = data["envelope"]["state_version"]

    t = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0},
    )
    assert t.status_code == 200
    body = t.json()
    env = body["envelope"]
    assert env["state_version"] == v0 + 1
    assert env["sandbox"]["tick"] >= 1
    assert body.get("last_workflow_run") is not None
    assert len(body["last_workflow_run"]["node_results"]) >= 1


def test_starter_workflow_id_endpoint(client: TestClient):
    r = client.get("/api/v1/sandbox/starter-workflow-id")
    assert r.status_code == 200
    assert r.json()["workflow_id"] == str(STARTER_SANDBOX_WORKFLOW_ID)


def test_sandbox_tick_persists_workflow_id_override(client: TestClient):
    """workflow_id on tick body is written to the stored envelope."""
    alt_id = uuid.uuid4()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        assert user is not None
        session.add(
            WorkflowDefinition(
                id=alt_id,
                user_id=user.id,
                name="Alt sandbox brain",
                graph=dict(STARTER_SANDBOX_WORKFLOW_GRAPH),
            )
        )
        session.commit()

    r = client.post("/api/v1/sandbox/sessions", json={})
    assert r.status_code == 200
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]
    assert r.json()["envelope"]["workflow_id"] == str(STARTER_SANDBOX_WORKFLOW_ID)

    t = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/tick",
        json={"interactions": [], "state_version": v0, "workflow_id": str(alt_id)},
    )
    assert t.status_code == 200
    assert t.json()["envelope"]["workflow_id"] == str(alt_id)

    g = client.get(f"/api/v1/sandbox/sessions/{doc_id}")
    assert g.status_code == 200
    assert g.json()["envelope"]["workflow_id"] == str(alt_id)


def test_sandbox_resize_grid_paused_only_and_version(client: TestClient):
    r = client.post("/api/v1/sandbox/sessions", json={})
    assert r.status_code == 200
    doc_id = r.json()["document_id"]
    v0 = r.json()["envelope"]["state_version"]
    assert r.json()["envelope"]["playback"].get("paused", True) is True

    bad = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 12, "height": 10, "state_version": v0 + 9},
    )
    assert bad.status_code == 409

    small = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 4, "height": 10, "state_version": v0},
    )
    assert small.status_code == 422

    ok = client.post(
        f"/api/v1/sandbox/sessions/{doc_id}/grid",
        json={"width": 12, "height": 10, "state_version": v0},
    )
    assert ok.status_code == 200
    env = ok.json()["envelope"]
    assert env["state_version"] == v0 + 1
    assert env["sandbox"]["world"]["grid"]["width"] == 12
    assert env["sandbox"]["world"]["grid"]["height"] == 10


def test_sandbox_resize_grid_rejects_when_not_paused(client: TestClient, db_session):
    """Playback must be paused; mutate persisted envelope via same DB session as API."""
    import json
    import uuid

    from app.domain.document_json import deterministic_json_dumps
    from app.persistence.tables import Document

    r = client.post("/api/v1/sandbox/sessions", json={})
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
    assert "paused" in (r2.json().get("detail") or "").lower()


def test_sandbox_create_session_applies_sandbox_defaults_from_workflow_graph(client: TestClient):
    """Optional top-level sandbox_defaults on the workflow graph sizes the initial grid."""
    wf_id = uuid.uuid4()
    graph = dict(STARTER_SANDBOX_WORKFLOW_GRAPH)
    graph["sandbox_defaults"] = {"grid_width": 12, "grid_height": 10}
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "testuser")).first()
        assert user is not None
        session.add(
            WorkflowDefinition(
                id=wf_id,
                user_id=user.id,
                name="With sandbox defaults",
                graph=graph,
            )
        )
        session.commit()

    r = client.post("/api/v1/sandbox/sessions", json={"workflow_id": str(wf_id)})
    assert r.status_code == 200
    env = r.json()["envelope"]
    assert env["sandbox"]["world"]["grid"]["width"] == 12
    assert env["sandbox"]["world"]["grid"]["height"] == 10
