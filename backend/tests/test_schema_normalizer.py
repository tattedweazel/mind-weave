"""Tests for schema normalizer (MLX/outlines compatibility)."""

from app.domain.workflow_executor.schema_normalizer import normalize_schema_for_structured_output


def test_type_array_string_null_becomes_string():
    """type: ["string", "null"] -> type: "string"."""
    schema = {"type": ["string", "null"]}
    out = normalize_schema_for_structured_output(schema)
    assert out["type"] == "string"


def test_type_array_integer_null_becomes_integer():
    """type: ["integer", "null"] -> type: "integer"."""
    schema = {"type": ["integer", "null"]}
    out = normalize_schema_for_structured_output(schema)
    assert out["type"] == "integer"


def test_type_string_unchanged():
    """type: "string" stays as "string"."""
    schema = {"type": "string"}
    out = normalize_schema_for_structured_output(schema)
    assert out["type"] == "string"


def test_type_object_unchanged():
    """type: "object" stays as "object"."""
    schema = {"type": "object", "properties": {}, "required": []}
    out = normalize_schema_for_structured_output(schema)
    assert out["type"] == "object"
    assert out["properties"] == {}
    assert out["required"] == []


def test_nested_properties_type_array():
    """properties.foo.type: ["number", "null"] -> type: "number"."""
    schema = {
        "type": "object",
        "properties": {"foo": {"type": ["number", "null"]}, "bar": {"type": "string"}},
        "required": ["foo"],
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["properties"]["foo"]["type"] == "number"
    assert out["properties"]["bar"]["type"] == "string"


def test_items_type_array():
    """items: { type: ["string"] } -> type: "string"."""
    schema = {"type": "array", "items": {"type": ["string"]}}
    out = normalize_schema_for_structured_output(schema)
    assert out["items"]["type"] == "string"


def test_items_single_element_array():
    """items with type: ["integer", "null"] -> "integer"."""
    schema = {"type": "array", "items": {"type": ["integer", "null"]}}
    out = normalize_schema_for_structured_output(schema)
    assert out["items"]["type"] == "integer"


def test_defs_referenced_schema_with_type_array():
    """$defs subschema with type array is normalized."""
    schema = {
        "type": "object",
        "properties": {"ref": {"$ref": "#/$defs/Nullable"}},
        "$defs": {"Nullable": {"type": ["string", "null"]}},
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["$defs"]["Nullable"]["type"] == "string"


def test_oneOf_subschemas_normalized():
    """oneOf subschemas with type arrays are normalized."""
    schema = {
        "oneOf": [
            {"type": ["string", "null"]},
            {"type": "object", "properties": {"x": {"type": ["number"]}}},
        ]
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["oneOf"][0]["type"] == "string"
    assert out["oneOf"][1]["properties"]["x"]["type"] == "number"


def test_anyOf_allOf_normalized():
    """anyOf and allOf subschemas are normalized."""
    schema = {
        "anyOf": [{"type": ["boolean", "null"]}],
        "allOf": [{"type": "object", "properties": {"y": {"type": ["int", "null"]}}}],
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["anyOf"][0]["type"] == "boolean"
    assert out["allOf"][0]["properties"]["y"]["type"] == "int"


def test_additional_properties_normalized():
    """additionalProperties subschema is normalized."""
    schema = {"type": "object", "additionalProperties": {"type": ["string", "null"]}}
    out = normalize_schema_for_structured_output(schema)
    assert out["additionalProperties"]["type"] == "string"


def test_preserves_required_description_enum():
    """required, description, enum are preserved."""
    schema = {
        "type": "object",
        "properties": {"joke": {"type": ["string", "null"], "description": "A joke"}},
        "required": ["joke"],
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["required"] == ["joke"]
    assert out["properties"]["joke"]["description"] == "A joke"
    assert out["properties"]["joke"]["type"] == "string"


def test_empty_schema_unchanged():
    """Empty schema returns as-is."""
    schema = {}
    out = normalize_schema_for_structured_output(schema)
    assert out == {}


def test_none_returns_none():
    """None input returns None (defensive)."""
    out = normalize_schema_for_structured_output(None)
    assert out is None


def test_non_dict_passthrough():
    """Non-dict schema returns as-is (e.g. list/primitive - defensive)."""
    out = normalize_schema_for_structured_output([])
    assert out == []


def test_type_array_null_only():
    """type: ["null"] -> picks first element "null"."""
    schema = {"type": ["null"]}
    out = normalize_schema_for_structured_output(schema)
    assert out["type"] == "null"


def test_integration_joke_schema():
    """Schema matching test_simple_llm_with_structure_returns_dictionary_output."""
    schema = {"type": "object", "properties": {"joke": {"type": "string"}}, "required": ["joke"]}
    out = normalize_schema_for_structured_output(schema)
    assert out == schema


def test_integration_joke_schema_with_nullable():
    """Same schema but with nullable joke - normalizes for MLX."""
    schema = {
        "type": "object",
        "properties": {"joke": {"type": ["string", "null"]}},
        "required": ["joke"],
    }
    out = normalize_schema_for_structured_output(schema)
    assert out["properties"]["joke"]["type"] == "string"
