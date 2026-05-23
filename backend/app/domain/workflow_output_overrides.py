"""Validate and build per-node output overrides for workflow runs."""

from __future__ import annotations

import uuid
from collections import deque
from typing import Any, Dict, Optional, Set

from sqlmodel import Session

from app.domain.schemas import (
    AddDaysUtilityNode,
    AddIntsUtilityNode,
    AddToListUtilityNode,
    AndControlNode,
    AppendValueToDocumentUtilityNode,
    AudioFileInputSkillNode,
    AudioNodeOutput,
    BasicConditionalControlNode,
    BetweenControlNode,
    BooleanNodeOutput,
    BooleanPrimitiveNode,
    CalendarListEventsSkillNode,
    GoogleDocsGetDocumentSkillNode,
    GoogleDocsParseDocumentUtilityNode,
    CaptureUrlSnapshotSkillNode,
    ConditionalNodeOutput,
    DateTimeNodeOutput,
    DateTimePrimitiveNode,
    DictionaryNodeOutput,
    DictionaryPrimitiveNode,
    DictionarySetValueByKeyUtilityNode,
    DictionaryValueByKeyUtilityNode,
    DivideIntsUtilityNode,
    DocumentNodeOutput,
    DocumentPrimitiveNode,
    FetchUrlSkillNode,
    ForLoopControlNode,
    ForLoopEndControlNode,
    GmailListMessagesSkillNode,
    GmailPrimitiveNode,
    GraphEdge,
    GtControlNode,
    GteControlNode,
    HtmlParseBasicUtilityNode,
    ImagePrimitiveNode,
    IntNodeOutput,
    IntPrimitiveNode,
    IntToStringUtilityNode,
    IsControlNode,
    IsEmptyControlNode,
    LenFromListUtilityNode,
    ListItemByIndexUtilityNode,
    ListNodeOutput,
    ListPrimitiveNode,
    ListToStringUtilityNode,
    LoadDocumentUtilityNode,
    LtControlNode,
    LteControlNode,
    MaxIntsUtilityNode,
    MessageUtilityNode,
    MinIntsUtilityNode,
    ModuloIntsUtilityNode,
    MultimodalLLMCallSkillNode,
    MultiplyIntsUtilityNode,
    NodeOutputUnion,
    NotControlNode,
    OrControlNode,
    ParseDocumentBodyUtilityNode,
    PrependTextUtilityNode,
    RandomItemFromListUtilityNode,
    ReadDocumentPropertyUtilityNode,
    ResponseNodeOutput,
    SandboxGetFacingUtilityNode,
    SandboxGetInventoryUtilityNode,
    SandboxGetNearbyUtilityNode,
    SandboxGetPositionUtilityNode,
    SandboxIdleUtilityNode,
    SandboxPickUpItemUtilityNode,
    SandboxPlaceItemUtilityNode,
    SandboxMoveForwardUtilityNode,
    SandboxTurnLeftUtilityNode,
    SandboxTurnRightUtilityNode,
    SimpleLLMCallSkillNode,
    StartGraphNode,
    StartNodeOutput,
    StopGraphNode,
    StopNodeOutput,
    StringNodeOutput,
    StringPrimitiveNode,
    StringToListUtilityNode,
    StringTruncUtilityNode,
    StructureNodeOutput,
    StructurePrimitiveNode,
    SubtractIntsUtilityNode,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
    TryCatchControlNode,
    UpsertDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    WorkflowRefNode,
    WriteObjectToDocumentBodyUtilityNode,
    XorControlNode,
    gmail_dict_to_node_output,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workflow_executor.graph import validate_for_loop_bodies
from app.domain.workflow_executor.helpers import parse_rfc3339_datetime_string
from app.domain.workflow_executor.parsing import _parse_node


# Lazy import to avoid circular dependency with executor.coerce_stop_output
def _coerce_stop_output(node_id: str, expected_type: str, out: NodeOutputUnion) -> NodeOutputUnion:
    from app.domain.workflow_executor.executor import coerce_stop_output

    return coerce_stop_output(node_id, expected_type, out)


def _stop_expected_type_from_graph(graph: dict[str, Any]) -> str:
    for n in graph.get("nodes") or []:
        if n.get("kind") == "stop":
            req = (n.get("data") or {}).get("required_outputs") or [{"key": "output", "type": "string"}]
            return (req[0] or {}).get("type", "string") if req else "string"
    return "string"


def _json_like_to_node_output(node_id: str, raw: Any) -> NodeOutputUnion:
    """Coerce JSON-like values to NodeOutputUnion (same idea as list item / Stop coercion)."""
    if isinstance(raw, str):
        return StringNodeOutput(node_id=node_id, text=raw)
    if isinstance(raw, list):
        return ListNodeOutput(node_id=node_id, data=raw)
    if isinstance(raw, dict):
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))
    if isinstance(raw, bool):
        return BooleanNodeOutput(node_id=node_id, value=raw)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return IntNodeOutput(node_id=node_id, value=int(raw))
    return StringNodeOutput(node_id=node_id, text=str(raw))


