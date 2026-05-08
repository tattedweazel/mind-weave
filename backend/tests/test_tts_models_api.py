"""TTS model registry API (admin vs authenticated)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import User
from tests.conftest import engine


def _promote_testuser_admin() -> None:
    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == "testuser")).first()
        assert u is not None
        u.is_admin = True
        session.add(u)
        session.commit()


def test_tts_models_ready_empty(client: TestClient):
    r = client.get("/api/v1/tts-models")
    assert r.status_code == 200
    assert r.json() == []


def test_tts_registry_forbidden_for_non_admin(client: TestClient):
    r = client.get("/api/v1/tts-models/registry")
    assert r.status_code == 403


def test_tts_create_and_list_ready_admin_mocked_pull(client: TestClient):
    _promote_testuser_admin()
    with patch("app.api.v1.tts_models.pull_model", new_callable=AsyncMock) as m_pull:
        m_pull.return_value = "qwen_torch/abc/weights"
        r = client.post(
            "/api/v1/tts-models",
            json={
                "display_name": "Test Voice",
                "engine": "qwen_torch",
                "source": {"kind": "huggingface_repo", "repo_id": "dummy/repo", "revision": None},
            },
        )
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "ready"
    assert row["local_key"] == "qwen_torch/abc/weights"
    assert row["engine"] == "qwen_torch"

    listed = client.get("/api/v1/tts-models").json()
    assert len(listed) == 1
    assert listed[0]["id"] == row["id"]


def test_tts_create_non_admin_forbidden(client: TestClient):
    r = client.post(
        "/api/v1/tts-models",
        json={
            "display_name": "X",
            "engine": "qwen_torch",
            "source": {"kind": "huggingface_repo", "repo_id": "a/b", "revision": None},
        },
    )
    assert r.status_code == 403
