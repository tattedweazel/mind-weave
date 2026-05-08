"""Unit tests for Workspace Start input extraction."""

from __future__ import annotations

from app.domain.workspace.start_inputs import (
    extract_start_input_slots_from_workflow_graph,
    filter_bindings_to_allowed,
    format_start_slots_for_capability_prompt,
    valid_start_override_keys,
    validate_bindings_against_slots,
    validate_capability_start_bindings,
    validate_start_binding_shapes,
)


def test_extract_legacy_start_no_default():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert len(slots) == 1
    assert slots[0].key == "user_input"
    assert slots[0].has_static_default is False


def test_extract_legacy_start_with_default():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"text": "hello"},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert slots[0].has_static_default is True
    assert slots[0].static_value == "hello"


def test_extract_required_inputs_empty_list():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": []},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    assert extract_start_input_slots_from_workflow_graph(graph) == []


def test_extract_multi_slots():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "start", "type": "datetime", "value": None},
                        {"key": "end", "type": "datetime", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert len(slots) == 2
    assert {s.key for s in slots} == {"start", "end"}
    assert all(not s.has_static_default for s in slots)


def test_valid_override_keys_legacy_includes_text_alias():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert valid_start_override_keys(slots) == {"user_input", "text"}


def test_validate_bindings_multi():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "start", "type": "datetime", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert validate_bindings_against_slots(slots, {}) is not None
    assert validate_bindings_against_slots(slots, {"start": "2026-04-07T00:00:00Z"}) is None


def test_filter_bindings_drops_unknown():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "q", "type": "string", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    out = filter_bindings_to_allowed(slots, {"q": "x", "extra": 1})
    assert out == {"q": "x"}


def test_extract_merges_starts_when_first_has_empty_required_inputs():
    graph = {
        "nodes": [
            {
                "id": "s1",
                "kind": "start",
                "label": "A",
                "data": {"required_inputs": []},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "s2",
                "kind": "start",
                "label": "B",
                "data": {
                    "required_inputs": [
                        {"key": "email_list", "type": "list", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert len(slots) == 1
    assert slots[0].key == "email_list"
    assert slots[0].input_type == "list"
    assert not slots[0].has_static_default


def test_valid_override_keys_merged_legacy_and_structured_includes_text_alias():
    graph = {
        "nodes": [
            {
                "id": "s1",
                "kind": "start",
                "label": "A",
                "data": {"text": ""},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "s2",
                "kind": "start",
                "label": "B",
                "data": {
                    "required_inputs": [
                        {"key": "q", "type": "string", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert {s.key for s in slots} == {"user_input", "q"}
    assert valid_start_override_keys(slots) == {"user_input", "q", "text"}


def test_validate_start_binding_shapes_rejects_string_for_list():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "email_list", "type": "list", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    err = validate_start_binding_shapes(slots, {"email_list": "not-a-list"})
    assert err is not None
    assert "array" in err


def test_validate_start_binding_shapes_accepts_list_for_email_list_when_slot_gmail():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "email_list", "type": "gmail", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert validate_start_binding_shapes(slots, {"email_list": []}) is None
    assert validate_capability_start_bindings(slots, {"email_list": []}) is None


def test_validate_capability_start_bindings_accepts_list_shape():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "email_list", "type": "list", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    assert validate_capability_start_bindings(slots, {"email_list": []}) is None


def test_format_prompt_mentions_rfc3339_for_datetime():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {"required_inputs": [{"key": "since", "type": "datetime", "value": None}]},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    text = format_start_slots_for_capability_prompt(slots)
    assert "since" in text
    assert "RFC3339" in text


def test_format_prompt_mentions_json_array_for_list_type():
    graph = {
        "nodes": [
            {
                "id": "st",
                "kind": "start",
                "label": "Start",
                "data": {
                    "required_inputs": [
                        {"key": "items", "type": "list", "value": None},
                    ]
                },
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    slots = extract_start_input_slots_from_workflow_graph(graph)
    text = format_start_slots_for_capability_prompt(slots)
    assert "items" in text
    assert "JSON array" in text
