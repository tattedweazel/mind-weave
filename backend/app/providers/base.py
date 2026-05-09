from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.providers.openai_usage import normalize_openai_usage_for_provider


class ProviderResponse(BaseModel):
    raw_text: str
    parsed: Optional[Dict[str, Any]] = None
    provider_name: str
    usage: Optional[Dict[str, int]] = None

    @field_validator("usage", mode="before")
    @classmethod
    def _normalize_usage(cls, v: Any) -> Optional[Dict[str, int]]:
        """Always flatten OpenAI-style nested usage (e.g. completion_tokens_details)."""
        return normalize_openai_usage_for_provider(v)


class ModelProvider(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> ProviderResponse:
        """
        Sends a conversation history to the model provider.
        messages matches OpenAI format: [{"role": "system", "content": "..."}].
        ``content`` may be a string or a list of parts (e.g. text + image_url) for multimodal models.
        """
        pass
