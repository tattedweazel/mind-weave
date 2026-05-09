"""Start node `required_inputs` metadata for Workspace capability prompts and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from app.domain.workflow_executor.parsing import _parse_node


@dataclass(frozen=True)
class StartInputSlot:
    """One Start input slot (matches executor `_resolve_start_node` semantics)."""

    key: str
    input_type: str
    has_static_default: bool
    static_value: Any = None


def _slots_from_single_start_raw(raw: Dict[str, Any]) -> List[StartInputSlot]:
    """Slots contributed by one Start node (empty if unparseable or no inputs)."""
    parsed = _parse_node(raw)
    if parsed is None:
        return []
    data = getattr(parsed, "data", None) or {}
    if not isinstance(data, dict):
        data = {}
    raw_inputs = data.get("required_inputs")
    if raw_inputs is None:
        text_default = data.get("text")
        has_def = text_default not in (None, "")
        return [
            StartInputSlot(
                key="user_input",
                input_type="string",
                has_static_default=has_def,
                static_value=text_default if has_def else None,
            )
        ]
    if not isinstance(raw_inputs, list):
        return []
    if len(raw_inputs) == 0:
        return []
    out: List[StartInputSlot] = []
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        inp_type = str(item.get("type", "string")).strip() or "string"
        val = item.get("value")
        has_def = val is not None
        if inp_type == "string" and val == "":
            has_def = False
        if inp_type == "datetime" and isinstance(val, str) and not val.strip():
            has_def = False
        out.append(
            StartInputSlot(
                key=key,
                input_type=inp_type,
                has_static_default=has_def,
                static_value=val if has_def else None,
            )
        )
    return out


def extract_start_input_slots_from_workflow_graph(graph: Optional[Dict[str, Any]]) -> List[StartInputSlot]:
    """Union of Start input slots from every Start node in graph order (first occurrence wins per key)."""
    if not graph or not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes") or []
    merged: Dict[str, StartInputSlot] = {}
    order: List[str] = []
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        if raw.get("kind") != "start":
            continue
        for slot in _slots_from_single_start_raw(raw):
            if slot.key not in merged:
                merged[slot.key] = slot
                order.append(slot.key)
    return [merged[k] for k in order]


def valid_start_override_keys(slots: List[StartInputSlot]) -> Set[str]:
    """Keys allowed in `WorkflowExecutor.run` input_overrides for Start."""
    keys = {s.key for s in slots}
    if "user_input" in keys:
        return keys | {"text"}
    return keys


def format_start_slots_for_capability_prompt(slots: List[StartInputSlot]) -> str:
    """Human-readable line for the interpret LLM (per workflow)."""
    if not slots:
        return "no Start inputs (runs without overrides)"
    if len(slots) == 1 and slots[0].key == "user_input":
        return (
            "single text input — use normalized_inputs.user_input or per-capability input_bindings.user_input "
            "(alias key `text` is also accepted)"
        )
    parts: List[str] = []
    for s in slots:
        extra = ""
        if s.input_type == "datetime":
            extra = ", RFC3339 with offset or Z"
        elif s.input_type == "list":
            extra = ', JSON array in input_bindings (e.g. [] or ["id"])'
        elif s.input_type in ("dictionary", "structure"):
            extra = ", JSON object in input_bindings"
        elif s.input_type == "gmail":
            extra = ", JSON object (Gmail-shaped) in input_bindings"
        elif s.input_type == "any":
            extra = ", JSON value as appropriate (null not allowed when required)"
        elif s.input_type == "boolean":
            extra = ", JSON true/false"
        elif s.input_type == "int":
            extra = ", JSON integer"
        elif s.input_type == "document":
            extra = ", string or object per graph default"
        if s.has_static_default:
            parts.append(f"{s.key}: {s.input_type} (optional; graph has default{extra})")
        else:
            parts.append(f"{s.key}: {s.input_type}{extra}")
    return "; ".join(parts)


def missing_required_start_binding_keys(slots: List[StartInputSlot], bindings: Dict[str, Any]) -> List[str]:
    """Keys for required Start slots that are still unset after ``bindings`` (and ``text`` alias)."""
    missing: List[str] = []
    for s in slots:
        if s.has_static_default:
            continue
        if s.key in bindings and bindings[s.key] is not None:
            continue
        if s.key == "user_input" and bindings.get("text") is not None:
            continue
        missing.append(s.key)
    return missing


def start_slots_for_api(slots: List[StartInputSlot]) -> List[Dict[str, Any]]:
    """Lightweight metadata for Workspace capability proposal UI."""
    return [
        {
            "key": s.key,
            "input_type": s.input_type,
            "required": not s.has_static_default,
        }
        for s in slots
    ]


def validate_bindings_against_slots(slots: List[StartInputSlot], bindings: Dict[str, Any]) -> Optional[str]:
    """Return an error message if required slots lack values after overrides, else None."""
    if not slots:
        return None
    allowed = valid_start_override_keys(slots)
    for k in bindings:
        if k not in allowed:
            return f"Unknown Start input key {k!r}; allowed: {sorted(allowed)}"
    for s in slots:
        if s.has_static_default:
            continue
        if s.key in bindings and bindings[s.key] is not None:
            continue
        if s.key == "user_input" and "text" in bindings and bindings["text"] is not None:
            continue
        return f"Missing value for required Start input {s.key!r}"
    return None


def validate_start_binding_shapes(slots: List[StartInputSlot], bindings: Dict[str, Any]) -> Optional[str]:
    """When a binding is present and not None, ensure JSON types match the Start slot type (executor-aligned)."""
    by_key = {s.key: s for s in slots}
    for key, val in bindings.items():
        if val is None:
            continue
        slot_key = "user_input" if key == "text" and "user_input" in by_key else key
        s = by_key.get(slot_key)
        if s is None:
            continue
        t = s.input_type
        if slot_key == "email_list" and isinstance(val, list):
            continue
        if t == "list" and not isinstance(val, list):
            return f"Start input {key!r} must be a JSON array"
        if t in ("dictionary", "structure", "gmail") and not isinstance(val, dict):
            return f"Start input {key!r} must be a JSON object"
        if t == "boolean" and not isinstance(val, bool):
            return f"Start input {key!r} must be a JSON boolean"
        if t == "int" and (not isinstance(val, int) or isinstance(val, bool)):
            return f"Start input {key!r} must be a JSON integer"
        if t == "datetime" and not isinstance(val, str):
            return f"Start input {key!r} must be an RFC3339 string"
        if t == "string" and not isinstance(val, str):
            return f"Start input {key!r} must be a string"
    return None


def validate_capability_start_bindings(slots: List[StartInputSlot], raw_bindings: Dict[str, Any]) -> Optional[str]:
    """Filter to allowed keys, then required-field and shape checks."""
    if not slots:
        return None
    filtered = filter_bindings_to_allowed(slots, raw_bindings)
    err = validate_bindings_against_slots(slots, filtered)
    if err:
        return err
    return validate_start_binding_shapes(slots, filtered)


def filter_bindings_to_allowed(slots: List[StartInputSlot], bindings: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys the Start node does not consume (avoids executor confusion)."""
    allowed = valid_start_override_keys(slots)
    return {k: v for k, v in bindings.items() if k in allowed}
