import asyncio
import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.providers.base import ModelProvider, ProviderResponse
from app.providers.lmstudio_http import (
    bearer_auth_headers,
    lmstudio_origin,
    normalize_bearer_secret_value,
    normalize_openai_base_url,
    resolve_lmstudio_bearer,
)
from app.providers.openai_usage import normalize_openai_usage_for_provider

# Matches any <|...|> special token produced by some model chat templates
_PROTOCOL_TOKEN_RE = re.compile(r"<\|[^|>]+\|>")

# Serialize native load / loaded check per (origin, model) across parallel workflow nodes.
_load_locks: dict[str, asyncio.Lock] = {}

# LM Studio may return 500 while weights are still initializing; 504 from some proxies.
_TRANSIENT_CHAT_STATUSES = frozenset({429, 500, 502, 503, 504})

class LMStudioModelNotMultimodalError(ValueError):
    """Raised when LM Studio rejects a chat request that includes image content (model not vision-capable)."""

    def __init__(self, message: str, *, provider_detail: str = ""):
        super().__init__(message)
        self.provider_detail = (provider_detail or "").strip()


def _payload_has_multimodal_image_parts(payload: dict[str, Any]) -> bool:
    for m in payload.get("messages") or []:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _lmstudio_body_suggests_model_not_multimodal(status_code: int, body: str) -> bool:
    """Heuristic: LM Studio / OpenAI-compatible servers often return 400/422 when the loaded LLM is text-only."""
    if status_code not in (400, 415, 422):
        return False
    low = (body or "").lower()
    if not low:
        return False
    if any(marker in low for marker in _WARMUP_BODY_MARKERS):
        return False
    markers = (
        "image input",
        "image_url",
        "vision",
        "multimodal",
        "does not support",
        "unsupported image",
        "invalid image",
        "image content",
        "cannot process image",
        "visual input",
        "invalid content",
        "content type",
    )
    return any(m in low for m in markers)


# LM Studio can also surface warmup races as 400 Bad Request with a body indicating the runtime is
# still loading. See docs/OPERATIONS.md "400 from LM Studio" for the full list of known markers.
# Case-insensitive substrings matched against the extracted error body (see ``_read_lm_error_body``).
_WARMUP_BODY_MARKERS: tuple[str, ...] = (
    "model not loaded",
    "model is not loaded",
    "no runtime",
    "model is loading",
    "model is warming",
    "warming up",
    "not ready",
    "still loading",
)

# Cap body read so a misbehaving LM Studio can't bloat logs or error text.
_LM_ERROR_BODY_READ_CAP = 2048


def _strip_protocol_tokens(text: str) -> str:
    """Remove model chat-template protocol tokens (e.g. <|channel|>, <|constrain|>).

    Some models trained with tool-calling capabilities leak these tokens into
    their plain-text output. We strip them defensively at the provider layer so
    that no upstream code ever sees them.
    """
    return _PROTOCOL_TOKEN_RE.sub("", text).strip()


def _find_json_blocks(text: str) -> list[tuple[int, int]]:
    """Find all top-level JSON object/array blocks. Returns list of (start, end) slices."""
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        if text[i] in "{[":
            start = i
            stack = 1
            open_ch, close_ch = ("{", "}") if text[i] == "{" else ("[", "]")
            i += 1
            while i < len(text) and stack > 0:
                if text[i] == open_ch:
                    stack += 1
                elif text[i] == close_ch:
                    stack -= 1
                elif text[i] in "\"'":
                    # Skip string contents
                    q = text[i]
                    i += 1
                    while i < len(text):
                        if text[i] == "\\":
                            i += 2
                            continue
                        if text[i] == q:
                            i += 1
                            break
                        i += 1
                    continue
                i += 1
            if stack == 0:
                blocks.append((start, i))
        else:
            i += 1
    return blocks


def _extract_last_json_block(text: str) -> str | None:
    """When text contains multiple JSON blocks (e.g. {...}\\n[...]), return the last one.
    Models sometimes output reasoning as an object then the answer as an array."""
    blocks = _find_json_blocks(text)
    if len(blocks) <= 1:
        return None
    start, end = blocks[-1]
    return text[start:end].strip()