def _raw_to_intermediate_for_stop(raw: Any) -> NodeOutputUnion:
    if isinstance(raw, dict) and raw.get("kind") == "stop" and "text" in raw:
        return StopNodeOutput(node_id=str(raw.get("node_id", "")), text=str(raw.get("text", "")))
    return _json_like_to_node_output("", raw)


def coerce_raw_to_node_output(
    node_id: str,
    parsed: Any,
    raw: Any,
    *,
    child_stop_expected_type: Optional[str] = None,
) -> NodeOutputUnion:
    """Build typed NodeOutputUnion for a parsed graph node from a JSON override value."""
    if isinstance(parsed, StringPrimitiveNode):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: string primitive requires a JSON string")
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(parsed, ListPrimitiveNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: list primitive requires a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, DictionaryPrimitiveNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: dictionary primitive requires a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, BooleanPrimitiveNode):
        if not isinstance(raw, bool):
            raise ValueError(f"output_overrides[{node_id!r}]: boolean primitive requires a JSON boolean")
        return BooleanNodeOutput(node_id=node_id, value=raw)

    if isinstance(parsed, IntPrimitiveNode):
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"output_overrides[{node_id!r}]: int primitive requires a JSON integer")
        return IntNodeOutput(node_id=node_id, value=int(raw))

    if isinstance(parsed, DateTimePrimitiveNode):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: datetime primitive requires a JSON string")
        norm = parse_rfc3339_datetime_string(raw)
        if norm is None:
            raise ValueError(f"output_overrides[{node_id!r}]: datetime primitive requires a valid RFC3339 string")
        return DateTimeNodeOutput(node_id=node_id, iso=norm)

    if isinstance(parsed, StructurePrimitiveNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: structure primitive requires a JSON object")
        return StructureNodeOutput(node_id=node_id, schema_dict=dict(raw))

    if isinstance(parsed, DocumentPrimitiveNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: document primitive requires a JSON object")
        d = raw
        for k in ("document_id", "name", "description", "markdown"):
            if k not in d:
                raise ValueError(f"output_overrides[{node_id!r}]: document output missing {k!r}")
            if not isinstance(d[k], str):
                raise ValueError(f"output_overrides[{node_id!r}]: document field {k!r} must be a string")
        return DocumentNodeOutput(
            node_id=node_id,
            document_id=d["document_id"],
            name=d["name"],
            description=d["description"],
            markdown=d["markdown"],
        )

    if isinstance(parsed, ImagePrimitiveNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: image primitive requires a JSON object")
        d = raw
        for k in ("artifact_id", "mime_type", "width", "height"):
            if k not in d:
                raise ValueError(f"output_overrides[{node_id!r}]: image output missing {k!r}")
        if not isinstance(d["artifact_id"], str) or not isinstance(d["mime_type"], str):
            raise ValueError(f"output_overrides[{node_id!r}]: artifact_id and mime_type must be strings")
        if isinstance(d["width"], bool) or not isinstance(d["width"], int):
            raise ValueError(f"output_overrides[{node_id!r}]: width must be an integer")
        if isinstance(d["height"], bool) or not isinstance(d["height"], int):
            raise ValueError(f"output_overrides[{node_id!r}]: height must be an integer")
        return DictionaryNodeOutput(
            node_id=node_id,
            data={
                "artifact_id": d["artifact_id"],
                "mime_type": d["mime_type"],
                "width": int(d["width"]),
                "height": int(d["height"]),
            },
        )

    if isinstance(parsed, GmailPrimitiveNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Gmail primitive requires a JSON object")
        return gmail_dict_to_node_output(node_id, dict(raw))

    if isinstance(parsed, StartGraphNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: start node requires a JSON object")
        outputs = raw.get("outputs")
        if outputs is not None and not isinstance(outputs, dict):
            raise ValueError("start output_overrides: outputs must be an object")
        text = raw.get("text", "")
        if not isinstance(text, str):
            raise ValueError("start output_overrides: text must be a string")
        return StartNodeOutput(
            node_id=node_id,
            outputs=dict(outputs) if isinstance(outputs, dict) else {},
            text=text,
        )

    if isinstance(parsed, StopGraphNode):
        req = (parsed.data or {}).get("required_outputs") or [{"key": "output", "type": "string"}]
        expected_type = (req[0] or {}).get("type", "string") if req else "string"
        inter = _raw_to_intermediate_for_stop(raw)
        return _coerce_stop_output(node_id, str(expected_type), inter)

    if isinstance(parsed, SimpleLLMCallSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Simple LLM Call requires a JSON object")
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError("Simple LLM Call output_overrides: text must be a string")
        md = raw.get("metadata", {})
        if md is None:
            md = {}
        if not isinstance(md, dict):
            raise ValueError("Simple LLM Call output_overrides: metadata must be an object")
        return ResponseNodeOutput(node_id=node_id, text=text, metadata=dict(md))

    if isinstance(parsed, MultimodalLLMCallSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Multimodal LLM requires a JSON object")
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError("Multimodal LLM output_overrides: text must be a string")
        md = raw.get("metadata", {})
        if md is None:
            md = {}
        if not isinstance(md, dict):
            raise ValueError("Multimodal LLM output_overrides: metadata must be an object")
        return ResponseNodeOutput(node_id=node_id, text=text, metadata=dict(md))

    if isinstance(parsed, TextToSpeechSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Text-to-Speech requires a JSON object")
        if raw.get("kind") != "audio":
            raise ValueError("Text-to-Speech output_overrides: kind must be 'audio'")
        b64 = raw.get("audio_base64")
        if not isinstance(b64, str):
            raise ValueError("Text-to-Speech output_overrides: audio_base64 must be a string")
        mime = raw.get("mime_type", "audio/wav")
        if not isinstance(mime, str):
            raise ValueError("Text-to-Speech output_overrides: mime_type must be a string")
        return AudioNodeOutput(node_id=node_id, mime_type=mime, audio_base64=b64)

    if isinstance(parsed, TranscribeAudioSkillNode):
        if not isinstance(raw, str):
            raise ValueError(
                f"output_overrides[{node_id!r}]: Voice input (transcribe_audio) requires a JSON string (transcript)"
            )
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(parsed, AudioFileInputSkillNode):
        if not isinstance(raw, str):
            raise ValueError(
                f"output_overrides[{node_id!r}]: Audio File Input (audio_file_input) requires a JSON string (transcript)"
            )
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(parsed, TranscribeFileSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(
                f"output_overrides[{node_id!r}]: Transcribe File (transcribe_file) requires a JSON object "
                "(TranscriptPrimitive shape)"
            )
        # Validate the shape so a typo'd override doesn't surface deep in the graph.
        from app.domain.schemas.transcript import TranscriptPrimitive

        try:
            primitive = TranscriptPrimitive.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError or similar
            raise ValueError(
                f"output_overrides[{node_id!r}]: Transcribe File primitive failed validation: {exc}"
            ) from exc
        return DictionaryNodeOutput(node_id=node_id, data=primitive.model_dump(mode="json"))

    if isinstance(parsed, GmailListMessagesSkillNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: Gmail List Messages requires a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, CalendarListEventsSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: skill output must be a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, GoogleDocsGetDocumentSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Google Docs Get Document requires a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, GoogleDocsParseDocumentUtilityNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: Google Docs Parse Document requires a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, FetchUrlSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Fetch URL requires a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, CaptureUrlSnapshotSkillNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Capture URL snapshot requires a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(
        parsed,
        (
            ListToStringUtilityNode,
            IntToStringUtilityNode,
            PrependTextUtilityNode,
            StringTruncUtilityNode,
            MessageUtilityNode,
        ),
    ):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON string")
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(parsed, StringToListUtilityNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, LenFromListUtilityNode):
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON integer")
        return IntNodeOutput(node_id=node_id, value=int(raw))

    if isinstance(parsed, SandboxGetNearbyUtilityNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, SandboxGetFacingUtilityNode):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON string")
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(
        parsed,
        (
            SandboxGetPositionUtilityNode,
            SandboxMoveForwardUtilityNode,
            SandboxTurnLeftUtilityNode,
            SandboxTurnRightUtilityNode,
            SandboxIdleUtilityNode,
            SandboxPickUpItemUtilityNode,
            SandboxPlaceItemUtilityNode,
        ),
    ):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))
    if isinstance(parsed, SandboxGetInventoryUtilityNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, (ListItemByIndexUtilityNode, RandomItemFromListUtilityNode)):
        return _json_like_to_node_output(node_id, raw)

    if isinstance(parsed, DictionaryValueByKeyUtilityNode):
        raw_ovt = (parsed.data or {}).get("output_value_type")
        ovt = raw_ovt if isinstance(raw_ovt, str) else "list"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int"})
        if ovt not in allowed:
            raise ValueError(f"Dictionary value by key: invalid output_value_type on node {node_id!r}")
        if ovt == "string" and isinstance(raw, str):
            return StringNodeOutput(node_id=node_id, text=raw)
        if ovt == "list" and isinstance(raw, list):
            return ListNodeOutput(node_id=node_id, data=list(raw))
        if ovt == "dictionary" and isinstance(raw, dict):
            return DictionaryNodeOutput(node_id=node_id, data=dict(raw))
        if ovt == "boolean" and isinstance(raw, bool):
            return BooleanNodeOutput(node_id=node_id, value=raw)
        if ovt == "int" and isinstance(raw, int) and not isinstance(raw, bool):
            return IntNodeOutput(node_id=node_id, value=int(raw))
        raise ValueError(f"output_overrides[{node_id!r}]: value type does not match output_value_type={ovt!r}")

    if isinstance(parsed, DictionarySetValueByKeyUtilityNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, ReadDocumentPropertyUtilityNode):
        raw_ovt = (parsed.data or {}).get("output_value_type")
        ovt = raw_ovt if isinstance(raw_ovt, str) else "string"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int"})
        if ovt not in allowed:
            raise ValueError(f"Read document property: invalid output_value_type on node {node_id!r}")
        if ovt == "string" and isinstance(raw, str):
            return StringNodeOutput(node_id=node_id, text=raw)
        if ovt == "list" and isinstance(raw, list):
            return ListNodeOutput(node_id=node_id, data=list(raw))
        if ovt == "dictionary" and isinstance(raw, dict):
            return DictionaryNodeOutput(node_id=node_id, data=dict(raw))
        if ovt == "boolean" and isinstance(raw, bool):
            return BooleanNodeOutput(node_id=node_id, value=raw)
        if ovt == "int" and isinstance(raw, int) and not isinstance(raw, bool):
            return IntNodeOutput(node_id=node_id, value=int(raw))
        raise ValueError(f"output_overrides[{node_id!r}]: value type does not match output_value_type={ovt!r}")

    if isinstance(
        parsed,
        (
            AddIntsUtilityNode,
            SubtractIntsUtilityNode,
            MultiplyIntsUtilityNode,
            DivideIntsUtilityNode,
            ModuloIntsUtilityNode,
            MinIntsUtilityNode,
            MaxIntsUtilityNode,
        ),
    ):
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"output_overrides[{node_id!r}]: int utility requires a JSON integer")
        return IntNodeOutput(node_id=node_id, value=int(raw))

    if isinstance(parsed, AddDaysUtilityNode):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: add_days utility requires a JSON string (RFC3339)")
        norm = parse_rfc3339_datetime_string(raw)
        if norm is None:
            raise ValueError(f"output_overrides[{node_id!r}]: add_days utility requires a valid RFC3339 string")
        return DateTimeNodeOutput(node_id=node_id, iso=norm)

    if isinstance(parsed, BasicConditionalControlNode):
        if isinstance(raw, dict) and raw.get("branch") in ("true", "false"):
            return ConditionalNodeOutput(node_id=node_id, branch=raw["branch"])
        if isinstance(raw, dict) and raw.get("kind") == "conditional" and raw.get("branch") in ("true", "false"):
            return ConditionalNodeOutput(node_id=node_id, branch=raw["branch"])
        raise ValueError(f'output_overrides[{node_id!r}]: basic conditional requires {{"branch": "true"|"false"}}')

    if isinstance(parsed, BetweenControlNode):
        if isinstance(raw, dict) and raw.get("branch") in ("true", "false"):
            return ConditionalNodeOutput(node_id=node_id, branch=raw["branch"])
        raise ValueError(f"output_overrides[{node_id!r}]: between requires branch true/false")

    if isinstance(
        parsed,
        (IsControlNode, IsEmptyControlNode, GtControlNode, LtControlNode, GteControlNode, LteControlNode),
    ):
        if isinstance(raw, dict) and raw.get("branch") in ("true", "false"):
            return ConditionalNodeOutput(node_id=node_id, branch=raw["branch"])
        raise ValueError(f"output_overrides[{node_id!r}]: comparison control requires branch true/false")

    if isinstance(parsed, (AndControlNode, OrControlNode, XorControlNode, NotControlNode)):
        if not isinstance(raw, bool):
            raise ValueError(f"output_overrides[{node_id!r}]: boolean combinator requires a JSON boolean")
        return BooleanNodeOutput(node_id=node_id, value=raw)

    if isinstance(parsed, ForLoopControlNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: for loop requires a JSON array (list output)")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, TryCatchControlNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: Try/Catch requires a JSON object (envelope)")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, ForLoopEndControlNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: for loop end requires a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, AddToListUtilityNode):
        if not isinstance(raw, list):
            raise ValueError(f"output_overrides[{node_id!r}]: add to list requires a JSON array")
        return ListNodeOutput(node_id=node_id, data=list(raw))

    if isinstance(parsed, WorkflowRefNode):
        et = child_stop_expected_type or "string"
        inter = _raw_to_intermediate_for_stop(raw)
        return _coerce_stop_output(node_id, et, inter)

    if isinstance(parsed, LoadDocumentUtilityNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: load document requires a JSON object")
        d = raw
        for k in ("document_id", "name", "description", "markdown"):
            if k not in d or not isinstance(d[k], str):
                raise ValueError(f"output_overrides[{node_id!r}]: load document needs string fields including {k!r}")
        return DocumentNodeOutput(
            node_id=node_id,
            document_id=d["document_id"],
            name=d["name"],
            description=d["description"],
            markdown=d["markdown"],
        )

    if isinstance(
        parsed,
        (
            UpsertDocumentUtilityNode,
            ParseDocumentBodyUtilityNode,
            HtmlParseBasicUtilityNode,
            WriteObjectToDocumentBodyUtilityNode,
        ),
    ):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    if isinstance(parsed, AppendValueToDocumentUtilityNode):
        if not isinstance(raw, str):
            raise ValueError(f"output_overrides[{node_id!r}]: append value requires a JSON string")
        return StringNodeOutput(node_id=node_id, text=raw)

    if isinstance(parsed, ValidateAgainstStructureUtilityNode):
        if not isinstance(raw, dict):
            raise ValueError(f"output_overrides[{node_id!r}]: expected a JSON object")
        return DictionaryNodeOutput(node_id=node_id, data=dict(raw))

    raise ValueError(f"output_overrides: node {node_id!r} has unsupported type for output override")


def _edges_from_graph(graph: dict[str, Any]) -> list[GraphEdge]:
    return [GraphEdge(**e) for e in (graph.get("edges") or [])]


def _parse_nodes_by_id(graph: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_node in graph.get("nodes") or []:
        parsed = _parse_node(raw_node)
        if parsed is not None:
            out[parsed.id] = parsed
    return out


def _forbidden_loop_body_ids(graph: dict[str, Any]) -> set[str]:
    nodes_by_id = _parse_nodes_by_id(graph)
    edges = _edges_from_graph(graph)
    try:
        bodies = validate_for_loop_bodies(nodes_by_id, edges)
    except ValueError:
        return set()
    forbidden: set[str] = set()
    for _fid, bset in bodies.items():
        forbidden |= bset
    return forbidden


def _collect_referenced_graphs(
    session: Session, user_id: uuid.UUID, root_graph: dict[str, Any]
) -> list[dict[str, Any]]:
    """BFS over WorkflowRef nodes to collect nested graphs (for valid node ids)."""
    out: list[dict[str, Any]] = [root_graph]
    seen_wf: set[uuid.UUID] = set()
    queue: deque[dict[str, Any]] = deque([root_graph])
    svc = WorkflowDefinitionService(session, user_id)
    while queue:
        g = queue.popleft()
        for n in g.get("nodes") or []:
            if n.get("kind") != "workflow":
                continue
            wid_raw = (n.get("data") or {}).get("workflow_id")
            if not wid_raw:
                continue
            try:
                wid = uuid.UUID(str(wid_raw))
            except (ValueError, TypeError):
                continue
            if wid in seen_wf:
                continue
            wf = svc.get_workflow(wid)
            if not wf:
                continue
            seen_wf.add(wid)
            out.append(wf.graph)
            queue.append(wf.graph)
    return out


def validate_and_build_output_overrides(
    session: Session,
    user_id: uuid.UUID,
    root_graph: dict[str, Any],
    output_overrides: Optional[Dict[str, Any]],
) -> Dict[str, NodeOutputUnion]:
    """Validate keys and values; return node_id -> typed output for the executor."""
    if not output_overrides:
        return {}

    graphs = _collect_referenced_graphs(session, user_id, root_graph)
    node_to_parsed: dict[str, Any] = {}
    forbidden: set[str] = set()
    for g in graphs:
        fid = _forbidden_loop_body_ids(g)
        forbidden |= fid
        by_id = _parse_nodes_by_id(g)
        for nid, p in by_id.items():
            node_to_parsed[nid] = p

    result: Dict[str, NodeOutputUnion] = {}
    svc = WorkflowDefinitionService(session, user_id)

    for node_id, raw in output_overrides.items():
        if node_id not in node_to_parsed:
            raise ValueError(f"output_overrides: unknown node id {node_id!r}")
        if node_id in forbidden:
            raise ValueError(
                f"output_overrides: node {node_id!r} lies inside a for-loop body and cannot be overridden (v1)"
            )
        parsed = node_to_parsed[node_id]
        child_et: Optional[str] = None
        if isinstance(parsed, WorkflowRefNode):
            wid_raw = (parsed.data or {}).get("workflow_id")
            if wid_raw:
                try:
                    wid = uuid.UUID(str(wid_raw))
                    sub = svc.get_workflow(wid)
                    if sub:
                        child_et = _stop_expected_type_from_graph(sub.graph)
                except (ValueError, TypeError):
                    child_et = "string"
        out = coerce_raw_to_node_output(node_id, parsed, raw, child_stop_expected_type=child_et)
        result[node_id] = out

    return result


def filter_output_overrides_for_graph(
    graph: dict[str, Any], full: Dict[str, NodeOutputUnion]
) -> Dict[str, NodeOutputUnion]:
    """Restrict override map to node ids present in this graph."""
    ids: Set[str] = set()
    for n in graph.get("nodes") or []:
        i = n.get("id")
        if isinstance(i, str):
            ids.add(i)
    return {k: v for k, v in full.items() if k in ids}
