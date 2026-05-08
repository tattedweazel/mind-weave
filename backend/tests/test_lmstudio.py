"""Tests for LMStudioProvider — JSON extraction, multi-block handling, and HTTP mocks."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers.base import ProviderResponse
from app.providers.lmstudio import (
    LMStudioModelNotMultimodalError,
    LMStudioProvider,
    _extract_clean_content,
    _extract_last_json_block,
    _find_json_blocks,
    _is_warmup_400,
    _lmstudio_body_suggests_model_not_multimodal,
    _native_list_shows_model_loaded,
    _payload_has_multimodal_image_parts,
    _read_lm_error_body,
    _strip_protocol_tokens,
)
from app.providers.openai_usage import normalize_openai_usage_for_provider


class TestFindJsonBlocks:
    def test_single_object(self):
        text = '{"a": 1}'
        blocks = _find_json_blocks(text)
        assert len(blocks) == 1
        assert text[blocks[0][0] : blocks[0][1]] == '{"a": 1}'

    def test_single_array(self):
        text = "[1, 2, 3]"
        assert _find_json_blocks(text) == [(0, 9)]

    def test_object_then_array(self):
        text = '{"persona": {"name": "Hana"}}\n[{"persona": {"name": "Hana"}}, {"persona": {"name": "Haruka"}}]'
        blocks = _find_json_blocks(text)
        assert len(blocks) == 2
        assert text[blocks[0][0] : blocks[0][1]] == '{"persona": {"name": "Hana"}}'
        assert text[blocks[1][0] : blocks[1][1]].startswith("[{")

    def test_nested_object(self):
        text = '{"outer": {"inner": 1}}'
        blocks = _find_json_blocks(text)
        assert len(blocks) == 1
        assert text[blocks[0][0] : blocks[0][1]] == text

    def test_string_with_braces(self):
        text = '{"key": "value with } inside"}'
        blocks = _find_json_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == (0, len(text))


class TestExtractLastJsonBlock:
    def test_single_block_returns_none(self):
        assert _extract_last_json_block('{"a": 1}') is None
        assert _extract_last_json_block("[1, 2]") is None

    def test_multiple_blocks_returns_last(self):
        text = '{"persona": {"name": "Hana"}}\n[{"persona": {"name": "Hana"}}, {"persona": {"name": "Haruka"}}]'
        result = _extract_last_json_block(text)
        assert result is not None
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["persona"]["name"] == "Hana"
        assert parsed[1]["persona"]["name"] == "Haruka"


class TestExtractCleanContent:
    def test_extracts_first_block_for_structured(self):
        raw = '{"reasoning": "..."}'
        result = _extract_clean_content(raw)
        parsed = json.loads(result)
        assert "reasoning" in parsed
        assert parsed["reasoning"] == "..."


class TestStripProtocolTokens:
    def test_strips_protocol_tokens(self):
        text = "<|channel|>hello<|constrain|>"
        assert _strip_protocol_tokens(text) == "hello"


def test_native_list_shows_model_loaded():
    assert _native_list_shows_model_loaded(
        {"models": [{"key": "my-model", "loaded_instances": [{"id": "1"}]}]},
        "my-model",
    )
    assert not _native_list_shows_model_loaded(
        {"models": [{"key": "my-model", "loaded_instances": []}]},
        "my-model",
    )
    assert not _native_list_shows_model_loaded({"models": []}, "my-model")


def _mock_http_clients(
    openai_models_json: dict,
    native_models_json: dict,
    chat_json: dict,
):
    """Chat resolves model via OpenAI ``GET …/v1/models`` then may hit native ``GET …/api/v1/models``."""

    mock_chat = MagicMock()
    mock_chat.raise_for_status = lambda: None
    mock_chat.json.return_value = chat_json

    async def get_side_effect(url: str, **kwargs: object):
        r = MagicMock()
        r.status_code = 200
        if "/api/v1/models" in str(url):
            r.json.return_value = native_models_json
        else:
            r.json.return_value = openai_models_json
        return r

    instance = MagicMock()
    instance.get = AsyncMock(side_effect=get_side_effect)
    instance.post = AsyncMock(return_value=mock_chat)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    return instance


@pytest.mark.asyncio
async def test_chat_extracts_last_block_when_multiple_freeform():
    """When free-form response contains object then array, provider returns only the array."""
    multi_block_response = {
        "choices": [
            {
                "message": {
                    "content": '{"persona": {"name": "Hana"}}\n[{"persona": {"name": "Hana"}}, {"persona": {"name": "Haruka"}}]'
                }
            }
        ],
        "usage": None,
    }
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    instance = _mock_http_clients(openai_list, native_list, multi_block_response)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        response = await provider.chat(
            [{"role": "user", "content": "Generate personas"}],
            options={},
        )

    parsed = json.loads(response.raw_text)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["persona"]["name"] == "Hana"
    assert parsed[1]["persona"]["name"] == "Haruka"
    assert response.parsed is None


@pytest.mark.asyncio
async def test_chat_uses_reasoning_content_when_content_empty():
    """When content is empty, fall back to reasoning_content (reasoning models)."""
    reasoning_response = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": "Hello from reasoning",
                }
            }
        ],
        "usage": None,
    }
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    instance = _mock_http_clients(openai_list, native_list, reasoning_response)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        response = await provider.chat(
            [{"role": "user", "content": "Say hello"}],
            options={},
        )

    assert response.raw_text == "Hello from reasoning"


@pytest.mark.asyncio
async def test_chat_prefers_content_over_reasoning_content():
    """When both content and reasoning_content exist, prefer content."""
    both_response = {
        "choices": [
            {
                "message": {
                    "content": "Final answer",
                    "reasoning_content": "Internal reasoning here",
                }
            }
        ],
        "usage": None,
    }
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    instance = _mock_http_clients(openai_list, native_list, both_response)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        response = await provider.chat(
            [{"role": "user", "content": "Answer"}],
            options={},
        )

    assert response.raw_text == "Final answer"


@pytest.mark.asyncio
async def test_chat_payload_includes_reasoning_effort_when_passed_in_options():
    """OpenAI-compatible body merges options; LM Studio uses reasoning_effort (0.4.8+)."""
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    chat_json = {"choices": [{"message": {"content": "{}"}}], "usage": None}
    instance = _mock_http_clients(openai_list, native_list, chat_json)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        await provider.chat(
            [{"role": "user", "content": "x"}],
            options={"reasoning_effort": "none"},
        )

    chat_body = None
    for call in instance.post.call_args_list:
        payload = call.kwargs.get("json")
        if isinstance(payload, dict) and "messages" in payload:
            chat_body = payload
            break
    assert chat_body is not None
    assert chat_body.get("reasoning_effort") == "none"


@pytest.mark.asyncio
async def test_chat_sends_authorization_header():
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    chat_json = {"choices": [{"message": {"content": "{}"}}], "usage": None}
    instance = _mock_http_clients(openai_list, native_list, chat_json)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="secret-bearer")
        await provider.chat([{"role": "user", "content": "x"}], options={})

    assert instance.get.await_count == 2  # OpenAI /v1/models + native /api/v1/models
    assert instance.post.await_count == 1
    call_kw = instance.post.call_args
    assert call_kw[1]["headers"].get("Authorization") == "Bearer secret-bearer"


@pytest.mark.asyncio
async def test_chat_retries_on_500_then_succeeds():
    """POST /v1/chat/completions may return 500 while the model is still initializing; we retry."""
    resp500 = MagicMock()
    resp500.status_code = 500
    req = MagicMock()
    resp500.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=req, response=resp500
    )
    resp200 = MagicMock()
    resp200.status_code = 200
    resp200.raise_for_status = lambda: None
    resp200.json.return_value = {
        "choices": [{"message": {"content": "recovered"}}],
        "usage": None,
    }
    mock_models = MagicMock()
    mock_models.status_code = 200
    mock_models.json.return_value = {"data": [{"id": "retry-m"}]}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_models)
    instance.post = AsyncMock(side_effect=[resp500, resp200])
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.providers.lmstudio._ensure_model_loaded", AsyncMock()),
        patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance),
    ):
        provider = LMStudioProvider(api_key="test-token")
        out = await provider.chat([{"role": "user", "content": "x"}], options={})

    assert instance.get.await_count == 1
    assert instance.post.await_count == 2
    assert out.raw_text == "recovered"


def _mock_status_response(status_code: int, body_text: str, reason: str = "") -> MagicMock:
    """Build a mock ``httpx.Response`` that raises ``HTTPStatusError`` on ``raise_for_status``."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body_text
    resp.reason_phrase = reason
    req = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"{status_code} error", request=req, response=resp
    )
    return resp