def _extract_clean_content(raw: str) -> str:
    """Strip protocol tokens and extract the JSON payload.

    If the response contains a <|message|> marker (agentic protocol), we take
    only the content that follows it. Then we further narrow to the first
    {...} block to avoid any surrounding noise.
    """
    # First, if there's an explicit <|message|> separator, grab what follows
    if "<|message|>" in raw:
        raw = raw.split("<|message|>")[-1]

    # Strip all remaining <|...|> tokens
    cleaned = _strip_protocol_tokens(raw)

    # Narrow to the JSON object boundaries if present
    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")

    # Find the earliest valid start block
    start = -1
    if start_obj != -1 and start_arr != -1:
        start = min(start_obj, start_arr)
    elif start_obj != -1:
        start = start_obj
    elif start_arr != -1:
        start = start_arr

    if start != -1:
        # Determine the expected end character based on the start character
        end_char = "}" if cleaned[start] == "{" else "]"
        end = cleaned.rfind(end_char)
        if end != -1 and end >= start:
            cleaned = cleaned[start : end + 1]

    return cleaned.strip()


# Historically defaulted in config; never a real LM Studio model id — treat like "unset".
_PLACEHOLDER_LM_MODEL_IDS = frozenset({"local-model"})


def _needs_lm_model_auto_resolve(model: str | None) -> bool:
    if model is None:
        return True
    s = str(model).strip()
    if not s:
        return True
    return s.lower() in _PLACEHOLDER_LM_MODEL_IDS


