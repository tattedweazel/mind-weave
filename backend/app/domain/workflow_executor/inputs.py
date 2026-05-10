import json
from typing import AbstractSet, Any, Dict, List, Optional

from app.domain.schemas import (
    BooleanNodeOutput,
    DateTimeNodeOutput,
    DictionaryNodeOutput,
    DocumentNodeOutput,
    GmailNodeOutput,
    GraphEdge,
    IntNodeOutput,
    ListNodeOutput,
    NodeOutputUnion,
    ResponseNodeOutput,
    StartNodeOutput,
    StopNodeOutput,
    StringNodeOutput,
    StructureNodeOutput,
)
from app.domain.workflow_executor.aux_outputs import get_for_loop_summary
from app.domain.workflow_executor.gmail_llm_prompt import (
    format_gmail_message_dict_for_llm_prompt,
    is_gmail_like_message_dict,
)


def _get_slot_value(out: NodeOutputUnion, source_handle: Optional[str]) -> NodeOutputUnion:
    """
    For multi-slot outputs (StartNodeOutput), pick the slot by source_handle.
    For single-output nodes (including StructureNodeOutput, DocumentNodeOutput), return the full output.
    """
    if isinstance(out, StructureNodeOutput):
        return out
    if isinstance(out, DocumentNodeOutput):
        return out
    if isinstance(out, GmailNodeOutput):
        return out
    if not isinstance(out, StartNodeOutput):
        if source_handle == "summary":
            nid = getattr(out, "node_id", None)
            if isinstance(nid, str):
                blob = get_for_loop_summary(nid)
                if blob is None:
                    return DictionaryNodeOutput(
                        node_id=nid,
                        data={
                            "items_processed": 0,
                            "items_failed": 0,
                            "results": [],
                            "errors": [],
                        },
                    )
                return DictionaryNodeOutput(node_id=nid, data=blob)
        return out
    if not source_handle:
        # Legacy: use first string output or full output
        if out.outputs:
            first_val = next(iter(out.outputs.values()), None)
            if isinstance(first_val, str):
                return StringNodeOutput(node_id=out.node_id, text=first_val)
            if isinstance(first_val, list):
                return ListNodeOutput(node_id=out.node_id, data=first_val)
            if isinstance(first_val, GmailNodeOutput):
                return first_val
            if isinstance(first_val, dict):
                return DictionaryNodeOutput(node_id=out.node_id, data=first_val)
        return out
    val = out.outputs.get(source_handle)
    if val is None:
        return StringNodeOutput(node_id=out.node_id, text="")
    if isinstance(val, str):
        return StringNodeOutput(node_id=out.node_id, text=val)
    if isinstance(val, list):
        return ListNodeOutput(node_id=out.node_id, data=val)
    if isinstance(val, GmailNodeOutput):
        return val
    if isinstance(val, dict):
        return DictionaryNodeOutput(node_id=out.node_id, data=val)
    if isinstance(val, bool):
        return BooleanNodeOutput(node_id=out.node_id, value=val)
    if isinstance(val, int):
        return IntNodeOutput(node_id=out.node_id, value=val)
    return StringNodeOutput(node_id=out.node_id, text=str(val))


def _expected_type_for_key(node_required_inputs: List[Dict[str, Any]], key: str) -> Optional[str]:
    for item in node_required_inputs or []:
        if isinstance(item, dict) and item.get("key") == key:
            return item.get("type")
    return None


def _dict_is_multimodal_images_upstream(d: Any) -> bool:
    """
    True when ``d`` is a dict that ``multimodal_llm`` ``normalize_images_input`` can coerce:
    a flat artifact ref, or a ``capture_url_snapshot``-style object with an ``image`` field.
    """
    if not isinstance(d, dict):
        return False
    inner = d.get("image")
    if isinstance(inner, dict) and (inner.get("artifact_id") is not None or inner.get("id") is not None):
        return True
    if d.get("artifact_id") is not None or d.get("id") is not None:
        return True
    return False