class TestReadLmErrorBody:
    def test_empty(self):
        resp = MagicMock()
        resp.text = ""
        assert _read_lm_error_body(resp) == ""

    def test_raw_non_json(self):
        resp = MagicMock()
        resp.text = "  plain text failure  "
        assert _read_lm_error_body(resp) == "plain text failure"

    def test_openai_style_error_dict(self):
        resp = MagicMock()
        resp.text = json.dumps({"error": {"message": "Model warming up"}})
        assert _read_lm_error_body(resp) == "Model warming up"

    def test_flat_error_string(self):
        resp = MagicMock()
        resp.text = json.dumps({"error": "Model not loaded"})
        assert _read_lm_error_body(resp) == "Model not loaded"

    def test_message_field_fallback(self):
        resp = MagicMock()
        resp.text = json.dumps({"message": "Bad schema"})
        assert _read_lm_error_body(resp) == "Bad schema"

    def test_json_dict_without_known_keys_returns_raw(self):
        """Dict body without error/error.message/message falls back to raw snippet."""
        resp = MagicMock()
        body = json.dumps({"other": "noise"})
        resp.text = body
        assert _read_lm_error_body(resp) == body

    def test_error_dict_without_message_key_returns_raw(self):
        """{"error": {"code": 1}} has no usable ``message`` field; fall back to raw snippet."""
        resp = MagicMock()
        body = json.dumps({"error": {"code": 1}})
        resp.text = body
        assert _read_lm_error_body(resp) == body

    def test_caps_at_read_cap(self):
        """Raw fallback body is capped at ``_LM_ERROR_BODY_READ_CAP`` chars."""
        from app.providers.lmstudio import _LM_ERROR_BODY_READ_CAP

        resp = MagicMock()
        resp.text = "x" * (_LM_ERROR_BODY_READ_CAP + 500)
        assert len(_read_lm_error_body(resp)) == _LM_ERROR_BODY_READ_CAP

    def test_non_400_non_warmup_body_ignored(self):
        """_is_warmup_400 ignores warmup markers when status != 400 (e.g. 503 with similar body)."""
        resp = _mock_status_response(503, '{"error": "Model not loaded"}')
        assert _is_warmup_400(resp) is False

    def test_read_exception_returns_empty(self):
        resp = MagicMock()
        type(resp).text = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        assert _read_lm_error_body(resp) == ""


