"""Normalize OpenAI-compatible chat completion `usage` objects for ProviderResponse."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any, Dict, Optional


def _usage_int_leaf(v: Any) -> int | None:
    """Coerce token counts to int (APIs may use int or whole floats)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and isfinite(v) and v == int(v):
        return int(v)
    return None


def normalize_openai_usage_for_provider(usage: Any) -> Optional[Dict[str, int]]:
    """Flatten nested usage dicts to Dict[str, int] for Pydantic ProviderResponse.

    Some models (e.g. Gemma via LM Studio) return nested objects such as
    completion_tokens_details: {reasoning_tokens: 0}. Flat keys use underscores,
    e.g. completion_tokens_details_reasoning_tokens.
    """
    if usage is None or not isinstance(usage, Mapping):
        return None

    out: Dict[str, int] = {}

    def _walk(d: Mapping[str, Any], prefix: str) -> None:
        for k, v in d.items():
            ks = str(k)
            key = f"{prefix}_{ks}" if prefix else ks
            if isinstance(v, Mapping):
                _walk(v, key)
            else:
                coerced = _usage_int_leaf(v)
                if coerced is not None:
                    out[key] = coerced

    _walk(usage, "")
    return out if out else None
