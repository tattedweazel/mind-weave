"""Normalize JSON Schema for LM Studio structured output (MLX/outlines compatibility).

LM Studio's MLX backend uses the outlines library, which expects `type` fields
to be strings. JSON Schema permits `type` as an array (e.g. `["string", "null"]`).
This module recursively normalizes schemas so every `type` is a string.
"""

from typing import Any, Dict


def _normalize_type(type_val: Any) -> str | None:
    """Convert type to a string. If type is an array, pick first non-null, else first."""
    if type_val is None:
        return None
    if isinstance(type_val, str):
        return type_val
    if isinstance(type_val, (list, tuple)):
        # Pick first non-null, or first element
        for t in type_val:
            if t is not None and t != "null":
                return str(t) if isinstance(t, str) else None
        if type_val:
            first = type_val[0]
            return str(first) if isinstance(first, str) else None
        return None
    return None


def _normalize_schema_recursive(schema: Any) -> Any:
    """Recursively normalize a JSON Schema object. Mutates in place but returns for clarity."""
    if schema is None:
        return None
    if not isinstance(schema, dict):
        return schema

    result: Dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type":
            normalized = _normalize_type(value)
            if normalized is not None:
                result[key] = normalized
            else:
                result[key] = value  # preserve as-is if we couldn't normalize
        elif key in ("properties",):
            if isinstance(value, dict):
                result[key] = {k: _normalize_schema_recursive(v) for k, v in value.items()}
            else:
                result[key] = value
        elif key in ("items", "additionalProperties"):
            if isinstance(value, dict):
                result[key] = _normalize_schema_recursive(value)
            elif isinstance(value, list):
                result[key] = [_normalize_schema_recursive(v) for v in value]
            else:
                result[key] = value
        elif key in ("oneOf", "anyOf", "allOf"):
            if isinstance(value, list):
                result[key] = [_normalize_schema_recursive(v) for v in value]
            else:
                result[key] = value
        elif key == "$defs" and isinstance(value, dict):
            result[key] = {k: _normalize_schema_recursive(v) for k, v in value.items()}
        else:
            result[key] = value

    return result


def normalize_schema_for_structured_output(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a JSON Schema for LM Studio structured output (MLX/outlines).

    Converts every `type` field from array (e.g. `["string", "null"]`) to string
    (e.g. `"string"`). Recursively processes properties, items, oneOf, anyOf,
    allOf, additionalProperties, and $defs.

    Args:
        schema: Raw JSON Schema dict (from Structure.json_schema).

    Returns:
        Normalized schema suitable for response_format.json_schema.schema.
    """
    if not schema or not isinstance(schema, dict):
        return schema
    return _normalize_schema_recursive(dict(schema))