class TestIsWarmup400:
    @pytest.mark.parametrize(
        "body",
        [
            '{"error": "Model not loaded"}',
            '{"error": "MODEL IS NOT LOADED"}',
            '{"error": {"message": "No runtime is currently loaded"}}',
            '{"error": "Model is loading weights"}',
            '{"error": "Model is warming up, please retry"}',
            '{"error": "Server is still loading the model"}',
            '{"message": "Not ready yet"}',
        ],
    )
    def test_matches_known_warmup_bodies(self, body: str):
        resp = _mock_status_response(400, body)
        assert _is_warmup_400(resp) is True

    def test_not_400_returns_false(self):
        resp = _mock_status_response(500, '{"error": "Model not loaded"}')
        assert _is_warmup_400(resp) is False

    def test_non_warmup_400_returns_false(self):
        resp = _mock_status_response(400, '{"error": "Invalid response_format schema"}')
        assert _is_warmup_400(resp) is False

    def test_empty_body_returns_false(self):
        resp = _mock_status_response(400, "")
        assert _is_warmup_400(resp) is False


@pytest.mark.asyncio
async def test_chat_retries_on_400_warmup_body_then_succeeds():
    """First parallel iteration may hit 400 while the OpenAI runtime is still warming; retry."""
    resp400 = _mock_status_response(
        400, json.dumps({"error": "Model not loaded yet"}), reason="Bad Request"
    )
    resp200 = MagicMock()
    resp200.status_code = 200
    resp200.raise_for_status = lambda: None
    resp200.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": None,
    }
    mock_models = MagicMock()
    mock_models.status_code = 200
    mock_models.json.return_value = {"data": [{"id": "warmup-m"}]}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_models)
    instance.post = AsyncMock(side_effect=[resp400, resp200])
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.providers.lmstudio._ensure_model_loaded", AsyncMock()),
        patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance),
        patch("app.providers.lmstudio.asyncio.sleep", AsyncMock()),
    ):
        provider = LMStudioProvider(api_key="test-token")
        out = await provider.chat([{"role": "user", "content": "x"}], options={})

    assert instance.post.await_count == 2
    assert out.raw_text == "ok"


