"""Deterministic JSON helpers for document body merge and serialization."""

from __future__ import annotations

import json
from typing import Any, Dict

JsonObject = Dict[str, Any]


def deterministic_json_dumps(value: Any) -> str:
    """Stable string for persisted document bodies and workflow outputs."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json_object_strict(text: str, *, what: str) -> JsonObject:
    """Parse JSON text; value must be a JSON object (not array or scalar)."""
    s = text.strip()
    try:
        val = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"{what}: invalid JSON ({e})") from e
    if not isinstance(val, dict):
        raise ValueError(f"{what}: JSON root must be an object, not {type(val).__name__}")
    return val


def merge_json_objects(base: JsonObject, incoming: JsonObject) -> JsonObject:
    """Deep-merge dicts; for conflicting keys, values from incoming win (recursive for nested dicts)."""
    out: JsonObject = dict(base)
    for k, v in incoming.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = merge_json_objects(out[k], v)
        else:
            out[k] = v
    return out
