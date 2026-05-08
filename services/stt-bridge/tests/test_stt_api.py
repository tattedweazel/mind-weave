"""API tests (mock; no real model)."""

import importlib
import os

import pytest


@pytest.fixture
def client_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STT_BRIDGE_MOCK", "1")
    monkeypatch.setenv("STT_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("STT_BRIDGE_TOKEN", raising=False)
    import stt_bridge.config as cfg
    import stt_bridge.main as main

    importlib.reload(cfg)
    importlib.reload(main)
    return tmp_path


def test_transcribe_mock(client_env):
    import stt_bridge.main as main
    from starlette.testclient import TestClient

    with TestClient(main.app) as c:
        r = c.post(
            "/v1/transcribe",
            files={"file": ("clip.webm", b"fake-bytes", "audio/webm")},
            data={"task": "transcribe"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["text"] == "mock transcript"
        assert body["language"] == "en"


def test_transcribe_requires_token_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("STT_BRIDGE_MOCK", "1")
    monkeypatch.setenv("STT_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("STT_BRIDGE_TOKEN", "secret")
    import stt_bridge.config as cfg
    import stt_bridge.main as main

    importlib.reload(cfg)
    importlib.reload(main)
    from starlette.testclient import TestClient

    with TestClient(main.app) as c:
        r = c.post(
            "/v1/transcribe",
            files={"file": ("c.webm", b"x", "audio/webm")},
        )
        assert r.status_code == 401

        r2 = c.post(
            "/v1/transcribe",
            files={"file": ("c.webm", b"x", "audio/webm")},
            headers={"X-STT-Bridge-Token": "secret"},
        )
        assert r2.status_code == 200