@pytest.mark.asyncio
async def test_chat_surfaces_body_on_non_warmup_400():
    """Real 400 (e.g. bad schema) must surface LM Studio's body in the raised ValueError."""
    body = json.dumps({"error": {"message": "Invalid response_format schema"}})
    resp400 = _mock_status_response(400, body, reason="Bad Request")
    mock_models = MagicMock()
    mock_models.status_code = 200
    mock_models.json.return_value = {"data": [{"id": "m-1"}]}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_models)
    instance.post = AsyncMock(return_value=resp400)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.providers.lmstudio._ensure_model_loaded", AsyncMock()),
        patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance),
    ):
        provider = LMStudioProvider(api_key="test-token")
        with pytest.raises(ValueError, match="Invalid response_format schema") as exc_info:
            await provider.chat([{"role": "user", "content": "x"}], options={})

    assert "400" in str(exc_info.value)
    assert "Bad Request" in str(exc_info.value)
    assert instance.post.await_count == 1


@pytest.mark.asyncio
async def test_chat_surfaces_body_on_non_transient_5xx():
    """Non-transient/unknown 4xx/5xx (e.g. 404) surfaces body text instead of httpx default."""
    resp404 = _mock_status_response(404, "Model id not found", reason="Not Found")
    mock_models = MagicMock()
    mock_models.status_code = 200
    mock_models.json.return_value = {"data": [{"id": "m-1"}]}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_models)
    instance.post = AsyncMock(return_value=resp404)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.providers.lmstudio._ensure_model_loaded", AsyncMock()),
        patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance),
    ):
        provider = LMStudioProvider(api_key="test-token")
        with pytest.raises(ValueError, match="Model id not found") as exc_info:
            await provider.chat([{"role": "user", "content": "x"}], options={})

    assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_chat_auto_resolve_uses_first_openai_model_id():
    openai = {"data": [{"id": "first-id"}, {"id": "second-id"}]}
    native = {"models": [{"key": "first-id", "loaded_instances": [{"id": "x"}]}]}
    chat_json = {"choices": [{"message": {"content": "ok"}}], "usage": None}
    instance = _mock_http_clients(openai, native, chat_json)
    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        await provider.chat([{"role": "user", "content": "x"}], options={})
    assert instance.post.call_args[1]["json"]["model"] == "first-id"


@pytest.mark.asyncio
async def test_chat_raises_when_auto_resolve_finds_no_models():
    mock_empty = MagicMock()
    mock_empty.status_code = 200
    mock_empty.json.return_value = {"data": []}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_empty)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        with pytest.raises(ValueError, match="No LM Studio chat model"):
            await provider.chat([{"role": "user", "content": "x"}], options={})