def _plain_upstream_from_slot(
    slot: NodeOutputUnion, expected_type: Optional[str], *, input_key: Optional[str] = None
) -> Any:
    """Convert a wired slot to a plain value (same rules as ``_resolve_inputs_by_target_handle``)."""
    if expected_type == "any":
        return node_output_to_input_override_value(slot)
    if hasattr(slot, "schema_dict") and isinstance(slot, StructureNodeOutput):
        return slot.schema_dict
    if isinstance(slot, DocumentNodeOutput):
        if expected_type == "string":
            return slot.markdown or ""
        return {
            "id": slot.document_id,
            "name": slot.name,
            "description": slot.description,
            "body": slot.markdown,
        }
    if isinstance(slot, GmailNodeOutput):
        g = dict(slot.model_dump(mode="json", by_alias=True))
        if expected_type == "string":
            return format_gmail_message_dict_for_llm_prompt(g)
        return g
    if isinstance(slot, DateTimeNodeOutput):
        return slot.iso
    if hasattr(slot, "value") and isinstance(slot, (BooleanNodeOutput, IntNodeOutput)):
        return slot.value
    if hasattr(slot, "text"):
        return slot.text
    if hasattr(slot, "data"):
        # Multimodal `images` is declared as type "list" in required_inputs, but a single
        # DictionaryNodeOutput (Image primitive, or full capture_url_snapshot output) must
        # pass through as a plain dict for ``normalize_images_input`` — not ``json.dumps``.
        if input_key == "images" and isinstance(slot, DictionaryNodeOutput) and isinstance(slot.data, dict):
            d = slot.data
            if _dict_is_multimodal_images_upstream(d):
                return d
        if expected_type == "list" and isinstance(slot.data, list):
            return slot.data
        if expected_type == "dictionary" and isinstance(slot.data, dict):
            return slot.data
        if expected_type == "gmail" and isinstance(slot.data, dict):
            return dict(slot.data)
        if isinstance(slot.data, dict) and expected_type == "string" and is_gmail_like_message_dict(slot.data):
            return format_gmail_message_dict_for_llm_prompt(slot.data)
        return json.dumps(slot.data, indent=2) if isinstance(slot.data, (dict, list)) else str(slot.data)
    return str(slot)


def _slot_needs_implicit_wire(
    key: str,
    current: Any,
    overrides: Dict[str, Any],
    node_required_inputs: List[Dict[str, Any]],
    *,
    implicit_null_target_wire_string_keys: Optional[AbstractSet[str]] = None,
) -> bool:
    """True when this slot still has the 'no wire' default and can accept an implicit edge."""
    if overrides.get(key) is not None:
        return False
    t = _expected_type_for_key(node_required_inputs, key)
    if implicit_null_target_wire_string_keys and key in implicit_null_target_wire_string_keys and t == "string":
        return current in (None, "")
    if t in ("dictionary", "list"):
        return current in (None, "")
    if t in ("structure", "document", "gmail"):
        return current is None
    return False


