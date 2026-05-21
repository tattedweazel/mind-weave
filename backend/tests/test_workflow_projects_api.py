"""Workflow project folder API (Shared seed, CRUD, workflow project_id)."""

import time

from fastapi.testclient import TestClient

_MINIMAL_GRAPH = {
    "nodes": [
        {
            "id": "n_str",
            "kind": "primitive",
            "primitive_type": "string",
            "label": "S",
            "data": {"text": "x"},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n_stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
            "position": {"x": 100, "y": 0},
        },
    ],
    "edges": [{"source": "n_str", "target": "n_stop"}],
}


def test_workflow_projects_list_includes_shared(client: TestClient):
    r = client.get("/api/v1/workflow-projects/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = {p["name"] for p in body}
    assert "Shared" in names
    shared = next(p for p in body if p["name"] == "Shared")
    assert "workflow_count" in shared


def test_workflow_projects_create_rejects_shared_name(client: TestClient):
    r = client.post("/api/v1/workflow-projects/", json={"name": "shared"})
    assert r.status_code == 400


def test_workflow_projects_crud_and_delete_empty(client: TestClient):
    create = client.post(
        "/api/v1/workflow-projects/",
        json={"name": "Alpha Project"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    dup = client.post("/api/v1/workflow-projects/", json={"name": "Alpha Project"})
    assert dup.status_code == 400

    deleted = client.delete(f"/api/v1/workflow-projects/{pid}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/workflow-projects/")
    assert listed.status_code == 200
    assert not any(p["id"] == pid for p in listed.json())


def test_workflow_projects_delete_nonempty_requires_cascade(client: TestClient):
    create = client.post(
        "/api/v1/workflow-projects/",
        json={"name": "Beta Project"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "In Beta", "graph": _MINIMAL_GRAPH, "project_id": pid},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]

    blocked = client.delete(f"/api/v1/workflow-projects/{pid}")
    assert blocked.status_code == 409

    still_there = client.get("/api/v1/workflow-definitions/")
    assert still_there.status_code == 200
    assert any(w["id"] == wf_id for w in still_there.json())

    deleted = client.delete(f"/api/v1/workflow-projects/{pid}?delete_workflows=true")
    assert deleted.status_code == 204

    wfs = client.get("/api/v1/workflow-definitions/")
    assert wfs.status_code == 200
    assert not any(w["id"] == wf_id for w in wfs.json())

    projects = client.get("/api/v1/workflow-projects/")
    assert not any(p["id"] == pid for p in projects.json())


def test_workflow_projects_cascade_delete_includes_custom_skills(client: TestClient):
    create = client.post(
        "/api/v1/workflow-projects/",
        json={"name": "Gamma Project"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Custom In Gamma",
            "graph": _MINIMAL_GRAPH,
            "project_id": pid,
            "expose_as_custom_skill": True,
        },
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]

    deleted = client.delete(f"/api/v1/workflow-projects/{pid}?delete_workflows=true")
    assert deleted.status_code == 204

    wfs = client.get("/api/v1/workflow-definitions/")
    assert not any(w["id"] == wf_id for w in wfs.json())


def test_workflow_definitions_list_ordered_by_updated_at_desc(client: TestClient):
    a = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Older", "graph": _MINIMAL_GRAPH},
    )
    assert a.status_code == 201
    time.sleep(0.01)
    b = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Newer", "graph": _MINIMAL_GRAPH},
    )
    assert b.status_code == 201
    listed = client.get("/api/v1/workflow-definitions/")
    assert listed.status_code == 200
    rows = listed.json()
    names = [w["name"] for w in rows if w["name"] in ("Older", "Newer")]
    # Newer should appear before Older (updated_at desc)
    assert names.index("Newer") < names.index("Older")
    for w in rows:
        assert "created_at" in w
        assert "updated_at" in w


def test_workflow_definition_update_project_id(client: TestClient):
    proj = client.post("/api/v1/workflow-projects/", json={"name": "Beta"})
    assert proj.status_code == 201
    pid = proj.json()["id"]
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Movable", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    put = client.put(
        f"/api/v1/workflow-definitions/{wf_id}",
        json={"project_id": pid},
    )
    assert put.status_code == 200
    assert put.json()["project_id"] == pid


def test_cannot_delete_shared_project(client: TestClient):
    shared = next(p for p in client.get("/api/v1/workflow-projects/").json() if p["name"] == "Shared")
    r = client.delete(f"/api/v1/workflow-projects/{shared['id']}")
    assert r.status_code == 400