class TestMultimodalRejectionHeuristics:
    def test_payload_detects_image_url_part(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "x"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ],
                }
            ]
        }
        assert _payload_has_multimodal_image_parts(payload) is True

    def test_payload_string_content_false(self):
        assert _payload_has_multimodal_image_parts({"messages": [{"role": "user", "content": "hi"}]}) is False

    def test_body_suggests_multimodal_rejection(self):
        assert _lmstudio_body_suggests_model_not_multimodal(400, "Model does not support vision input") is True

    def test_body_warmup_not_multimodal(self):
        assert _lmstudio_body_suggests_model_not_multimodal(400, "Model not loaded") is False


@pytest.mark.asyncio
async def test_chat_400_vision_rejection_raises_lm_studio_model_not_multimodal_error():
    body = json.dumps({"error": {"message": "This model does not support image input"}})
    resp400 = _mock_status_response(400, body, reason="Bad Request")
    mock_models = MagicMock()
    mock_models.status_code = 200
    mock_models.json.return_value = {"data": [{"id": "m-1"}]}
    instance = MagicMock()
    instance.get = AsyncMock(return_value=mock_models)
    instance.post = AsyncMock(return_value=resp400)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    mm_messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ]
    with (
        patch("app.providers.lmstudio._ensure_model_loaded", AsyncMock()),
        patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance),
    ):
        provider = LMStudioProvider(api_key="test-token")
        with pytest.raises(LMStudioModelNotMultimodalError, match="does not support image"):
            await provider.chat(mm_messages, options={"model": "m-1"})


class TestNormalizeOpenaiUsageForProvider:
    def test_none_and_non_dict(self):
        assert normalize_openai_usage_for_provider(None) is None
        assert normalize_openai_usage_for_provider("x") is None
        assert normalize_openai_usage_for_provider([]) is None

    def test_flat_unchanged(self):
        u = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
        assert normalize_openai_usage_for_provider(u) == u

    def test_nested_completion_tokens_details(self):
        u = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 0},
        }
        assert normalize_openai_usage_for_provider(u) == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details_reasoning_tokens": 0,
        }

    def test_deeply_nested(self):
        u = {"a": {"b": {"c": 7}}}
        assert normalize_openai_usage_for_provider(u) == {"a_b_c": 7}

    def test_skips_bool(self):
        assert normalize_openai_usage_for_provider({"x": True}) is None

    def test_empty_dict_returns_none(self):
        assert normalize_openai_usage_for_provider({}) is None

    def test_whole_float_counts_as_int(self):
        u = {"prompt_tokens": 3.0, "completion_tokens_details": {"reasoning_tokens": 63.0}}
        assert normalize_openai_usage_for_provider(u) == {
            "prompt_tokens": 3,
            "completion_tokens_details_reasoning_tokens": 63,
        }


def test_provider_response_accepts_raw_nested_usage():
    """Field validator must flatten even if a caller passes unnormalized usage."""
    r = ProviderResponse(
        raw_text="x",
        provider_name="lmstudio",
        usage={
            "prompt_tokens": 1,
            "completion_tokens_details": {"reasoning_tokens": 63},
        },
    )
    assert r.usage == {
        "prompt_tokens": 1,
        "completion_tokens_details_reasoning_tokens": 63,
    }


@pytest.mark.asyncio
async def test_chat_normalizes_nested_usage_like_gemma():
    """Gemma-style nested completion_tokens_details must not break ProviderResponse."""
    chat_json = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 1,
            "total_tokens": 6,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }
    mid = "mock-lmstudio-model"
    openai_list = {"data": [{"id": mid}]}
    native_list = {"models": [{"key": mid, "loaded_instances": [{"id": "i"}]}]}
    instance = _mock_http_clients(openai_list, native_list, chat_json)

    with patch("app.providers.lmstudio.httpx.AsyncClient", return_value=instance):
        provider = LMStudioProvider(api_key="test-token")
        response = await provider.chat([{"role": "user", "content": "x"}], options={})

    assert response.usage == {
        "prompt_tokens": 5,
        "completion_tokens": 1,
        "total_tokens": 6,
        "completion_tokens_details_reasoning_tokens": 0,
    }