def node_output_to_input_override_value(slot: NodeOutputUnion) -> Any:
    """
    Convert a wired upstream ``NodeOutputUnion`` into a plain Python value for ``input_overrides``.

    Must preserve list/dict/bool/int (not JSON strings) so sub-workflow **Start** slots receive the
    correct types when a **Workflow** node passes another node's output.
    """
    if isinstance(slot, StructureNodeOutput):
        return dict(slot.schema_dict) if slot.schema_dict else {}
    if isinstance(slot, DocumentNodeOutput):
        return {
            "id": slot.document_id,
            "name": slot.name,
            "description": slot.description,
            "body": slot.markdown,
        }
    if isinstance(slot, (BooleanNodeOutput, IntNodeOutput)):
        return slot.value
    if isinstance(slot, DateTimeNodeOutput):
        return slot.iso
    if isinstance(slot, GmailNodeOutput):
        return dict(slot.model_dump(mode="json", by_alias=True))
    if isinstance(slot, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        return slot.text
    if isinstance(slot, ListNodeOutput):
        return list(slot.data)
    if isinstance(slot, DictionaryNodeOutput):
        return dict(slot.data)
    return str(slot)


def _resolve_upstream_for_node(
    node_id: str,
    edges: List[GraphEdge],
    outputs: Dict[str, NodeOutputUnion],
) -> List[NodeOutputUnion]:
    """Build upstream list using handle-aware resolution. Skips trigger edges (control-flow only)."""
    result: List[NodeOutputUnion] = []
    for edge in edges:
        if edge.target != node_id:
            continue
        if edge.target_handle == "trigger":
            continue
        src = edge.source
        out = outputs.get(src)
        if out is None:
            continue
        slot_val = _get_slot_value(out, edge.source_handle)
        result.append(slot_val)
    return result


def _resolve_inputs_by_target_handle(
    node_id: str,
    required_keys: List[str],
    edges: List[GraphEdge],
    outputs: Dict[str, NodeOutputUnion],
    input_overrides: Dict[str, Any],
    node_required_inputs: List[Dict[str, Any]],
    *,
    implicit_null_target_wire_string_keys: Optional[AbstractSet[str]] = None,
) -> Dict[str, Any]:
    """
    Resolve input values for a node with multiple target handles.
    For each key: override > upstream (if wired) > node value.
    When an edge exists to a handle, upstream wins over the stored node value
    (e.g. Int wired to index overrides stored 0).

    ``implicit_null_target_wire_string_keys``: optional allow-list of ``required_keys``
    entries with ``type`` string that may bind edges whose ``target_handle`` is null/empty
    (second pass). Used by Upsert Document so ``content`` (and ``name``) wires survive
    legacy/malformed persisted graphs without handle ids.
    """
    result: Dict[str, Any] = {}
    overrides = input_overrides or {}
    node_values = {
        item["key"]: item.get("value")
        for item in (node_required_inputs or [])
        if isinstance(item, dict) and "key" in item
    }

    for key in required_keys:
        val = overrides.get(key)
        if val is not None:
            result[key] = val
            continue
        upstream_val: Any = None
        for edge in edges:
            if edge.target != node_id:
                continue
            # Match explicit target_handle, or treat None/empty as user_prompt for legacy edges
            if edge.target_handle != key and not (key == "user_prompt" and edge.target_handle in (None, "")):
                continue
            src = edge.source
            out = outputs.get(src)
            if out is None:
                continue
            slot = _get_slot_value(out, edge.source_handle)
            expected_type = _expected_type_for_key(node_required_inputs, key)
            upstream_val = _plain_upstream_from_slot(slot, expected_type, input_key=key)
            break
        if upstream_val is not None:
            result[key] = upstream_val
            continue
        val = node_values.get(key)
        if val is not None or (key in node_values and node_values[key] == ""):
            result[key] = val if val is not None else ""
            continue
        result[key] = None if key in ("structure", "document") else ""

    # Second pass: edges with null/empty target_handle never matched a named slot above.
    # Map them in graph order to structured slots (dictionary/list/structure/document) that
    # are still empty — fixes e.g. Sandbox is nearby8 cell_b when the saved graph has
    # target_handle null (UI may default display to cell_a only).
    missing_keys = [
        k
        for k in required_keys
        if _slot_needs_implicit_wire(
            k,
            result.get(k),
            overrides,
            node_required_inputs,
            implicit_null_target_wire_string_keys=implicit_null_target_wire_string_keys,
        )
    ]
    null_edges = [
        e
        for e in edges
        if e.target == node_id
        and (e.target_handle is None or e.target_handle == "")
        and (e.target_handle or "") != "trigger"
    ]
    if missing_keys and null_edges:
        for i, edge in enumerate(null_edges):
            if i >= len(missing_keys):
                break
            key = missing_keys[i]
            src = edge.source
            out = outputs.get(src)
            if out is None:
                continue
            slot = _get_slot_value(out, edge.source_handle)
            et = _expected_type_for_key(node_required_inputs, key)
            result[key] = _plain_upstream_from_slot(slot, et, input_key=key)

    return result
