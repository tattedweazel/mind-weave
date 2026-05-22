"""Parity: every row in shared/workflow_graph_step_kinds.json must parse via _parse_node."""

import importlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from app.domain.schemas.graph_nodes import SimpleLLMCallSkillNode
from app.domain.palette_defaults import DEFAULT_PALETTE_COLORS, WORKFLOW_PALETTE_FAMILY_KEYS
from app.domain.workflow_executor.parsing import _parse_node

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "shared" / "workflow_graph_step_kinds.json"

_WF_ID = "00000000-0000-0000-0000-0000000000aa"
_STRUCTURE_ID = "00000000-0000-0000-0000-0000000000bb"
_DOCUMENT_ID = "00000000-0000-0000-0000-0000000000cc"


def _minimal_raw_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal API-shaped node dict for manifest row `step`."""
    node_id = "parity_node"
    pos = {"x": 0.0, "y": 0.0}
    kind = step["kind"]
    label = "p"

    if kind == "primitive":
        pt = step["primitive_type"]
        if pt == "string":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "string",
                "label": label,
                "data": {"text": ""},
                "position": pos,
            }
        if pt == "list":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "list",
                "label": label,
                "data": [],
                "position": pos,
            }
        if pt == "dictionary":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "dictionary",
                "label": label,
                "data": {},
                "position": pos,
            }
        if pt == "boolean":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "boolean",
                "label": label,
                "data": {"value": False},
                "position": pos,
            }
        if pt == "int":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "int",
                "label": label,
                "data": {"value": 0},
                "position": pos,
            }
        if pt == "datetime":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "datetime",
                "label": label,
                "data": {"iso": "2026-01-01T00:00:00Z"},
                "position": pos,
            }
        if pt == "structure":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "structure",
                "label": label,
                "data": {"structure_id": _STRUCTURE_ID},
                "position": pos,
            }
        if pt == "document":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "document",
                "label": label,
                "data": {"document_id": _DOCUMENT_ID},
                "position": pos,
            }
        if pt == "image":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "image",
                "label": label,
                "data": {
                    "artifact_id": "00000000-0000-0000-0000-0000000000dd",
                    "required_inputs": [{"key": "image", "type": "dictionary", "value": None}],
                },
                "position": pos,
            }
        if pt == "sandbox_tick":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "sandbox_tick",
                "label": label,
                "data": {},
                "position": pos,
            }
        if pt == "gmail":
            return {
                "id": node_id,
                "kind": "primitive",
                "primitive_type": "gmail",
                "label": label,
                "data": {"message": {"id": "parity-msg"}},
                "position": pos,
            }
        pytest.fail(f"unknown primitive_type {pt}")

    if kind == "skill":
        st = step["skill_type"]
        return {
            "id": node_id,
            "kind": "skill",
            "skill_type": st,
            "label": label,
            "data": {},
            "position": pos,
        }

    if kind == "utility":
        ut = step["utility_type"]
        base = {
            "id": node_id,
            "kind": "utility",
            "utility_type": ut,
            "label": label,
            "data": {},
            "position": pos,
        }
        if ut == "list_item_by_index":
            base["data"] = {
                "required_inputs": [
                    {"key": "index", "type": "int", "value": 0},
                    {"key": "list", "type": "list", "value": None},
                ]
            }
        if ut == "dictionary_value_by_key":
            base["data"] = {
                "output_value_type": "list",
                "required_inputs": [
                    {"key": "key", "type": "string", "value": ""},
                    {"key": "dictionary", "type": "dictionary", "value": None},
                    {"key": "fallback", "type": "any", "value": None},
                ],
            }
        if ut == "dictionary_set_value_by_key":
            base["data"] = {
                "required_inputs": [
                    {"key": "dictionary", "type": "dictionary", "value": None},
                    {"key": "key", "type": "string", "value": ""},
                    {"key": "value", "type": "any", "value": None},
                ],
            }
        if ut == "read_document_property":
            base["data"] = {
                "output_value_type": "string",
                "required_inputs": [
                    {"key": "target_property", "type": "string", "value": ""},
                    {"key": "document", "type": "document", "value": None},
                ],
            }
        if ut == "load_document":
            base["data"] = {
                "required_inputs": [
                    {"key": "document_id", "type": "string", "value": None},
                    {"key": "document_name", "type": "string", "value": None},
                ],
            }
        if ut == "upsert_document":
            base["data"] = {
                "required_inputs": [
                    {"key": "name", "type": "string", "value": "n"},
                    {"key": "content", "type": "string", "value": "{}"},
                    {"key": "existing_document_id", "type": "string", "value": None},
                    {"key": "write_mode", "type": "string", "value": "merge_json"},
                ],
            }
        if ut == "parse_document_body":
            base["data"] = {
                "required_inputs": [
                    {"key": "document", "type": "document", "value": None},
                ],
            }
        if ut == "html_parse_basic":
            base["data"] = {
                "required_inputs": [
                    {"key": "html", "type": "string", "value": None},
                ],
            }
        if ut == "write_object_to_document_body":
            base["data"] = {
                "required_inputs": [
                    {"key": "value", "type": "any", "value": None},
                ],
            }
        if ut == "append_value_to_document":
            base["data"] = {
                "required_inputs": [
                    {"key": "document", "type": "document", "value": None},
                    {"key": "value", "type": "any", "value": None},
                ],
            }
        if ut == "validate_against_structure":
            base["data"] = {
                "structure_id": None,
                "required_inputs": [
                    {"key": "value", "type": "any", "value": None},
                    {"key": "structure", "type": "structure", "value": None},
                ],
            }
        if ut == "add_to_list":
            base["data"] = {
                "required_inputs": [
                    {"key": "list", "type": "list", "value": None},
                    {"key": "value", "type": "any", "value": None},
                ]
            }
        if ut == "message":
            base["data"] = {
                "required_inputs": [
                    {"key": "message", "type": "string", "value": None},
                ]
            }
        if ut == "string_trunc":
            base["data"] = {
                "required_inputs": [
                    {"key": "target_string", "type": "string", "value": ""},
                    {"key": "start_index", "type": "int", "value": 0},
                    {"key": "end_index", "type": "int", "value": -1},
                ]
            }
        return base

    if kind == "control":
        ct = step["control_type"]
        base_ci = {
            "id": node_id,
            "kind": "control",
            "control_type": ct,
            "label": label,
            "position": pos,
        }
        if ct == "basic_conditional":
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "condition", "type": "boolean", "value": None},
                ]
            }
        elif ct == "is_empty":
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "value", "type": "any", "value": None},
                ]
            }
        elif ct == "not":
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "input", "type": "boolean", "value": None},
                ]
            }
        elif ct == "between":
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "low", "type": "int", "value": 0},
                    {"key": "value", "type": "int", "value": 0},
                    {"key": "high", "type": "int", "value": 0},
                ]
            }
        elif ct in ("and", "or", "xor"):
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "input_a", "type": "boolean", "value": None},
                    {"key": "input_b", "type": "boolean", "value": None},
                ]
            }
        elif ct == "try_catch":
            base_ci["data"] = {}
        elif ct == "for_loop":
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "input", "type": "list", "value": None},
                ]
            }
        elif ct == "for_loop_end":
            base_ci["data"] = {
                "for_loop_id": "parity_for_loop",
                "exports": ["odds", "evens"],
            }
        else:
            base_ci["data"] = {
                "required_inputs": [
                    {"key": "input_a", "type": "string", "value": None},
                    {"key": "input_b", "type": "string", "value": None},
                ]
            }
        return base_ci

    if kind == "start":
        return {
            "id": node_id,
            "kind": "start",
            "label": label,
            "data": {},
            "position": pos,
        }

    if kind == "stop":
        return {
            "id": node_id,
            "kind": "stop",
            "label": label,
            "data": {
                "required_outputs": [{"key": "output", "type": "string"}],
            },
            "position": pos,
        }

    if kind == "workflow":
        return {
            "id": node_id,
            "kind": "workflow",
            "label": label,
            "data": {"workflow_id": _WF_ID},
            "position": pos,
        }

    pytest.fail(f"unknown kind {kind}")


@pytest.fixture(scope="module")
def manifest_steps():
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return raw["steps"]


def test_manifest_step_parses_and_matches_model(manifest_steps):
    for step in manifest_steps:
        raw = _minimal_raw_step(step)
        parsed = _parse_node(raw)
        assert parsed is not None, f"parse failed for manifest step {step}"
        model_name = step["pydantic_model"]
        mod = importlib.import_module("app.domain.schemas.graph_nodes")
        model_cls = getattr(mod, model_name)
        assert isinstance(parsed, model_cls), f"expected {model_name} for {step}, got {type(parsed).__name__}"


def test_manifest_path_exists():
    assert MANIFEST_PATH.is_file()


def test_manifest_palette_handles_cover_default_colors():
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert raw.get("manifest_version") >= 2
    handles = {s["palette_handle"] for s in raw["steps"]}
    extras = raw.get("palette_extras") or []
    handles |= {e["palette_handle"] for e in extras}
    unset = sorted(set(DEFAULT_PALETTE_COLORS) - handles - WORKFLOW_PALETTE_FAMILY_KEYS)
    assert not unset, f"palette_defaults keys missing from manifest handles: {unset}"


def test_manifest_palette_handles_unique():
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    step_handles = [s["palette_handle"] for s in raw["steps"]]
    extras = raw.get("palette_extras") or []
    extra_handles = [e["palette_handle"] for e in extras]
    all_h = step_handles + extra_handles
    assert len(all_h) == len(set(all_h)), f"duplicate palette_handle entries: {all_h}"

    seen = set()
    for row in raw["steps"]:
        assert "palette_handle" in row and "editor_label" in row and row["editor_label"]
        ph = row["palette_handle"]
        assert ph not in seen
        seen.add(ph)
    for row in extras:
        assert row["palette_handle"] not in seen
        seen.add(row["palette_handle"])
        assert row.get("editor_label")


def test_legacy_utility_simple_llm_call_parses_as_skill_node():
    raw = {
        "id": "n1",
        "kind": "utility",
        "utility_type": "simple_llm_call",
        "label": "LLM",
        "data": {"persona_id": None},
        "position": {"x": 0.0, "y": 0.0},
    }
    parsed = _parse_node(raw)
    assert isinstance(parsed, SimpleLLMCallSkillNode)
    assert parsed.kind == "skill"
    assert parsed.skill_type == "simple_llm_call"
