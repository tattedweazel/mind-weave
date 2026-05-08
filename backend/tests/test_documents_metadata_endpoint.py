"""Integration tests for ``GET /api/v1/documents/{id}/metadata``."""

import uuid

from fastapi.testclient import TestClient


def _create_doc(client: TestClient, name: str, body: str) -> str:
    res = client.post(
        "/api/v1/documents/",
        json={"name": name, "description": "", "body": body},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_metadata_endpoint_happy_path(client: TestClient):
    doc_id = _create_doc(client, f"meta_{uuid.uuid4().hex[:8]}", "alpha beta gamma")

    res = client.get(f"/api/v1/documents/{doc_id}/metadata")
    assert res.status_code == 200
    payload = res.json()

    assert payload["id"] == doc_id
    assert payload["tokenizer"] == "o200k_base"
    assert payload["character_count"] == len("alpha beta gamma")
    assert payload["word_count"] == 3
    assert payload["line_count"] == 1
    assert payload["token_count"] > 0
    assert "created_at" in payload
    assert "updated_at" in payload
    assert "name" in payload


def test_metadata_endpoint_empty_body(client: TestClient):
    doc_id = _create_doc(client, f"empty_{uuid.uuid4().hex[:8]}", "")

    res = client.get(f"/api/v1/documents/{doc_id}/metadata")
    assert res.status_code == 200
    payload = res.json()

    assert payload["token_count"] == 0
    assert payload["character_count"] == 0
    assert payload["word_count"] == 0
    assert payload["line_count"] == 0


def test_metadata_endpoint_returns_404_when_missing(client: TestClient):
    fake_id = uuid.uuid4()
    res = client.get(f"/api/v1/documents/{fake_id}/metadata")
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found."


def test_metadata_endpoint_reflects_body_after_update(client: TestClient):
    doc_id = _create_doc(client, f"reflect_{uuid.uuid4().hex[:8]}", "one")

    initial = client.get(f"/api/v1/documents/{doc_id}/metadata").json()

    upd = client.put(f"/api/v1/documents/{doc_id}", json={"body": "one\ntwo\nthree"})
    assert upd.status_code == 200

    after = client.get(f"/api/v1/documents/{doc_id}/metadata").json()
    assert after["line_count"] == 3
    assert after["character_count"] == len("one\ntwo\nthree")
    assert after["word_count"] == 3
    assert after["token_count"] >= initial["token_count"]
