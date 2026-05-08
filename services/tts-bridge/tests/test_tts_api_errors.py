"""HTTP status mapping for /v1/tts: PyTorch meta-tensor NIE is 500, engine stubs are 501."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tts_bridge.main import app, _is_pytorch_meta_device_notimplemented


class _EngStubMlx:
    def synthesize(self, model_local_key: str, text: str, options: dict) -> bytes:  # noqa: ARG002
        raise NotImplementedError(
            "qwen_mlx engine is not implemented yet. Use qwen_torch or set TTS_BRIDGE_MOCK=1 for tests."
        )


class _EngStubMeta:
    def synthesize(self, model_local_key: str, text: str, options: dict) -> bytes:  # noqa: ARG002
        raise NotImplementedError("Cannot copy out of meta tensor; no data! Please use to_empty()...")


def test_is_pytorch_meta_notimplemented():
    assert _is_pytorch_meta_device_notimplemented(NotImplementedError("Cannot copy out of meta tensor; no data!"))
    assert _is_pytorch_meta_device_notimplemented(NotImplementedError("Please use torch.nn.Module.to_empty()"))
    assert not _is_pytorch_meta_device_notimplemented(NotImplementedError("qwen_mlx not implemented"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_tts_501_unimplemented_engine_stub(client: TestClient):
    with patch("tts_bridge.main.get_engine", return_value=_EngStubMlx()):
        r = client.post(
            "/v1/tts",
            json={"engine": "qwen_mlx", "model_local_key": "k", "text": "hi", "options": {}},
        )
    assert r.status_code == 501
    assert "qwen_mlx" in (r.json().get("detail") or "")


def test_tts_500_pytorch_meta_tensor_notimplemented(client: TestClient):
    with patch("tts_bridge.main.get_engine", return_value=_EngStubMeta()):
        r = client.post(
            "/v1/tts",
            json={"engine": "qwen_torch", "model_local_key": "k", "text": "hi", "options": {}},
        )
    assert r.status_code == 500
    assert "meta tensor" in (r.json().get("detail") or "")


def test_health_includes_qwen_cache_revision(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("qwen_torch_cache_revision")
    assert isinstance(j["qwen_torch_cache_revision"], str)
    # Bump when qwen load logic changes; helps confirm which code the running bridge uses.
    assert "st_mat" in j["qwen_torch_cache_revision"] or "v4" in j["qwen_torch_cache_revision"]
