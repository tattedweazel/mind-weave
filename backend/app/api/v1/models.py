"""LLM model listing. Uses ``async def`` because handlers await ``httpx`` (see ARCHITECTURE.md)."""

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import logger
from app.persistence.tables import User
from app.providers.lmstudio_http import bearer_auth_headers, normalize_openai_base_url, resolve_lmstudio_bearer

router = APIRouter()


class ModelsListResponse(BaseModel):
    """Model ids for Persona/workspace pickers. ``local`` is LM Studio (``LMSTUDIO_BASE_URL``)."""

    local: list[str] = Field(default_factory=list)
    external: list[str] = Field(default_factory=list)
    lm_studio_list_error: str | None = None


@router.get("/", response_model=ModelsListResponse)
async def get_models(
    _: User = Depends(get_current_user),
):
    """
    List LM Studio model ids from the OpenAI-compat ``GET …/v1/models`` endpoint.

    Uses **server** ``LMSTUDIO_API_KEY`` only so every authenticated user sees the same catalog for
    the configured ``LMSTUDIO_BASE_URL``. Per-user **My Settings** keys still apply to chat and
    workflow LLM calls. On failure, ``local`` is empty and ``lm_studio_list_error`` explains why.
    """
    out = ModelsListResponse()
    token = resolve_lmstudio_bearer(decrypted_api_keys=None)
    if not token:
        msg = (
            "No LM Studio API key configured for model listing. Set LMSTUDIO_API_KEY on the server "
            "(My Settings keys are for chat, not this list)."
        )
        logger.warning(msg)
        out.lm_studio_list_error = msg
        return out

    base = normalize_openai_base_url(settings.LMSTUDIO_BASE_URL)
    url = f"{base}/models"
    headers = bearer_auth_headers(token)

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, headers=headers, timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    out.local = [item.get("id") for item in data["data"] if "id" in item]
            else:
                snippet = (response.text or "")[:300]
                logger.warning(
                    "Failed to fetch models from LMStudio. Status: %s body_prefix: %r",
                    response.status_code,
                    snippet,
                )
                out.lm_studio_list_error = (
                    f"LM Studio returned HTTP {response.status_code} when listing models. "
                    "Confirm LMSTUDIO_API_KEY matches a token in LM Studio and the model server is running."
                )
    except Exception as e:
        logger.error("Error calling local LMStudio models endpoint (%s): %s: %s", url, type(e).__name__, e)
        out.lm_studio_list_error = (
            f"Could not reach LM Studio ({type(e).__name__}). Check LMSTUDIO_BASE_URL and server logs."
        )

    return out
