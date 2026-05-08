"""Reference JSON Schema for LLM-generated workflow exports (shared/)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.domain.workflow_executor.schema_normalizer import normalize_schema_for_structured_output

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "shared" / "mind_weave_workflow_export_llm_response.schema.json"


@pytest.fixture
def workflow_export_schema() -> dict:
    raw = _SCHEMA_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def test_reference_schema_file_exists_and_is_valid_json_schema(workflow_export_schema: dict) -> None:
    assert workflow_export_schema.get("type") == "object"
    assert "properties" in workflow_export_schema
    assert workflow_export_schema["properties"].get("kind", {}).get("const") == "mind_weave_workflow_export"
    Draft202012Validator.check_schema(workflow_export_schema)


def test_normalize_schema_for_structured_output_preserves_const_and_refs(workflow_export_schema: dict) -> None:
    normalized = normalize_schema_for_structured_output(workflow_export_schema)
    assert normalized["properties"]["kind"]["const"] == "mind_weave_workflow_export"
    assert "$defs" in normalized


def test_minimal_valid_export_passes(workflow_export_schema: dict) -> None:
    """Matches the pass-through example in WORKFLOW_EXPORT_FROM_PROMPT.md."""
    instance = {
        "kind": "mind_weave_workflow_export",
        "schema_version": 1,
        "exported_at": "2026-03-22T12:00:00.000Z",
        "definition": {
            "name": "Minimal pass-through",
            "description": "Test",
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {
                            "required_inputs": [
                                {"key": "user_input", "type": "string", "value": None},
                            ]
                        },
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": "n_stop",
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": "n_start",
                        "target": "n_stop",
                        "source_handle": "user_input",
                        "target_handle": "output",
                    },
                ],
            },
        },
    }
    Draft202012Validator(workflow_export_schema).validate(instance)


def test_definition_only_root_fails(workflow_export_schema: dict) -> None:
    instance = {
        "name": "Bad",
        "description": "No envelope",
        "graph": {"schema_version": 1, "nodes": [], "edges": []},
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(workflow_export_schema).validate(instance)


def test_start_only_graph_without_stop_fails(workflow_export_schema: dict) -> None:
    """Observed failure mode: model emits only Start + empty edges (valid under permissive schemas)."""
    instance = {
        "kind": "mind_weave_workflow_export",
        "schema_version": 1,
        "exported_at": "2026-03-22T12:00:00.000Z",
        "definition": {
            "name": "Bad",
            "description": None,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "integers", "type": "list", "value": None}]},
                        "position": {"x": 0, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(workflow_export_schema).validate(instance)


def test_empty_edges_fails(workflow_export_schema: dict) -> None:
    instance = {
        "kind": "mind_weave_workflow_export",
        "schema_version": 1,
        "exported_at": "2026-03-22T12:00:00.000Z",
        "definition": {
            "name": "Bad",
            "description": None,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "a", "type": "string", "value": None}]},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 1, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(workflow_export_schema).validate(instance)


def test_empty_start_stop_data_fails(workflow_export_schema: dict) -> None:
    instance = {
        "kind": "mind_weave_workflow_export",
        "schema_version": 1,
        "exported_at": "2026-03-22T12:00:00.000Z",
        "definition": {
            "name": "Bad",
            "description": None,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {},
                        "position": {"x": 1, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_stop", "source_handle": "a", "target_handle": "b"},
                ],
            },
        },
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(workflow_export_schema).validate(instance)


def test_primitive_without_primitive_type_fails(workflow_export_schema: dict) -> None:
    instance = {
        "kind": "mind_weave_workflow_export",
        "schema_version": 1,
        "exported_at": "2026-03-22T12:00:00.000Z",
        "definition": {
            "name": "Bad",
            "description": None,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": [{"key": "a", "type": "string", "value": None}]},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n_bad",
                        "kind": "primitive",
                        "label": "Bucket",
                        "data": {},
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "n_stop",
                        "kind": "stop",
                        "label": "Stop",
                        "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {"source": "n_start", "target": "n_bad"},
                    {"source": "n_bad", "target": "n_stop"},
                ],
            },
        },
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(workflow_export_schema).validate(instance)
