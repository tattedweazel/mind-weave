"""Smoke tests: Persona and Structure REST CRUD (get/put/delete)."""

import uuid

from fastapi.testclient import TestClient


def test_persona_crud_smoke(client: TestClient):
    name = f"p_smoke_{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/api/v1/personas/",
        json={
            "name": name,
            "type": "custom",
            "description": "d",
            "system_prompt": "You are helpful.",
        },
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    got = client.get(f"/api/v1/personas/{pid}")
    assert got.status_code == 200
    assert got.json()["name"] == name

    updated = client.put(
        f"/api/v1/personas/{pid}",
        json={"description": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated"

    deleted = client.delete(f"/api/v1/personas/{pid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/personas/{pid}").status_code == 404


def test_document_crud_smoke(client: TestClient):
    name = f"doc_smoke_{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/api/v1/documents/",
        json={"name": name, "description": "d", "body": "# Hello"},
    )
    assert create.status_code == 201
    did = create.json()["id"]

    got = client.get(f"/api/v1/documents/{did}")
    assert got.status_code == 200
    assert got.json()["name"] == name
    assert got.json()["body"] == "# Hello"

    updated = client.put(
        f"/api/v1/documents/{did}",
        json={"description": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated"

    deleted = client.delete(f"/api/v1/documents/{did}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{did}").status_code == 404


def test_structure_crud_smoke(client: TestClient):
    schema = '{"type":"object","properties":{"x":{"type":"string"}}}'
    create = client.post(
        "/api/v1/structures/",
        json={"name": "SmokeStruct", "description": "d", "json_schema": schema},
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    got = client.get(f"/api/v1/structures/{sid}")
    assert got.status_code == 200
    assert got.json()["name"] == "SmokeStruct"

    updated = client.put(
        f"/api/v1/structures/{sid}",
        json={"description": "new desc"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "new desc"

    deleted = client.delete(f"/api/v1/structures/{sid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/structures/{sid}").status_code == 404
