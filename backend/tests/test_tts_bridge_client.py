"""Unit tests for ``app.providers.tts_bridge`` — httpx fully mocked (no real bridge)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings as app_settings
from app.providers.tts_bridge import TtsBridgeError, pull_model, synthesize_wav


def _mock_async_client(post_return: MagicMock) -> MagicMock:
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.post = AsyncMock(return_value=post_return)
    return instance


@pytest.mark.asyncio
async def test_pull_model_includes_x_tts_bridge_token(monkeypatch):
    monkeypatch.setattr(app_settings, "TTS_BRIDGE_TOKEN", "  bridge-secret  ")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"local_key": "k"}
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        await pull_model("qwen_torch", "a", {"kind": "huggingface_repo", "repo_id": "x/y"})
    headers = instance.post.await_args.kwargs["headers"]
    assert headers["X-TTS-Bridge-Token"] == "bridge-secret"


@pytest.mark.asyncio
async def test_pull_model_success():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"local_key": "qwen_torch/artifact-1"}
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        key = await pull_model("qwen_torch", "artifact-1", {"kind": "huggingface_repo", "repo_id": "x/y"})
    assert key == "qwen_torch/artifact-1"
    instance.post.assert_awaited_once()
    call_kw = instance.post.await_args.kwargs
    assert call_kw["json"]["engine"] == "qwen_torch"
    assert call_kw["json"]["artifact_id"] == "artifact-1"


@pytest.mark.asyncio
async def test_pull_model_request_error():
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.post = AsyncMock(side_effect=httpx.ConnectError("refused", request=MagicMock()))
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="unreachable"):
            await pull_model("qwen_torch", "a", {"kind": "huggingface_repo", "repo_id": "x/y"})


@pytest.mark.asyncio
async def test_pull_model_http_error_non_json_body():
    resp = MagicMock()
    resp.status_code = 503
    resp.reason_phrase = "Service Unavailable"
    resp.json.side_effect = ValueError("not json")
    resp.text = "plain error"
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="503.*plain error"):
            await pull_model("qwen_torch", "a", {"kind": "huggingface_repo", "repo_id": "x/y"})


@pytest.mark.asyncio
async def test_pull_model_http_error_detail_json():
    resp = MagicMock()
    resp.status_code = 502
    resp.reason_phrase = "Bad Gateway"
    resp.json.return_value = {"detail": "upstream failed"}
    resp.text = ""
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="502.*upstream failed"):
            await pull_model("qwen_torch", "a", {"kind": "huggingface_repo", "repo_id": "x/y"})


@pytest.mark.asyncio
async def test_pull_model_missing_local_key():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {}
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="no local_key"):
            await pull_model("qwen_torch", "a", {"kind": "huggingface_repo", "repo_id": "x/y"})


@pytest.mark.asyncio
async def test_synthesize_wav_request_error():
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.post = AsyncMock(side_effect=httpx.TimeoutException("timeout", request=MagicMock()))
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="unreachable"):
            await synthesize_wav("qwen_torch", "k", "hi")


@pytest.mark.asyncio
async def test_synthesize_wav_http_error_json_detail():
    resp = MagicMock()
    resp.status_code = 422
    resp.reason_phrase = "Unprocessable"
    resp.json.return_value = {"detail": "invalid payload"}
    resp.text = ""
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="422.*invalid payload"):
            await synthesize_wav("qwen_torch", "k", "hi")


@pytest.mark.asyncio
async def test_synthesize_wav_success():
    wav = b"RIFF....WAVE"
    resp = MagicMock()
    resp.status_code = 200
    resp.content = wav
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        out = await synthesize_wav("qwen_torch", "qwen_torch/x", "hello", {"language": "English"})
    assert out == wav
    call_kw = instance.post.await_args.kwargs
    assert call_kw["json"]["model_local_key"] == "qwen_torch/x"
    assert call_kw["json"]["text"] == "hello"
    assert call_kw["json"]["options"] == {"language": "English"}


@pytest.mark.asyncio
async def test_synthesize_wav_too_large():
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"x" * 60_000_000
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="exceeds configured cap"):
            await synthesize_wav("qwen_torch", "k", "hi")


@pytest.mark.asyncio
async def test_synthesize_wav_http_error_non_json_body():
    resp = MagicMock()
    resp.status_code = 500
    resp.reason_phrase = "Error"
    resp.json.side_effect = ValueError("not json")
    resp.text = "boom"
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="500.*boom"):
            await synthesize_wav("qwen_torch", "k", "hi")


@pytest.mark.asyncio
async def test_synthesize_wav_http_error_plain_text():
    resp = MagicMock()
    resp.status_code = 400
    resp.reason_phrase = "Bad Request"
    resp.json.side_effect = ValueError("not json")
    resp.text = "bad request body"
    instance = _mock_async_client(resp)
    with patch("app.providers.tts_bridge.httpx.AsyncClient", return_value=instance):
        with pytest.raises(TtsBridgeError, match="400.*bad request body"):
            await synthesize_wav("qwen_torch", "k", "hi")
