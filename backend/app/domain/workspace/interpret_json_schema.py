"""Per-request JSON Schema tightening for Workspace interpret structured output."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Set

from sqlmodel import Session

from app.domain.schemas.workspace_contracts import InterpretationPayload
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workspace.capability_resolution import parse_workflow_id_from_capability_key
from app.domain.workspace.start_inputs import StartInputSlot, extract_start_input_slots_from_workflow_graph

_MAX_STRICT_INTERPRET_CAPABILITY_BRANCHES = 32


def _json_schema_property_for_start_slot(slot: StartInputSlot) -> Dict[str, Any]:
    """Map Start slot type to a JSON Schema property (LM Studio / outlines friendly)."""
    t = slot.input_type
    if t == "boolean":
        return {"type": "boolean"}
    if t == "int":
        return {"type": "integer"}
    if t == "list":
        return {"type": "array"}
    if t in ("dictionary", "structure", "gmail", "any"):
        return {"type": "object", "additionalProperties": True}
    if t in ("string", "datetime"):
        prop: Dict[str, Any] = {"type": "string"}
        if t == "datetime":
            prop["description"] = "RFC3339 with offset or Z"
        return prop
    return {"type": "string"}


def _candidate_capability_oneof_branch(capability_key: str, slots: List[StartInputSlot]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required_keys: List[str] = []
    for s in slots:
        properties[s.key] = _json_schema_property_for_start_slot(s)
        if not s.has_static_default:
            required_keys.append(s.key)
    if any(s.key == "user_input" for s in slots):
        properties["text"] = {
            "type": "string",
            "description": "Optional alias for user_input (same value shape).",
        }
    return {
        "type": "object",
        "properties": {
            "capability_key": {"const": capability_key},
            "confidence": {"type": "number", "default": 0.0},
            "input_bindings": {
                "type": "object",
                "properties": properties,
                "required": required_keys,
                "additionalProperties": False,
            },
        },
        "required": ["capability_key", "input_bindings"],
        "additionalProperties": False,
    }


def build_strict_candidate_capability_oneof_branches(
    session: Session,
    user_id: uuid.UUID,
    allowed_capability_keys: Set[str],
    *,
    max_branches: int = _MAX_STRICT_INTERPRET_CAPABILITY_BRANCHES,
) -> Optional[List[Dict[str, Any]]]:
    """
    Return one ``oneOf`` branch per allowed capability, or ``None`` to keep the generic Pydantic schema.

    Fails closed to ``None`` if any key does not resolve to an owned workflow or branch count exceeds cap.
    """
    keys = sorted(allowed_capability_keys)
    if not keys or len(keys) > max_branches:
        return None
    svc = WorkflowDefinitionService(session, user_id)
    branches: List[Dict[str, Any]] = []
    for key in keys:
        wf_id = parse_workflow_id_from_capability_key(key)
        if wf_id is None:
            return None
        wf = svc.get_workflow(wf_id)
        if wf is None:
            return None
        slots = extract_start_input_slots_from_workflow_graph(wf.graph if wf else None)
        branches.append(_candidate_capability_oneof_branch(key, slots))
    return branches


def interpret_json_schema_with_strict_candidate_bindings(
    session: Session,
    user_id: uuid.UUID,
    allowed_capability_keys: Set[str],
) -> Dict[str, Any]:
    """Full ``InterpretationPayload`` JSON Schema, optionally with strict per-capability ``input_bindings``."""
    base = InterpretationPayload.model_json_schema()
    branches = build_strict_candidate_capability_oneof_branches(session, user_id, allowed_capability_keys)
    if not branches:
        return base
    schema = copy.deepcopy(base)
    cap_prop = schema.get("properties", {}).get("candidate_capabilities")
    if not isinstance(cap_prop, dict):
        return base
    cap_prop["items"] = {"oneOf": branches}
    return schema