async def _fetch_first_openai_models_list_id(
    *,
    base_url: str,
    headers: dict[str, str],
) -> str | None:
    """GET OpenAI-compatible ``/v1/models``; return first ``data[].id``."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(url, headers=headers, timeout=10.0)
            if r.status_code != 200:
                logger.warning(
                    "LM Studio OpenAI models list returned %s; cannot auto-select chat model",
                    r.status_code,
                )
                return None
            body = r.json()
    except Exception as e:
        logger.warning("LM Studio OpenAI models list failed: %s", e)
        return None
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list):
        return None
    for item in data:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid.strip():
                return mid.strip()
    return None


def _lock_for_load(origin: str, model: str) -> asyncio.Lock:
    key = f"{origin}\0{model}"
    if key not in _load_locks:
        _load_locks[key] = asyncio.Lock()
    return _load_locks[key]


def _native_list_shows_model_loaded(data: Any, model: str) -> bool:
    """True if LM Studio native GET /api/v1/models JSON lists this model with a non-empty loaded_instances."""
    models_list = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models_list, list):
        return False
    for m in models_list:
        if not isinstance(m, dict):
            continue
        if m.get("key") != model:
            continue
        inst = m.get("loaded_instances")
        return isinstance(inst, list) and len(inst) > 0
    return False


async def _ensure_model_loaded(
    *,
    origin: str,
    model: str,
    headers: dict[str, str],
) -> None:
    """Best-effort: native GET /api/v1/models then POST load if not in memory."""
    list_url = f"{origin}/api/v1/models"
    load_url = f"{origin}/api/v1/models/load"
    lock = _lock_for_load(origin, model)
    async with lock:
        async with httpx.AsyncClient(trust_env=False) as client:
            try:
                r = await client.get(list_url, headers=headers, timeout=10.0)
                if r.status_code != 200:
                    logger.warning(
                        "LM Studio native list models returned %s; skipping preload",
                        r.status_code,
                    )
                    return
                data = r.json()
            except Exception as e:
                logger.warning("LM Studio native list models failed (%s); skipping preload", e)
                return
            if _native_list_shows_model_loaded(data, model):
                return
            try:
                lr = await client.post(
                    load_url,
                    headers=headers,
                    json={"model": model},
                    timeout=settings.LMSTUDIO_MODEL_LOAD_TIMEOUT,
                )
                lr.raise_for_status()
            except Exception as e:
                logger.warning("LM Studio POST /api/v1/models/load failed (%s); continuing to chat", e)
                return

            max_ready = float(settings.LMSTUDIO_MODEL_READY_MAX_WAIT_SECONDS)
            if max_ready <= 0:
                return
            ready_deadline = time.monotonic() + max_ready
            poll_s = 0.5
            while time.monotonic() < ready_deadline:
                try:
                    rp = await client.get(list_url, headers=headers, timeout=10.0)
                    if rp.status_code != 200:
                        logger.warning(
                            "LM Studio ready poll: native list models returned %s",
                            rp.status_code,
                        )
                        break
                    data = rp.json()
                    if _native_list_shows_model_loaded(data, model):
                        return
                except Exception as e:
                    logger.warning("LM Studio ready poll failed (%s); continuing to chat", e)
                    break
                remain = ready_deadline - time.monotonic()
                if remain <= 0:
                    break
                await asyncio.sleep(min(poll_s, remain))
            logger.warning(
                "LM Studio model %r did not report loaded_instances within %ss after load; chat retries may apply",
                model,
                max_ready,
            )


def _read_lm_error_body(response: httpx.Response) -> str:
    """Return a short, human-readable snippet of an LM Studio error response body.

    Prefers ``error`` / ``error.message`` / ``message`` JSON fields when the body parses,
    otherwise returns the raw text trimmed to ``_LM_ERROR_BODY_READ_CAP`` chars. Never raises.
    """
    try:
        raw = response.text or ""
    except Exception:
        return ""
    snippet = raw[:_LM_ERROR_BODY_READ_CAP].strip()
    if not snippet:
        return ""
    try:
        parsed = json.loads(snippet)
    except (json.JSONDecodeError, ValueError):
        return snippet
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
        msg = parsed.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return snippet


def _is_warmup_400(response: httpx.Response) -> bool:
    """True iff the response is a 400 whose extracted body matches a known warmup marker.

    LM Studio reports cold-start races as 400 with bodies like ``"Model not loaded"`` or
    ``"No runtime is loaded"``; the first chat after ``POST /api/v1/models/load`` can hit this
    window even when native ``GET /api/v1/models`` already shows ``loaded_instances``.
    """
    if response.status_code != 400:
        return False
    body = _read_lm_error_body(response)
    if not body:
        return False
    low = body.lower()
    return any(marker in low for marker in _WARMUP_BODY_MARKERS)


async def _post_chat_completions(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> httpx.Response:
    """POST chat/completions with transient retries.

    Retries the same statuses as before (429/500/502/503/504) plus **400 when the body matches a
    known warmup marker** (see ``_WARMUP_BODY_MARKERS``). Non-warmup 4xx/5xx errors are re-raised as
    ``ValueError`` carrying status + short body snippet so the Simple LLM Call step error shows the
    actual LM Studio message instead of httpx's default ``...``.
    """
    budget = settings.LMSTUDIO_CHAT_RETRY_BUDGET_SECONDS
    deadline = time.monotonic() + max(0.0, budget)
    delay = 0.5
    last_retryable_err: Exception | None = None
    async with httpx.AsyncClient(trust_env=False) as client:
        while True:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=settings.LMSTUDIO_CHAT_TIMEOUT,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code == 401:
                    raise ValueError(
                        "LM Studio returned 401 Unauthorized: the API token was rejected. "
                        "Confirm the token in LM Studio → Server Settings → API Tokens matches "
                        "My Settings → LM Studio API key (or LMSTUDIO_API_KEY on the server). "
                        "If you recently changed SECRET_KEY, re-save your API keys."
                    ) from e
                warmup = _is_warmup_400(e.response)
                if warmup:
                    body = _read_lm_error_body(e.response)
                    logger.warning(
                        "LM Studio returned 400 warmup response (%r); retrying within budget", body
                    )
                if code not in _TRANSIENT_CHAT_STATUSES and not warmup:
                    body = _read_lm_error_body(e.response)
                    reason = (e.response.reason_phrase or "").strip() or "error"
                    detail = f": {body}" if body else ""
                    if _payload_has_multimodal_image_parts(payload) and _lmstudio_body_suggests_model_not_multimodal(
                        code, body
                    ):
                        raise LMStudioModelNotMultimodalError(
                            "Selected model does not support image input.",
                            provider_detail=body,
                        ) from e
                    raise ValueError(
                        f"LM Studio returned {code} {reason}{detail}"
                    ) from e
                last_retryable_err = e
                if time.monotonic() >= deadline:
                    raise
            except httpx.RequestError:
                raise
            sleep_s = min(delay, max(0.0, deadline - time.monotonic()))
            if sleep_s <= 0:
                if last_retryable_err is not None:
                    raise last_retryable_err
                raise RuntimeError("LM Studio chat retry budget exhausted")
            sleep_s += sleep_s * random.random() * 0.2
            await asyncio.sleep(sleep_s)
            delay = min(delay * 2.0, 8.0)


class LMStudioProvider(ModelProvider):
    def __init__(self, api_key: str | None = None):
        self.base_url = normalize_openai_base_url(settings.LMSTUDIO_BASE_URL)
        self.model = settings.LMSTUDIO_MODEL
        self.provider_name = "lmstudio"
        self._explicit_api_key = api_key

    def _effective_bearer(self) -> str | None:
        if self._explicit_api_key is not None and self._explicit_api_key.strip():
            return normalize_bearer_secret_value(self._explicit_api_key)
        return resolve_lmstudio_bearer(decrypted_api_keys=None)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderResponse:
        url = f"{self.base_url}/chat/completions"

        token = self._effective_bearer()
        if not token:
            raise ValueError(
                "LM Studio requires an API key: set lmstudio_api_key in My Settings or LMSTUDIO_API_KEY in the environment.",
            )
        headers = bearer_auth_headers(token)
        if os.environ.get("MW_DEBUG_LOG_LM_BEARER", "").strip() == "1":
            logger.warning(
                "MW_DEBUG_LOG_LM_BEARER: token=%r chat_url=%s",
                token,
                f"{self.base_url}/chat/completions",
            )

        # Allow model to be overridden via options (e.g. persona default_model / workflow step).
        model: str | None = self.model
        options_copy = dict(options) if options else {}
        if "model" in options_copy:
            model = options_copy.pop("model")
        model_str = (model if model is not None else "").strip()
        if _needs_lm_model_auto_resolve(model_str):
            resolved = await _fetch_first_openai_models_list_id(
                base_url=self.base_url,
                headers=headers,
            )
            if resolved:
                model_str = resolved
                logger.info(
                    "LM Studio chat model was unset or placeholder; using first listed model %r",
                    model_str,
                )
            else:
                raise ValueError(
                    "No LM Studio chat model is configured. Load a model in LM Studio (so it appears "
                    "under GET /v1/models), or set LMSTUDIO_MODEL to a valid model id, or set "
                    "default_model on the Persona linked to your Companion for Workspace chat."
                )
        model = model_str

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }

        # Pass response_format for structured outputs (LM Studio / OpenAI compatible)
        if options_copy.get("response_format"):
            payload["response_format"] = options_copy.pop("response_format")

        if options_copy:
            payload.update(options_copy)

        logger.info(f"Sending request to LMStudio at {url} with model {model}")

        origin = lmstudio_origin()
        await _ensure_model_loaded(origin=origin, model=model, headers=headers)

        # trust_env=False: do not honor HTTP(S)_PROXY for local LM Studio. IDE/agent shells
        # often set proxies; routing 127.0.0.1 / LAN IPs through them breaks with ConnectError.
        try:
            response = await _post_chat_completions(url=url, payload=payload, headers=headers)
            data = response.json()

            msg = data["choices"][0]["message"]
            raw_content = msg.get("content") or msg.get("reasoning_content") or ""
            if not isinstance(raw_content, str):
                raw_content = str(raw_content) if raw_content is not None else ""

            # Strip protocol tokens always. For structured output, also extract first JSON block.
            # For free-form text, skip extraction so we don't truncate e.g. "{\"reasoning\":\"...\"}\n[actual list]"
            has_structured = "response_format" in payload
            if has_structured:
                clean_content = _extract_clean_content(raw_content)
            else:
                if "<|message|>" in raw_content:
                    raw_content = raw_content.split("<|message|>")[-1]
                clean_content = _strip_protocol_tokens(raw_content)
                # When model returns multiple JSON blocks (e.g. {...}\n[...]), use the last one
                last_block = _extract_last_json_block(clean_content)
                if last_block is not None:
                    clean_content = last_block

            # Attempt to parse JSON (ProviderResponse.parsed expects Dict; lists go in raw_text)
            parsed = None
            if clean_content:
                try:
                    loaded = json.loads(clean_content)
                    parsed = loaded if isinstance(loaded, dict) else None
                except json.JSONDecodeError:
                    logger.warning("LMStudioProvider: failed to parse response as JSON")

            return ProviderResponse(
                # raw_text is also cleaned so callers never see protocol tokens
                raw_text=clean_content or _strip_protocol_tokens(raw_content),
                parsed=parsed,
                provider_name=self.provider_name,
                usage=normalize_openai_usage_for_provider(data.get("usage")),
            )
        except Exception as e:
            logger.error(f"Error calling LMStudio: {e}")
            raise
