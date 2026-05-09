"""
Workflow Executor
=================
Runs a WorkflowDefinition DAG, producing a WorkflowRunResult.

Execution model:
  1. Validate the graph: detect cycles, verify all step_id references exist.
  2. Topologically sort nodes (Kahn's algorithm).
  3. Execute nodes in level-based (wave) batches:
       - Nodes whose dependencies are satisfied run concurrently via asyncio.gather, up to the
         per-user cap in User.settings max_concurrent_lm_studio_calls (default 3). The same cap
         batches parallel For Loop iterations when parallel_iterations is enabled (otherwise N
         iterations would all run at once and bypass the wave limit).
       - Value nodes resolve immediately (no LLM call).
       - Collection nodes gather all upstream outputs.
       - SimpleLLMCall skill nodes call the LLM with system_prompt and user_prompt.
  4. Parallel siblings (nodes sharing the same source) execute simultaneously,
     enabling concurrent LLM calls to LM Studio. A failing sibling is recorded
     but does not halt its peers (return_exceptions=True).
"""

import asyncio
import base64
import contextlib
import copy
import json
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional, Sequence, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.logging import logger
from app.core.run_log_redaction import redact_node_log_for_storage
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.domain.audio_file_validation import ValidatedAudioFile
from app.domain.document_json import deterministic_json_dumps
from app.domain.persona_lm_options import persona_lm_chat_options
from app.domain.sandbox.constants import DECISION_ACTION_STRINGS
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
    CaptureUrlSnapshotSkillNode,
    ConditionalNodeOutput,
    DateTimeNodeOutput,
    DateTimePrimitiveNode,
    DecisionActionPrimitiveNode,
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
    GmailNodeOutput,
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
    NodeRunResult,
    NotControlNode,
    OrControlNode,
    ParseDocumentBodyUtilityNode,
    PrependTextUtilityNode,
    RandomItemFromListUtilityNode,
    ReadDocumentPropertyUtilityNode,
    ResponseNodeOutput,
    SandboxAvailableCellsUtilityNode,
    SandboxBehaviorPrimitiveNode,
    SandboxClosestItemUtilityNode,
    SandboxDecisionIntentUtilityNode,
    SandboxDecisionMoveToUtilityNode,
    SandboxFilterItemsByTypeUtilityNode,
    SandboxFirstFoodWorldOrderUtilityNode,
    SandboxFirstNearbyFoodUtilityNode,
    SandboxIsNearby8UtilityNode,
    SandboxNearestItemByTypeUtilityNode,
    SandboxPetCellUtilityNode,
    SandboxPetEnergyUtilityNode,
    SandboxPetHungerUtilityNode,
    SandboxStarterDecisionUtilityNode,
    SandboxTickItemsUtilityNode,
    SandboxTickPetUtilityNode,
    SandboxTickPrimitiveNode,
    SandboxWorldGridUtilityNode,
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
    UpsertDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    WorkflowRefNode,
    WorkflowRunResult,
    WriteObjectToDocumentBodyUtilityNode,
    XorControlNode,
    gmail_dict_to_node_output,
)
from app.domain.schemas.sandbox import DecisionIntent, GridCell, SandboxTickInput
from app.domain.services.document_service import DocumentService
from app.domain.services.url_fetch_cache_service import get_cached_payload, upsert_success_cache
from app.domain.services.url_snapshot_cache_service import create_artifact, get_cache_artifact, upsert_cache
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.user_settings import resolve_max_concurrent_lm_studio_calls
from app.domain.workflow_executor.capture_url_snapshot_runtime import (
    build_success_output_from_artifact,
    perform_url_snapshot_capture,
    strip_internal_keys_for_output,
)
from app.domain.workflow_executor.capture_url_snapshot_runtime import (
    compute_cache_key as compute_snapshot_cache_key,
)
from app.domain.workflow_executor.html_parse_basic import parse_html_basic
from app.domain.workflow_executor.multimodal_llm_runtime import (
    MultimodalLLMInputError,
    build_openai_image_parts_from_artifacts,
    image_artifact_refs_for_log,
    normalize_images_input,
)
from app.domain.workflow_executor.schema_normalizer import normalize_schema_for_structured_output
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeUpload,
    TranscribeWaitKey,
    cancel_transcribe_wait,
    register_transcribe_wait,
)
from app.domain.workflow_output_overrides import filter_output_overrides_for_graph
from app.domain.workspace.workspace_google_graph import workflow_graph_with_default_google_connection
from app.integrations.gmail_query import (
    append_category_q_clauses,
    build_messages_list_q,
    coerce_bool_unread,
    normalize_gmail_exclude_categories,
    normalize_gmail_inbox_focus,
)
from app.integrations.google_workspace import (
    calendar_list_events,
    ensure_workflow_google_access_token,
    gmail_get_message_full,
    gmail_list_messages,
)
from app.persistence.tables import (
    AudioFileArtifact,
    Document,
    NodeRunLog,
    Persona,
    Structure,
    TtsModelArtifact,
    UrlSnapshotArtifact,
    User,
    VoiceSample,
    WorkflowDefinition,
    WorkflowRun,
)
from app.providers.lmstudio import LMStudioModelNotMultimodalError, LMStudioProvider
from app.providers.lmstudio_http import resolve_lmstudio_bearer
from app.providers.stt_bridge import SttBridgeError as SttBridgeHttpError
from app.providers.stt_bridge import transcribe_audio_bytes
from app.providers.transcription import (
    TranscriptionOptions,
    TranscriptionProviderError,
    enabled_provider_ids,
    get_speech_provider,
)
from app.providers.transcription.keys import resolve_assemblyai_api_key
from app.providers.tts_bridge import TtsBridgeError, synthesize_wav

from .diagnostics import (
    GMAIL_MESSAGE_BODY_MAX_CHARS,
    curated_gmail_message_from_full_api,
    curated_google_calendar_event,
    merge_skill_diagnostics,
    truncate_gmail_messages_list_response,
    truncate_google_calendar_events_list_response,
)
from .fetch_url_runtime import compute_cache_key, normalize_headers, perform_http_fetch
from .gmail_llm_prompt import (
    format_gmail_message_dict_for_llm_prompt,
    is_gmail_like_message_dict,
)
from .graph import (
    _build_in_degree_and_adjacency,
    _detect_cycle,
    _topological_order,
    edges_with_both_endpoints_in,
    for_loop_body_node_ids,
    main_schedule_node_ids,
    validate_for_loop_bodies,
    validate_for_loop_end_configuration,
    validate_parallel_for_loop_no_nested_loop,
)
from .helpers import (
    _condition_to_bool,
    _format_exception,
    _to_comparable,
    _values_equal,
    parse_rfc3339_datetime_string,
    parse_strict_int_for_slot,
    pop_wave_batch,
    shift_rfc3339_instant_by_days,
    split_batch_isolating_audio_steps,
    utc_now_rfc3339_normalized_for_executor,
)
from .inputs import (
    _get_slot_value,
    _resolve_inputs_by_target_handle,
    _resolve_upstream_for_node,
    node_output_to_input_override_value,
)
from .output_explorer import (
    attach_output_explorer_after_redact,
    merge_details_with_output_explorer,
)
from .parsing import _parse_node


def _sandbox_tick_dict_from_upstream(upstream: list[NodeOutputUnion]) -> dict | None:
    """Pick a dict-shaped ``SandboxTickInput`` from upstream node outputs."""
    for out in upstream:
        if isinstance(out, DictionaryNodeOutput):
            d = dict(out.data)
            if "world" in d and "pet" in d and "tick" in d:
                return d
        if isinstance(out, StartNodeOutput):
            st = out.outputs.get("sandbox_tick")
            if isinstance(st, dict):
                return st
    return None


def _paired_for_loop_end_id(for_loop_id: str, nodes_by_id: Dict[str, Any]) -> Optional[str]:
    for nid, n in nodes_by_id.items():
        if isinstance(n, ForLoopEndControlNode) and (n.data or {}).get("for_loop_id") == for_loop_id:
            return nid
    return None


def _node_output_to_json_dict(o: Any) -> Any:
    """Serialize a node output for ``resolved_inputs`` / run logs (JSON-friendly)."""
    md = getattr(o, "model_dump", None)
    if callable(md):
        return md(mode="json")
    return str(o)


def _resolved_inputs_value_for_log(v: Any) -> Any:
    """JSON-serialize one value for ``details.resolved_inputs`` (Run Logs / Last Run)."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {str(kk): _resolved_inputs_value_for_log(vv) for kk, vv in v.items()}
    if isinstance(v, list):
        return [_resolved_inputs_value_for_log(x) for x in v]
    md = getattr(v, "model_dump", None)
    if callable(md):
        return md(mode="json")
    return _node_output_to_json_dict(v)


def _resolved_inputs_dict_for_log(resolved: dict[str, Any]) -> dict[str, Any]:
    """Normalize a resolved-input map for run logs (JSON-friendly)."""
    return {str(k): _resolved_inputs_value_for_log(val) for k, val in resolved.items()}


def _error_with_resolved_inputs(error_msg: str, resolved: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured error with optional ``details.resolved_inputs`` for troubleshooting failed steps."""
    out: dict[str, Any] = {"status": "error", "error": error_msg}
    if resolved is not None:
        out["details"] = {"resolved_inputs": _resolved_inputs_dict_for_log(resolved)}
    return out


def _error_with_structured(
    error_msg: str,
    *,
    err_type: str,
    retryable: bool,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "structured_error": {"type": err_type, "message": error_msg, "retryable": retryable},
    }
    if resolved is not None:
        details["resolved_inputs"] = _resolved_inputs_dict_for_log(resolved)
    return {"status": "error", "error": error_msg, "details": details}


MESSAGE_UTILITY_MAX_LEN = 2048

STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS = 4096
STRING_TRUNC_RESOLVED_PREFIX_LEN = 200


def _string_trunc_resolved_inputs_payload(text: str, start_used: int, end_used: int, *, result: str) -> dict[str, Any]:
    n = len(text)
    out: dict[str, Any] = {
        "start_index": start_used,
        "end_index": end_used,
        "target_chars": n,
        "result_chars": len(result),
    }
    if n <= STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
        out["target_string"] = text
    else:
        out["target_truncated"] = True
        out["target_prefix"] = text[:STRING_TRUNC_RESOLVED_PREFIX_LEN]
    return out


def _string_trunc_error_resolved(resolved: dict[str, Any]) -> dict[str, Any]:
    """Omit or cap ``target_string`` in error snapshots for huge inputs."""
    raw_target = resolved.get("target_string")
    text = raw_target if isinstance(raw_target, str) else ("" if raw_target is None else str(raw_target))
    snap = {k: v for k, v in resolved.items() if k != "target_string"}
    n = len(text)
    snap["target_chars"] = n
    if n <= STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
        snap["target_string"] = text
    elif n:
        snap["target_truncated"] = True
        snap["target_prefix"] = text[:STRING_TRUNC_RESOLVED_PREFIX_LEN]
    return snap


def _coerce_message_display_text(raw: Any) -> str:
    """Best-effort string for Message utility display and ``details.user_message``."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, indent=2)
    return str(raw)


def _text_from_stringish_output(out: NodeOutputUnion) -> Optional[str]:
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        return out.text
    if isinstance(out, StartNodeOutput):
        return out.text
    return None


def _list_item_to_join_token(item: Any) -> str:
    """Stringify one list element for List-to-String join mode (prompt-friendly)."""
    if isinstance(item, str):
        return item
    try:
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(item)


def _json_text_to_fallback_string(out: NodeOutputUnion) -> str:
    """Best-effort string for ``StopNodeOutput`` when typed coercion fails."""
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        return out.text
    if isinstance(out, StartNodeOutput):
        return out.text
    if isinstance(out, (ListNodeOutput, DictionaryNodeOutput)):
        return json.dumps(out.data, indent=2)
    if isinstance(out, (BooleanNodeOutput, IntNodeOutput)):
        return str(out.value)
    if isinstance(out, DateTimeNodeOutput):
        return out.iso
    if isinstance(out, GmailNodeOutput):
        return json.dumps(out.model_dump(mode="json", by_alias=True), indent=2)
    if isinstance(out, AudioNodeOutput):
        return "[audio]"
    return str(out)


def coerce_stop_output(node_id: str, expected_type: str, out: NodeOutputUnion) -> NodeOutputUnion:
    """Return a typed node output matching Stop ``required_outputs[0].type`` for workflow chaining.

    Historically Stop always emitted ``StopNodeOutput`` with JSON/text, which broke List/Dict/boolean/int
    wiring into workflow refs and downstream nodes. When the expected type matches the upstream shape,
    pass through as ``ListNodeOutput`` / ``DictionaryNodeOutput`` / ``IntNodeOutput`` / ``BooleanNodeOutput``;
    string-like targets still use ``StopNodeOutput`` with ``text``.
    """
    et = (expected_type or "string").strip().lower() or "string"

    if et == "any":
        if isinstance(out, ListNodeOutput):
            return ListNodeOutput(node_id=node_id, data=list(out.data))
        if isinstance(out, DictionaryNodeOutput):
            return DictionaryNodeOutput(node_id=node_id, data=dict(out.data))
        if isinstance(out, BooleanNodeOutput):
            return BooleanNodeOutput(node_id=node_id, value=out.value)
        if isinstance(out, IntNodeOutput):
            return IntNodeOutput(node_id=node_id, value=int(out.value))
        if isinstance(out, DateTimeNodeOutput):
            return DateTimeNodeOutput(node_id=node_id, iso=out.iso)
        if isinstance(out, StructureNodeOutput):
            return StructureNodeOutput(node_id=node_id, schema_dict=dict(out.schema_dict))
        if isinstance(out, DocumentNodeOutput):
            return DocumentNodeOutput(
                node_id=node_id,
                document_id=out.document_id,
                name=out.name,
                description=out.description,
                markdown=out.markdown,
            )
        if isinstance(out, GmailNodeOutput):
            return gmail_dict_to_node_output(node_id, out.model_dump(mode="json", by_alias=True))
        if isinstance(out, AudioNodeOutput):
            return AudioNodeOutput(node_id=node_id, mime_type=out.mime_type, audio_base64=out.audio_base64)
        if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
            return StopNodeOutput(node_id=node_id, text=out.text)
        if isinstance(out, StartNodeOutput):
            return StopNodeOutput(node_id=node_id, text=out.text)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "list":
        if isinstance(out, ListNodeOutput):
            return ListNodeOutput(node_id=node_id, data=list(out.data))
        if isinstance(out, DictionaryNodeOutput):
            msgs = out.data.get("messages")
            if isinstance(msgs, list):
                return ListNodeOutput(node_id=node_id, data=list(msgs))
        t = _text_from_stringish_output(out)
        if t is not None:
            try:
                parsed = json.loads(t) if t.strip() else []
                if isinstance(parsed, dict) and isinstance(parsed.get("messages"), list):
                    return ListNodeOutput(node_id=node_id, data=list(parsed["messages"]))
                if not isinstance(parsed, list):
                    parsed = [parsed]
                return ListNodeOutput(node_id=node_id, data=parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "dictionary":
        if isinstance(out, DictionaryNodeOutput):
            return DictionaryNodeOutput(node_id=node_id, data=dict(out.data))
        t = _text_from_stringish_output(out)
        if t is not None:
            if not t.strip():
                # Empty string must not become {} — that breaks sandbox Stop (DecisionIntent) and hides wiring bugs.
                return StopNodeOutput(node_id=node_id, text=t)
            try:
                parsed = json.loads(t)
                if not isinstance(parsed, dict):
                    parsed = {}
                return DictionaryNodeOutput(node_id=node_id, data=parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "int":
        if isinstance(out, IntNodeOutput):
            return IntNodeOutput(node_id=node_id, value=int(out.value))
        t = _text_from_stringish_output(out)
        if t is not None:
            try:
                v = int(t.strip()) if t.strip() else 0
                return IntNodeOutput(node_id=node_id, value=v)
            except ValueError:
                return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "boolean":
        if isinstance(out, BooleanNodeOutput):
            return BooleanNodeOutput(node_id=node_id, value=out.value)
        ft = _json_text_to_fallback_string(out)
        val = (ft or "").strip().lower() in ("true", "yes", "1")
        return BooleanNodeOutput(node_id=node_id, value=val)

    if et == "structure":
        if isinstance(out, StructureNodeOutput):
            return StructureNodeOutput(node_id=node_id, schema_dict=dict(out.schema_dict))
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "document":
        if isinstance(out, DocumentNodeOutput):
            return DocumentNodeOutput(
                node_id=node_id,
                document_id=out.document_id,
                name=out.name,
                description=out.description,
                markdown=out.markdown,
            )
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "datetime":
        if isinstance(out, DateTimeNodeOutput):
            return DateTimeNodeOutput(node_id=node_id, iso=out.iso)
        t = _text_from_stringish_output(out)
        if t is not None:
            norm = parse_rfc3339_datetime_string(t)
            if norm is not None:
                return DateTimeNodeOutput(node_id=node_id, iso=norm)
            return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "gmail":
        if isinstance(out, GmailNodeOutput):
            return gmail_dict_to_node_output(node_id, out.model_dump(mode="json", by_alias=True))
        if isinstance(out, DictionaryNodeOutput):
            return gmail_dict_to_node_output(node_id, dict(out.data))
        t = _text_from_stringish_output(out)
        if t is not None and t.strip():
            try:
                parsed = json.loads(t)
                if isinstance(parsed, dict):
                    return gmail_dict_to_node_output(node_id, parsed)
            except (json.JSONDecodeError, TypeError):
                pass
            return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "audio":
        if isinstance(out, AudioNodeOutput):
            return AudioNodeOutput(node_id=node_id, mime_type=out.mime_type, audio_base64=out.audio_base64)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    # string (default): preserve text shell for LLM / text workflows
    final_text: str
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        final_text = out.text
    elif isinstance(out, StartNodeOutput):
        final_text = out.text
    elif isinstance(out, (ListNodeOutput, DictionaryNodeOutput)):
        final_text = json.dumps(out.data, indent=2)
    elif isinstance(out, (BooleanNodeOutput, IntNodeOutput)):
        final_text = str(out.value)
    elif isinstance(out, DateTimeNodeOutput):
        final_text = out.iso
    elif isinstance(out, GmailNodeOutput):
        final_text = json.dumps(out.model_dump(mode="json", by_alias=True), indent=2)
    elif isinstance(out, AudioNodeOutput):
        final_text = "[audio]"
    else:
        final_text = str(out)
    return StopNodeOutput(node_id=node_id, text=final_text)


class _StepRecorder:
    __slots__ = ("_n",)

    def __init__(self) -> None:
        self._n = 0

    def next_step(self) -> int:
        self._n += 1
        return self._n


def _effective_gmail_calendar_zone(
    user_settings: Optional[Dict[str, Any]],
    execution_time_zone: Optional[str],
) -> Optional[str]:
    """Prefer explicit profile IANA; else optional per-run client zone (for profile 'system')."""
    st = user_settings or {}
    pref = st.get("workflow_time_zone")
    if isinstance(pref, str):
        p = pref.strip()
        if p and p.casefold() != "system":
            return p
    ex = (execution_time_zone or "").strip()
    return ex if ex else None


_UPSERT_CONTENT_HANDLE_ALIASES = frozenset({"output", "text", "body", "markdown"})


def _normalize_edges_for_upsert_document(node_id: str, edges: List[GraphEdge]) -> List[GraphEdge]:
    """
    Map legacy/wrong ``target_handle`` values onto ``content`` so pass-1 resolution matches.
    Does not alter ``trigger`` or null/empty handles (implicit pass still applies).
    """
    out: List[GraphEdge] = []
    for e in edges:
        if e.target != node_id:
            out.append(e)
            continue
        th = (e.target_handle or "").strip()
        if th == "trigger" or th == "":
            out.append(e)
            continue
        if th in _UPSERT_CONTENT_HANDLE_ALIASES:
            out.append(e.model_copy(update={"target_handle": "content"}))
            continue
        out.append(e)
    return out


def _explorer_upsert_name_from_required_inputs(raw_inputs: Sequence[Dict[str, Any]]) -> str:
    for item in raw_inputs:
        if isinstance(item, dict) and item.get("key") == "name":
            v = item.get("value")
            if v is None:
                return ""
            return str(v).strip()
    return ""


def _upsert_content_resolved_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    return False


def _recover_upsert_miswired_body_into_content(
    node_id: str,
    edges: List[GraphEdge],
    resolved: Dict[str, Any],
    raw_inputs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Recover graphs where ``target_handle: "name"`` was persisted for what was intended as body text
    (null-handle default in older editor conversions). Explorer title wins; wired text moves to
    ``content`` when there is no explicit ``content`` edge.
    """
    if not _upsert_content_resolved_blank(resolved.get("content")):
        return resolved
    explorer_name = _explorer_upsert_name_from_required_inputs(raw_inputs)
    if not explorer_name:
        return resolved
    resolved_name = resolved.get("name")
    if resolved_name is None:
        return resolved
    rs = str(resolved_name).strip()
    if rs == explorer_name:
        return resolved
    has_content_edge = False
    has_name_edge = False
    for e in edges:
        if e.target != node_id:
            continue
        th = (e.target_handle or "").strip()
        if th == "trigger":
            continue
        if th == "content":
            has_content_edge = True
        if th == "name":
            has_name_edge = True
    if not has_name_edge or has_content_edge:
        return resolved
    out = dict(resolved)
    out["name"] = explorer_name
    out["content"] = resolved_name
    return out


def _decrement_signal_out_triggers(
    node_id: str,
    main_edges: List[GraphEdge],
    main_ids: set[str],
    in_degree: Dict[str, int],
    ready: deque[str],
) -> None:
    """After a branching control completes, schedule nodes connected via signal_out → trigger."""
    for edge in main_edges:
        if edge.source != node_id:
            continue
        if edge.source_handle != "signal_out":
            continue
        th = (edge.target_handle or "").strip()
        if th != "trigger":
            continue
        succ = edge.target
        if succ in main_ids:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)


class WorkflowExecutor:
    """Executes a WorkflowDefinition and returns a WorkflowRunResult."""

    def __init__(
        self,
        session: Session,
        user_id: uuid.UUID,
        default_google_workflow_connection_id: Optional[uuid.UUID] = None,
    ):
        self.session = session
        self.user_id = user_id
        self.default_google_workflow_connection_id = default_google_workflow_connection_id
        # Serialize ORM access: parallel waves run multiple nodes concurrently (asyncio.gather);
        # SQLAlchemy Session is not safe for concurrent use from overlapping asyncio tasks.
        # Simple LLM loads User/api_keys under this lock; httpx to LM Studio runs outside it.
        self._async_session_lock = asyncio.Lock()
        # Cleared at the start of each run / run_stream; then cached from User.settings.
        self._max_concurrent_wave_cap: Optional[int] = None
        self._interstitial_ndjson_lines: list[str] = []
        self._stream_interstitial_sink: Optional[list[str]] = None
        self._active_transcribe_wait_keys: set[TranscribeWaitKey] = set()

    @contextlib.contextmanager
    def _transcribe_stream_sink(self, stream_lines: Optional[list[str]]):
        """While in a For loop body, mirror interstitial NDJSON into the parent stream buffer."""
        prev = self._stream_interstitial_sink
        if stream_lines is not None:
            self._stream_interstitial_sink = stream_lines
        try:
            yield
        finally:
            self._stream_interstitial_sink = prev

    def _emit_interstitial(self, obj: Dict[str, Any]) -> None:
        line = json.dumps(obj) + "\n"
        self._interstitial_ndjson_lines.append(line)
        sink = self._stream_interstitial_sink
        if sink is not None:
            sink.append(line)

    def _track_transcribe_wait(self, key: TranscribeWaitKey) -> None:
        self._active_transcribe_wait_keys.add(key)

    def _untrack_transcribe_wait(self, key: TranscribeWaitKey) -> None:
        self._active_transcribe_wait_keys.discard(key)

    def _cancel_active_transcribe_waits(self) -> None:
        for key in list(self._active_transcribe_wait_keys):
            cancel_transcribe_wait(key)
        self._active_transcribe_wait_keys.clear()

    def _inject_google_into_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        """Return a shallow copy whose graph has workspace default Google ids injected (no-op if unset)."""
        if self.default_google_workflow_connection_id is None:
            return workflow
        adj = workflow_graph_with_default_google_connection(
            self.session,
            user_id=self.user_id,
            graph=workflow.graph,
            default_connection_id=self.default_google_workflow_connection_id,
        )
        wf = copy.copy(workflow)
        wf.graph = adj
        return wf

    def _wave_cap_for_run(self) -> int:
        if self._max_concurrent_wave_cap is not None:
            return self._max_concurrent_wave_cap
        u = self.session.get(User, self.user_id)
        self._max_concurrent_wave_cap = resolve_max_concurrent_lm_studio_calls(
            getattr(u, "settings", None) if u else None
        )
        return self._max_concurrent_wave_cap

    async def run(
        self,
        workflow: WorkflowDefinition,
        input_overrides: Optional[Dict[str, Any]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
    ) -> WorkflowRunResult:
        """
        Validate, sort, and execute the workflow graph.
        Returns a WorkflowRunResult regardless of whether individual nodes fail.
        Raises ValueError for structural errors (cycles, missing steps).
        execution_stack: workflow IDs currently being executed (for cycle detection in workflow nodes).
        """
        stack = execution_stack or frozenset()
        etz = (execution_time_zone or "").strip() or None
        workflow = self._inject_google_into_workflow(workflow)
        graph = workflow.graph
        raw_nodes: list[Dict[str, Any]] = graph.get("nodes", [])
        raw_edges: list[Dict[str, Any]] = graph.get("edges", [])

        # Parse nodes and edges.
        nodes_by_id: Dict[str, Any] = {}
        for raw_node in raw_nodes:
            parsed = _parse_node(raw_node)
            if parsed is not None:
                nodes_by_id[parsed.id] = parsed

        edges = [GraphEdge(**e) for e in raw_edges]

        # --- Validation: cycle detection ---
        cycle = _detect_cycle(list(nodes_by_id.keys()), edges)
        if cycle:
            raise ValueError(f"Workflow graph contains a cycle involving nodes: {cycle}")

        fl_bodies = validate_for_loop_bodies(nodes_by_id, edges)
        validate_for_loop_end_configuration(nodes_by_id, edges)
        validate_parallel_for_loop_no_nested_loop(nodes_by_id, edges)
        union_body: set[str] = set()
        for _fid, bset in fl_bodies.items():
            union_body |= bset
        main_ids = main_schedule_node_ids(set(nodes_by_id.keys()), union_body)
        main_edges = edges_with_both_endpoints_in(main_ids, edges)

        # --- Execution (level-based parallel, main schedule only) ---
        order = _topological_order(sorted(main_ids), main_edges)
        order_index = {nid: i for i, nid in enumerate(order)}
        in_degree, adjacency = _build_in_degree_and_adjacency(sorted(main_ids), main_edges, nodes_by_id)
        ready: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)

        outputs: Dict[str, NodeOutputUnion] = {}
        node_results: list[NodeRunResult] = []
        recorder = _StepRecorder()
        om = output_overrides_map or {}
        self._max_concurrent_wave_cap = None
        wave_cap = self._wave_cap_for_run()

        for _nid, _n in nodes_by_id.items():
            if isinstance(_n, TranscribeAudioSkillNode) and _nid not in om:
                raise ValueError(
                    "This workflow includes Voice input (transcribe_audio). Use the streaming Run from the "
                    "workflow editor, or provide an output override for that node."
                )
            if isinstance(_n, AudioFileInputSkillNode) and _nid not in om:
                data = _n.data or {}
                if not (isinstance(data.get("audio_artifact_id"), str) and data["audio_artifact_id"].strip()):
                    raise ValueError(
                        "This workflow includes Audio File Input without a saved file. Use the streaming Run from the "
                        "workflow editor, attach an audio file artifact to the node, or provide an output override."
                    )
            if isinstance(_n, TranscribeFileSkillNode) and _nid not in om:
                data = _n.data or {}
                if not (isinstance(data.get("audio_artifact_id"), str) and data["audio_artifact_id"].strip()):
                    raise ValueError(
                        "This workflow includes Transcribe File without a saved file. Use the streaming Run from the "
                        "workflow editor, attach an audio file artifact to the node, or provide an output override."
                    )

        while ready:
            batch = pop_wave_batch(ready, order_index, wave_cap)
            batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

            async def run_node(node_id: str):
                node = nodes_by_id[node_id]
                t0 = time.monotonic()
                if isinstance(node, ForLoopControlNode):
                    result = await self._run_for_loop_node(
                        node_id,
                        node,
                        edges,
                        outputs,
                        input_overrides,
                        workflow,
                        stack,
                        nodes_by_id,
                        recorder,
                        node_results,
                        execution_time_zone=etz,
                        output_overrides_map=om,
                    )
                elif isinstance(node, ForLoopEndControlNode):
                    result = self._resolve_for_loop_end_node(node_id, node, edges, outputs, output_overrides_map=om)
                else:
                    upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                    result = await self._execute_node(
                        node_id,
                        node,
                        upstream,
                        edges,
                        outputs,
                        input_overrides,
                        workflow=workflow,
                        execution_stack=stack,
                        execution_time_zone=etz,
                        output_overrides_map=om,
                        stream_run_id=None,
                        for_loop_id=None,
                        for_loop_iteration=None,
                    )
                elapsed_ms = (time.monotonic() - t0) * 1000
                return result, elapsed_ms

            gathered = await asyncio.gather(
                *[run_node(node_id) for node_id in batch],
                return_exceptions=True,
            )

            for node_id, raw in zip(batch, gathered):
                if isinstance(raw, BaseException):
                    result = {"status": "error", "error": _format_exception(raw)}
                    elapsed_ms = 0.0
                else:
                    result, elapsed_ms = cast(tuple[dict[str, Any], float], raw)

                out_for_result: Any = result.get("output")
                raw_output_result: dict[str, Any] | None = None
                if out_for_result is not None:
                    md_r = getattr(out_for_result, "model_dump", None)
                    if callable(md_r):
                        raw_output_result = md_r(mode="json")
                raw_det_result = cast(dict[str, Any], result.get("details") or {})
                details_for_client = merge_details_with_output_explorer(raw_det_result, raw_output_result)

                node_results.append(
                    NodeRunResult(
                        node_id=node_id,
                        status=result["status"],
                        output=result.get("output"),
                        error=result.get("error"),
                        latency_ms=round(elapsed_ms, 2),
                        details=details_for_client,
                        step_number=recorder.next_step(),
                    )
                )

                if result["status"] == "ok" and result.get("output"):
                    outputs[node_id] = cast(NodeOutputUnion, result["output"])

                node_exec: Any = nodes_by_id[node_id]
                output_val: Any = result.get("output")
                if isinstance(
                    node_exec,
                    (
                        BasicConditionalControlNode,
                        BetweenControlNode,
                        IsControlNode,
                        IsEmptyControlNode,
                        GtControlNode,
                        LtControlNode,
                        GteControlNode,
                        LteControlNode,
                    ),
                ) and isinstance(output_val, ConditionalNodeOutput):
                    for edge in main_edges:
                        if edge.source == node_id and edge.source_handle == output_val.branch:
                            succ = edge.target
                            if succ in main_ids:
                                in_degree[succ] -= 1
                                if in_degree[succ] == 0:
                                    ready.append(succ)
                    _decrement_signal_out_triggers(node_id, main_edges, main_ids, in_degree, ready)
                else:
                    for succ in adjacency.get(node_id, []):
                        in_degree[succ] -= 1
                        if in_degree[succ] == 0:
                            ready.append(succ)

        # Overall status: ok if all succeeded, partial if some failed, error if all failed.
        statuses = {r.status for r in node_results}
        if statuses == {"ok"}:
            overall = "ok"
        elif "ok" in statuses:
            overall = "partial"
        else:
            overall = "error"

        return WorkflowRunResult(
            workflow_id=workflow.id,
            status=overall,
            node_results=node_results,
        )

    async def run_stream(
        self,
        workflow: WorkflowDefinition,
        input_overrides: Optional[Dict[str, Any]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
    ):
        """
        Validate, sort, and execute the workflow graph while yielding NDJSON events.
        execution_stack: workflow IDs currently being executed (for cycle detection).
        """
        stack = execution_stack or frozenset()
        workflow = self._inject_google_into_workflow(workflow)
        graph = workflow.graph
        raw_nodes: list[Dict[str, Any]] = graph.get("nodes", [])
        raw_edges: list[Dict[str, Any]] = graph.get("edges", [])

        run_id = uuid.uuid4()
        run_record = WorkflowRun(
            id=run_id,
            workflow_id=workflow.id,
            started_by_user_id=self.user_id,
            status="running",
        )
        self.session.add(run_record)
        self.session.commit()
        self._interstitial_ndjson_lines = []
        self._active_transcribe_wait_keys.clear()
        _run_tasks: list[asyncio.Task[Any]] = []

        async def _cancel_run_tasks() -> None:
            pending_tasks = [task for task in _run_tasks if not task.done()]
            if not pending_tasks:
                return
            for task in pending_tasks:
                task.cancel()
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        def _persist_stream_error_status(reason: str) -> None:
            try:
                if (run_record.status or "") == "running":
                    run_record.status = "error"
                    self.session.commit()
            except Exception:
                logger.exception(
                    "run_stream failed to persist %s status for workflow %s run_id=%s",
                    reason,
                    workflow.id,
                    run_id,
                )

        yield json.dumps({"event": "start", "workflow_id": str(workflow.id), "run_id": str(run_id)}) + "\n"

        try:
            etz = (execution_time_zone or "").strip() or None

            # Parse nodes and edges.
            nodes_by_id: Dict[str, Any] = {}
            for raw_node in raw_nodes:
                parsed = _parse_node(raw_node)
                if parsed is not None:
                    nodes_by_id[parsed.id] = parsed

            edges = [GraphEdge(**e) for e in raw_edges]

            # --- Validation: cycle detection ---
            cycle = _detect_cycle(list(nodes_by_id.keys()), edges)
            if cycle:
                run_record.status = "error"
                self.session.commit()
                yield (
                    json.dumps({"event": "error", "error": f"Workflow graph contains a cycle involving nodes: {cycle}"})
                    + "\n"
                )
                return

            try:
                fl_bodies = validate_for_loop_bodies(nodes_by_id, edges)
                validate_for_loop_end_configuration(nodes_by_id, edges)
                validate_parallel_for_loop_no_nested_loop(nodes_by_id, edges)
            except ValueError as exc:
                run_record.status = "error"
                self.session.commit()
                yield json.dumps({"event": "error", "error": str(exc)}) + "\n"
                return

            union_body: set[str] = set()
            for _fid, bset in fl_bodies.items():
                union_body |= bset
            main_ids = main_schedule_node_ids(set(nodes_by_id.keys()), union_body)
            main_edges = edges_with_both_endpoints_in(main_ids, edges)

            # --- Execution (level-based parallel, main schedule only) ---
            order = _topological_order(sorted(main_ids), main_edges)
            order_index = {nid: i for i, nid in enumerate(order)}
            in_degree, adjacency = _build_in_degree_and_adjacency(sorted(main_ids), main_edges, nodes_by_id)
            ready: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)

            outputs: Dict[str, NodeOutputUnion] = {}
            node_results: list[NodeRunResult] = []
            recorder = _StepRecorder()
            om = output_overrides_map or {}
            self._max_concurrent_wave_cap = None
            wave_cap = self._wave_cap_for_run()

            while ready:
                batch = pop_wave_batch(ready, order_index, wave_cap)
                batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                for node_id in batch:
                    yield json.dumps({"event": "node_start", "node_id": node_id}) + "\n"

                async def run_node(node_id: str):
                    node = nodes_by_id[node_id]
                    t0 = time.monotonic()
                    stream_bucket: list[str] = []
                    if isinstance(node, ForLoopControlNode):
                        result = await self._run_for_loop_node(
                            node_id,
                            node,
                            edges,
                            outputs,
                            input_overrides,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            run_id,
                            stream_bucket,
                            execution_time_zone=etz,
                            output_overrides_map=om,
                        )
                    elif isinstance(node, ForLoopEndControlNode):
                        result = self._resolve_for_loop_end_node(node_id, node, edges, outputs, output_overrides_map=om)
                    else:
                        upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                        result = await self._execute_node(
                            node_id,
                            node,
                            upstream,
                            edges,
                            outputs,
                            input_overrides,
                            workflow=workflow,
                            execution_stack=stack,
                            execution_time_zone=etz,
                            output_overrides_map=om,
                            stream_run_id=run_id,
                            for_loop_id=None,
                            for_loop_iteration=None,
                        )
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return result, elapsed_ms, stream_bucket

                # Parallel batch (e.g. several LLM calls) may run for minutes with no further
                # yields here — nginx proxy_read_timeout and home-router NAT often default to
                # ~60s idle with no bytes. Emit keepalive NDJSON lines until all tasks finish.
                _run_tasks = [asyncio.create_task(run_node(node_id)) for node_id in batch]
                # Let batch tasks start so they can enqueue interstitials (e.g. input_required
                # for transcribe_audio) before the first asyncio.wait. Otherwise the parent
                # blocks in wait with an empty _interstitial_ndjson_lines and the client sees
                # no bytes until the first wait timeout (~25s) — looks like a hang with no
                # voice prompt.
                await asyncio.sleep(0)
                _pending: set[asyncio.Task[Any]] = set(_run_tasks)
                _keepalive_sec = 25.0
                while _pending:
                    while self._interstitial_ndjson_lines:
                        yield self._interstitial_ndjson_lines.pop(0)
                    _, _pending = await asyncio.wait(_pending, timeout=_keepalive_sec)
                    if _pending:
                        yield json.dumps({"event": "keepalive"}) + "\n"
                while self._interstitial_ndjson_lines:
                    yield self._interstitial_ndjson_lines.pop(0)
                gathered = []
                for _t in _run_tasks:
                    try:
                        gathered.append(_t.result())
                    except BaseException as _exc:
                        gathered.append(_exc)

                for node_id, raw in zip(batch, gathered):
                    stream_bucket: list[str] = []
                    if isinstance(raw, BaseException):
                        result = {"status": "error", "error": _format_exception(raw)}
                        elapsed_ms = 0.0
                    else:
                        result, elapsed_ms, stream_bucket = cast(tuple[dict[str, Any], float, list[str]], raw)

                    for line in stream_bucket:
                        yield line

                    out_for_log: Any = result.get("output")
                    raw_output: dict[str, Any] | None = None
                    if out_for_log is not None:
                        md = getattr(out_for_log, "model_dump", None)
                        if callable(md):
                            raw_output = md(mode="json")
                    raw_details: dict[str, Any] = cast(dict[str, Any], result.get("details") or {})
                    details_for_client = merge_details_with_output_explorer(raw_details, raw_output)

                    node_run_result = NodeRunResult(
                        node_id=node_id,
                        status=result["status"],
                        output=result.get("output"),
                        error=result.get("error"),
                        latency_ms=round(elapsed_ms, 2),
                        details=details_for_client,
                        step_number=recorder.next_step(),
                    )
                    node_results.append(node_run_result)

                    yield (
                        json.dumps(
                            {
                                "event": "node_end",
                                "node_id": node_id,
                                "result": node_run_result.model_dump(mode="json"),
                            }
                        )
                        + "\n"
                    )

                    safe_out, safe_det = redact_node_log_for_storage(raw_output, raw_details)
                    safe_det = attach_output_explorer_after_redact(safe_out, safe_det)
                    node_log = NodeRunLog(
                        run_id=run_id,
                        node_id=node_id,
                        step_number=node_run_result.step_number,
                        status=result["status"],
                        output_data=safe_out,
                        error=result.get("error"),
                        latency_ms=round(elapsed_ms, 2),
                        details=safe_det,
                    )
                    self.session.add(node_log)
                    self.session.commit()

                    if result["status"] == "ok" and result.get("output"):
                        outputs[node_id] = cast(NodeOutputUnion, result["output"])

                    node_exec: Any = nodes_by_id[node_id]
                    output_val: Any = result.get("output")
                    if isinstance(
                        node_exec,
                        (
                            BasicConditionalControlNode,
                            BetweenControlNode,
                            IsControlNode,
                            IsEmptyControlNode,
                            GtControlNode,
                            LtControlNode,
                            GteControlNode,
                            LteControlNode,
                        ),
                    ) and isinstance(output_val, ConditionalNodeOutput):
                        for edge in main_edges:
                            if edge.source == node_id and edge.source_handle == output_val.branch:
                                succ = edge.target
                                if succ in main_ids:
                                    in_degree[succ] -= 1
                                    if in_degree[succ] == 0:
                                        ready.append(succ)
                        _decrement_signal_out_triggers(node_id, main_edges, main_ids, in_degree, ready)
                    else:
                        for succ in adjacency.get(node_id, []):
                            in_degree[succ] -= 1
                            if in_degree[succ] == 0:
                                ready.append(succ)
                _run_tasks = []

            # Overall status
            statuses = {r.status for r in node_results}
            if statuses == {"ok"}:
                overall = "ok"
            elif "ok" in statuses:
                overall = "partial"
            else:
                overall = "error"

            final_result = WorkflowRunResult(
                workflow_id=workflow.id,
                status=overall,
                node_results=node_results,
            )

            run_record.status = overall
            self.session.commit()
            self._cancel_active_transcribe_waits()

            yield json.dumps({"event": "end", "result": final_result.model_dump(mode="json")}) + "\n"
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("run_stream cancelled for workflow %s run_id=%s", workflow.id, run_id)
            await _cancel_run_tasks()
            self._cancel_active_transcribe_waits()
            _persist_stream_error_status("cancelled")
            raise
        except Exception as exc:
            logger.exception("run_stream failed for workflow %s run_id=%s", workflow.id, run_id)
            await _cancel_run_tasks()
            self._cancel_active_transcribe_waits()
            _persist_stream_error_status("error")
            yield json.dumps({"event": "error", "error": _format_exception(exc)}) + "\n"

    def _coerce_list_value_for_for_loop(self, raw: Any) -> List[Any]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            return list(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return []

    def _resolve_for_loop_list(
        self,
        node: ForLoopControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> List[Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input", "type": "list", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        data = resolved.get("input")
        return self._coerce_list_value_for_for_loop(data)

    def _item_json_to_node_output(self, node_id: str, item: Any) -> NodeOutputUnion:
        if isinstance(item, str):
            return StringNodeOutput(node_id=node_id, text=item)
        if isinstance(item, list):
            return ListNodeOutput(node_id=node_id, data=item)
        if isinstance(item, dict):
            return DictionaryNodeOutput(node_id=node_id, data=item)
        if isinstance(item, int):
            return IntNodeOutput(node_id=node_id, value=item)
        if isinstance(item, bool):
            return BooleanNodeOutput(node_id=node_id, value=item)
        return StringNodeOutput(node_id=node_id, text=str(item))

    @staticmethod
    def _for_loop_parallel_iterations(node: ForLoopControlNode) -> bool:
        return (node.data or {}).get("parallel_iterations") is True

    @staticmethod
    def _fork_outputs_for_loop_iteration(
        baseline: Dict[str, NodeOutputUnion],
        body_ids: set[str],
        node_id: str,
        item_out: NodeOutputUnion,
    ) -> Dict[str, NodeOutputUnion]:
        out: Dict[str, NodeOutputUnion] = {}
        for k, v in baseline.items():
            if k in body_ids or k == node_id:
                continue
            out[k] = v
        out[node_id] = item_out
        return out

    @staticmethod
    def _patch_last_for_loop_body_node_result(
        node_results: list[NodeRunResult],
        *,
        node_id: str,
        body_node_id: str,
        merged_output: NodeOutputUnion,
    ) -> None:
        """After parallel For Loop iterations, align the last body node run with merged output (sequential parity)."""
        matches = [
            i
            for i, r in enumerate(node_results)
            if r.node_id == body_node_id and (r.details or {}).get("for_loop_node_id") == node_id
        ]
        if not matches:
            return
        last_i = max(
            matches,
            key=lambda i: float(sn) if (sn := node_results[i].step_number) is not None else float("-inf"),
        )
        prev = node_results[last_i]
        node_results[last_i] = NodeRunResult(
            node_id=prev.node_id,
            status=prev.status,
            output=merged_output,
            error=prev.error,
            latency_ms=prev.latency_ms,
            details=prev.details,
            step_number=prev.step_number,
        )

    async def _run_loop_body_waves(
        self,
        for_loop_id: str,
        body_ids: set[str],
        iteration_index: int,
        edges: List[GraphEdge],
        nodes_by_id: Dict[str, Any],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        recorder: _StepRecorder,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_lines: Optional[list[str]] = None,
        execution_time_zone: Optional[str] = None,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
    ) -> None:
        with self._transcribe_stream_sink(stream_lines):
            plock = parallel_side_effects_lock
            inner_edges = [e for e in edges if e.source in body_ids and e.target in body_ids]
            in_degree, adjacency = _build_in_degree_and_adjacency(sorted(body_ids), inner_edges, nodes_by_id)
            fl_counts: Dict[str, int] = {}
            for e in edges:
                if e.source == for_loop_id and e.target in body_ids:
                    fl_counts[e.target] = fl_counts.get(e.target, 0) + 1
            for _t, c in fl_counts.items():
                in_degree[_t] += c
            for _t, c in fl_counts.items():
                in_degree[_t] -= c

            ready: deque[str] = deque(nid for nid in body_ids if in_degree[nid] == 0)
            order = _topological_order(sorted(body_ids), inner_edges)
            order_index = {nid: i for i, nid in enumerate(order)}
            ov = input_overrides or {}
            om = output_overrides_map or {}
            wave_cap = self._wave_cap_for_run()

            while ready:
                batch = pop_wave_batch(ready, order_index, wave_cap)
                batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                if stream_lines is not None:
                    with contextlib.nullcontext() if plock is None else plock:
                        for nid in batch:
                            stream_lines.append(json.dumps({"event": "node_start", "node_id": nid}) + "\n")

                async def run_body_node(node_id: str):
                    node = nodes_by_id[node_id]
                    t0 = time.monotonic()
                    if isinstance(node, ForLoopControlNode):
                        r = await self._run_for_loop_node(
                            node_id,
                            node,
                            edges,
                            outputs,
                            ov,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            stream_run_id,
                            stream_lines,
                            execution_time_zone=execution_time_zone,
                            output_overrides_map=om,
                            parallel_side_effects_lock=plock,
                        )
                    else:
                        upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                        r = await self._execute_node(
                            node_id,
                            node,
                            upstream,
                            edges,
                            outputs,
                            ov,
                            workflow=workflow,
                            execution_stack=stack,
                            execution_time_zone=execution_time_zone,
                            loop_list_carry=loop_list_carry,
                            for_loop_id=for_loop_id,
                            output_overrides_map=om,
                            stream_run_id=stream_run_id,
                            for_loop_iteration=iteration_index,
                        )
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return r, elapsed_ms

                gathered = await asyncio.gather(
                    *[run_body_node(nid) for nid in batch],
                    return_exceptions=True,
                )

                for node_id, raw in zip(batch, gathered):
                    if isinstance(raw, BaseException):
                        result = {"status": "error", "error": _format_exception(raw)}
                        elapsed_ms = 0.0
                    else:
                        result, elapsed_ms = cast(tuple[dict[str, Any], float], raw)

                    det_raw: Any = result.get("details") or {}
                    det: dict[str, Any] = dict(det_raw if isinstance(det_raw, dict) else {})
                    det["for_loop_node_id"] = for_loop_id
                    det["for_loop_iteration"] = iteration_index

                    out_for_log_fl: Any = result.get("output")
                    raw_output_fl: dict[str, Any] | None = None
                    if out_for_log_fl is not None:
                        md_fl = getattr(out_for_log_fl, "model_dump", None)
                        if callable(md_fl):
                            raw_output_fl = md_fl(mode="json")
                    details_for_client_fl = merge_details_with_output_explorer(det, raw_output_fl)

                    with contextlib.nullcontext() if plock is None else plock:
                        node_run_result = NodeRunResult(
                            node_id=node_id,
                            status=result["status"],
                            output=result.get("output"),
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=details_for_client_fl,
                            step_number=recorder.next_step(),
                        )
                        node_results.append(node_run_result)

                        if stream_lines is not None:
                            stream_lines.append(
                                json.dumps(
                                    {
                                        "event": "node_end",
                                        "node_id": node_id,
                                        "result": node_run_result.model_dump(mode="json"),
                                    }
                                )
                                + "\n"
                            )

                        if stream_run_id is not None:
                            safe_out, safe_det = redact_node_log_for_storage(raw_output_fl, cast(dict[str, Any], det))
                            safe_det = attach_output_explorer_after_redact(safe_out, safe_det)
                            self.session.add(
                                NodeRunLog(
                                    run_id=stream_run_id,
                                    node_id=node_id,
                                    step_number=node_run_result.step_number,
                                    status=result["status"],
                                    output_data=safe_out,
                                    error=result.get("error"),
                                    latency_ms=round(elapsed_ms, 2),
                                    details=safe_det,
                                )
                            )
                            self.session.commit()

                    if result["status"] == "ok" and result.get("output"):
                        outputs[node_id] = cast(NodeOutputUnion, result["output"])

                    node_exec: Any = nodes_by_id[node_id]
                    output_val: Any = result.get("output")
                    if isinstance(
                        node_exec,
                        (
                            BasicConditionalControlNode,
                            BetweenControlNode,
                            IsControlNode,
                            IsEmptyControlNode,
                            GtControlNode,
                            LtControlNode,
                            GteControlNode,
                            LteControlNode,
                        ),
                    ) and isinstance(output_val, ConditionalNodeOutput):
                        for edge in inner_edges:
                            if edge.source == node_id and edge.source_handle == output_val.branch:
                                succ = edge.target
                                if succ in body_ids:
                                    in_degree[succ] -= 1
                                    if in_degree[succ] == 0:
                                        ready.append(succ)
                        _decrement_signal_out_triggers(node_id, inner_edges, body_ids, in_degree, ready)
                    else:
                        for succ in adjacency.get(node_id, []):
                            if succ not in body_ids:
                                continue
                            in_degree[succ] -= 1
                            if in_degree[succ] == 0:
                                ready.append(succ)

    async def _run_for_loop_node(
        self,
        node_id: str,
        node: ForLoopControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        nodes_by_id: Dict[str, Any],
        recorder: _StepRecorder,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_lines: Optional[list[str]] = None,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
    ) -> Dict[str, Any]:
        _ = stream_run_id
        ov = input_overrides or {}
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            outputs[node_id] = forced
            return {
                "status": "ok",
                "output": forced,
                "details": {"resolved_inputs": {}, "forced_output": True},
            }
        body_ids = for_loop_body_node_ids(node_id, edges, nodes_by_id)
        items = self._resolve_for_loop_list(node, edges, outputs, ov)
        end_nid = _paired_for_loop_end_id(node_id, nodes_by_id)
        if end_nid and end_nid in om:
            items = []
        if not items:
            outputs[node_id] = ListNodeOutput(node_id=node_id, data=[])
            return {
                "status": "ok",
                "output": ListNodeOutput(node_id=node_id, data=[]),
                "details": {"resolved_inputs": {"input_list": [], "iteration_count": 0}},
            }

        if self._for_loop_parallel_iterations(node):
            baseline: Dict[str, NodeOutputUnion] = {
                k: v for k, v in outputs.items() if k not in body_ids and k != node_id
            }
            iter_lock = threading.Lock()
            last_out_item = self._item_json_to_node_output(node_id, items[-1])

            async def run_one_iteration(
                i: int, raw_item: Any
            ) -> tuple[int, Dict[str, NodeOutputUnion], Dict[tuple[str, str], list[Any]]]:
                item_out = self._item_json_to_node_output(node_id, raw_item)
                scratch = self._fork_outputs_for_loop_iteration(baseline, body_ids, node_id, item_out)
                carry: Dict[tuple[str, str], list[Any]] = {}
                await self._run_loop_body_waves(
                    node_id,
                    body_ids,
                    i,
                    edges,
                    nodes_by_id,
                    scratch,
                    ov,
                    workflow,
                    stack,
                    recorder,
                    node_results,
                    stream_run_id,
                    stream_lines,
                    execution_time_zone=execution_time_zone,
                    loop_list_carry=carry,
                    output_overrides_map=om,
                    parallel_side_effects_lock=iter_lock,
                )
                return i, scratch, carry

            # Respect User.settings max_concurrent_lm_studio_calls: do not run every iteration at once,
            # or N iterations each doing LLM work would bypass the main graph wave cap.
            iter_concurrency = self._wave_cap_for_run()
            gathered_chunks: list[Any] = []
            for chunk_start in range(0, len(items), iter_concurrency):
                chunk_end = min(chunk_start + iter_concurrency, len(items))
                chunk = await asyncio.gather(
                    *[run_one_iteration(i, items[i]) for i in range(chunk_start, chunk_end)],
                    return_exceptions=True,
                )
                gathered_chunks.extend(chunk)
            for g in gathered_chunks:
                if isinstance(g, BaseException):
                    raise g

            ordered = sorted(
                cast(list[tuple[int, Dict[str, NodeOutputUnion], Dict[tuple[str, str], list[Any]]]], gathered_chunks),
                key=lambda t: t[0],
            )
            merged_carry: Dict[tuple[str, str], list[Any]] = {}
            for _i, _scratch, carry in ordered:
                for ck, lst in carry.items():
                    merged_carry.setdefault(ck, []).extend(lst)

            for bid in body_ids:
                bn = nodes_by_id.get(bid)
                if isinstance(bn, AddToListUtilityNode):
                    ck = (node_id, bid)
                    lst = list(merged_carry.get(ck, []))
                    merged_out = ListNodeOutput(node_id=bid, data=lst)
                    outputs[bid] = merged_out
                    self._patch_last_for_loop_body_node_result(
                        node_results,
                        node_id=node_id,
                        body_node_id=bid,
                        merged_output=merged_out,
                    )

            scratch_last = ordered[-1][1]
            for bid in body_ids:
                if isinstance(nodes_by_id.get(bid), AddToListUtilityNode):
                    continue
                if bid in scratch_last:
                    outputs[bid] = scratch_last[bid]

            outputs[node_id] = last_out_item
            return {
                "status": "ok",
                "output": last_out_item,
                "details": {"resolved_inputs": {"input_list": items, "iteration_count": len(items)}},
            }

        last_out: NodeOutputUnion = ListNodeOutput(node_id=node_id, data=[])
        loop_list_carry: Dict[tuple[str, str], list[Any]] = {}
        for i, raw_item in enumerate(items):
            item_out = self._item_json_to_node_output(node_id, raw_item)
            outputs[node_id] = item_out
            last_out = item_out
            for bid in body_ids:
                outputs.pop(bid, None)
            await self._run_loop_body_waves(
                node_id,
                body_ids,
                i,
                edges,
                nodes_by_id,
                outputs,
                ov,
                workflow,
                stack,
                recorder,
                node_results,
                stream_run_id,
                stream_lines,
                execution_time_zone=execution_time_zone,
                loop_list_carry=loop_list_carry,
                output_overrides_map=om,
                parallel_side_effects_lock=parallel_side_effects_lock,
            )

        # Finalize Add to List outputs from carry so For Loop End and downstream can read
        # even when the last iteration did not execute a given Add to List node.
        for bid in body_ids:
            bn = nodes_by_id.get(bid)
            if isinstance(bn, AddToListUtilityNode):
                ck = (node_id, bid)
                lst = list(loop_list_carry.get(ck, []))
                outputs[bid] = ListNodeOutput(node_id=bid, data=lst)

        outputs[node_id] = last_out
        return {
            "status": "ok",
            "output": last_out,
            "details": {"resolved_inputs": {"input_list": items, "iteration_count": len(items)}},
        }

    def _resolve_for_loop_end_node(
        self,
        node_id: str,
        node: ForLoopEndControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        *,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
    ) -> Dict[str, Any]:
        """Aggregate named exports from the paired For Loop body into one dictionary output."""
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            return {
                "status": "ok",
                "output": forced,
                "details": {
                    "resolved_inputs": {
                        "exports": dict(forced.data) if isinstance(forced, DictionaryNodeOutput) else {}
                    },
                    "forced_output": True,
                },
            }
        export_edges = [e for e in edges if e.target == node_id and (e.target_handle or "") != "trigger"]
        data: dict[str, Any] = {}
        for e in sorted(export_edges, key=lambda x: (x.target_handle or "", x.source)):
            key = (e.target_handle or "").strip()
            out = outputs.get(e.source)
            if out is None:
                data[key] = None
            else:
                slot = _get_slot_value(out, e.source_handle)
                data[key] = node_output_to_input_override_value(slot)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=data),
            "details": {"resolved_inputs": {"exports": data}},
        }

    async def _execute_node(
        self,
        node_id: str,
        node: Any,
        upstream: list[NodeOutputUnion],
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]] = None,
        workflow: Optional[WorkflowDefinition] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]] = None,
        for_loop_id: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        stream_run_id: Optional[uuid.UUID] = None,
        for_loop_iteration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch to the correct handler based on node kind."""
        overrides = input_overrides or {}
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            return {
                "status": "ok",
                "output": forced,
                "details": {"resolved_inputs": {}, "forced_output": True},
            }
        stack = execution_stack or frozenset()
        try:
            if isinstance(node, DecisionActionPrimitiveNode):
                return self._resolve_decision_action_primitive_node(node, upstream)
            if isinstance(node, SandboxTickPrimitiveNode):
                return self._resolve_sandbox_tick_primitive_node(node, upstream, overrides)
            if isinstance(node, StringPrimitiveNode):
                return self._resolve_string_primitive_node(node, upstream)
            if isinstance(node, ListPrimitiveNode):
                return self._resolve_list_primitive_node(node, upstream)
            if isinstance(node, DictionaryPrimitiveNode):
                return self._resolve_dictionary_primitive_node(node, edges, outputs)
            if isinstance(node, BooleanPrimitiveNode):
                return self._resolve_boolean_primitive_node(node, upstream)
            if isinstance(node, IntPrimitiveNode):
                return self._resolve_int_primitive_node(node, upstream)
            if isinstance(node, DateTimePrimitiveNode):
                return self._resolve_datetime_primitive_node(node, upstream)
            if isinstance(node, StructurePrimitiveNode):
                return self._resolve_structure_primitive_node(node)
            if isinstance(node, DocumentPrimitiveNode):
                return self._resolve_document_primitive_node(node)
            if isinstance(node, ImagePrimitiveNode):
                return self._resolve_image_primitive_node(node, edges, outputs, overrides)
            if isinstance(node, GmailPrimitiveNode):
                return self._resolve_gmail_primitive_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxBehaviorPrimitiveNode):
                return self._resolve_sandbox_behavior_primitive_node(node, upstream)
            if isinstance(node, StartGraphNode):
                return self._resolve_start_node(node, overrides)
            if isinstance(node, StopGraphNode):
                return self._resolve_stop_node(node, upstream)
            if isinstance(node, SimpleLLMCallSkillNode):
                return await self._run_simple_llm_call_node(node, edges, outputs, overrides)
            if isinstance(node, MultimodalLLMCallSkillNode):
                return await self._run_multimodal_llm_call_node(node, edges, outputs, overrides)
            if isinstance(node, TextToSpeechSkillNode):
                return await self._run_text_to_speech_node(node, edges, outputs, overrides)
            if isinstance(node, TranscribeAudioSkillNode):
                return await self._run_transcribe_audio_node(
                    node,
                    node_id,
                    stream_run_id=stream_run_id,
                    for_loop_id=for_loop_id,
                    for_loop_iteration=for_loop_iteration,
                )
            if isinstance(node, AudioFileInputSkillNode):
                return await self._run_audio_file_input_node(
                    node,
                    node_id,
                    stream_run_id=stream_run_id,
                    for_loop_id=for_loop_id,
                    for_loop_iteration=for_loop_iteration,
                )
            if isinstance(node, TranscribeFileSkillNode):
                return await self._run_transcribe_file_node(
                    node,
                    node_id,
                    stream_run_id=stream_run_id,
                    for_loop_id=for_loop_id,
                    for_loop_iteration=for_loop_iteration,
                )
            if isinstance(node, GmailListMessagesSkillNode):
                return await self._run_gmail_list_messages_node(
                    node, edges, outputs, overrides, execution_time_zone=execution_time_zone
                )
            if isinstance(node, CalendarListEventsSkillNode):
                return await self._run_calendar_list_events_node(node, edges, outputs, overrides)
            if isinstance(node, FetchUrlSkillNode):
                return await self._run_fetch_url_node(node, edges, outputs, overrides)
            if isinstance(node, CaptureUrlSnapshotSkillNode):
                return await self._run_capture_url_snapshot_node(node, edges, outputs, overrides)
            if isinstance(node, ListToStringUtilityNode):
                return self._resolve_list_to_string_node(node, upstream)
            if isinstance(node, StringToListUtilityNode):
                return self._resolve_string_to_list_node(node, upstream)
            if isinstance(node, IntToStringUtilityNode):
                return self._resolve_int_to_string_node(node, upstream)
            if isinstance(node, LenFromListUtilityNode):
                return self._resolve_len_from_list_node(node, upstream)
            if isinstance(node, RandomItemFromListUtilityNode):
                return self._resolve_random_item_from_list_node(node, upstream)
            if isinstance(node, SandboxTickItemsUtilityNode):
                return self._resolve_sandbox_tick_items_node(node, upstream)
            if isinstance(node, SandboxWorldGridUtilityNode):
                return self._resolve_sandbox_world_grid_node(node, upstream)
            if isinstance(node, SandboxAvailableCellsUtilityNode):
                return self._resolve_sandbox_available_cells_node(node, upstream)
            if isinstance(node, SandboxTickPetUtilityNode):
                return self._resolve_sandbox_tick_pet_node(node, upstream)
            if isinstance(node, SandboxFilterItemsByTypeUtilityNode):
                return self._resolve_sandbox_filter_items_by_type_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxNearestItemByTypeUtilityNode):
                return self._resolve_sandbox_nearest_item_by_type_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxClosestItemUtilityNode):
                return self._resolve_sandbox_closest_item_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxDecisionIntentUtilityNode):
                return self._resolve_sandbox_decision_intent_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxDecisionMoveToUtilityNode):
                return self._resolve_sandbox_decision_move_to_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxStarterDecisionUtilityNode):
                return self._resolve_sandbox_starter_decision_node(node, upstream)
            if isinstance(node, SandboxPetHungerUtilityNode):
                return self._resolve_sandbox_pet_hunger_node(node, upstream)
            if isinstance(node, SandboxPetEnergyUtilityNode):
                return self._resolve_sandbox_pet_energy_node(node, upstream)
            if isinstance(node, SandboxPetCellUtilityNode):
                return self._resolve_sandbox_pet_cell_node(node, upstream)
            if isinstance(node, SandboxIsNearby8UtilityNode):
                return self._resolve_sandbox_is_nearby8_node(node, edges, outputs, overrides)
            if isinstance(node, SandboxFirstNearbyFoodUtilityNode):
                return self._resolve_sandbox_first_nearby_food_node(node, upstream)
            if isinstance(node, SandboxFirstFoodWorldOrderUtilityNode):
                return self._resolve_sandbox_first_food_world_order_node(node, upstream)
            if isinstance(node, ListItemByIndexUtilityNode):
                return self._resolve_list_item_by_index_node(node, edges, outputs, overrides)
            if isinstance(node, DictionaryValueByKeyUtilityNode):
                return self._resolve_dictionary_value_by_key_node(node, edges, outputs, overrides)
            if isinstance(node, DictionarySetValueByKeyUtilityNode):
                return self._resolve_dictionary_set_value_by_key_node(node, edges, outputs, overrides)
            if isinstance(node, ReadDocumentPropertyUtilityNode):
                return self._resolve_read_document_property_node(node, edges, outputs, overrides)
            if isinstance(node, LoadDocumentUtilityNode):
                return self._resolve_load_document_node(node, edges, outputs, overrides)
            if isinstance(node, UpsertDocumentUtilityNode):
                return self._resolve_upsert_document_node(node, edges, outputs, overrides)
            if isinstance(node, ParseDocumentBodyUtilityNode):
                return self._resolve_parse_document_body_node(node, edges, outputs, overrides)
            if isinstance(node, HtmlParseBasicUtilityNode):
                return self._resolve_html_parse_basic_node(node, edges, outputs, overrides)
            if isinstance(node, WriteObjectToDocumentBodyUtilityNode):
                return self._resolve_write_object_to_document_body_node(node, edges, outputs, overrides)
            if isinstance(node, AppendValueToDocumentUtilityNode):
                return self._resolve_append_value_to_document_node(node, edges, outputs, overrides)
            if isinstance(node, ValidateAgainstStructureUtilityNode):
                return self._resolve_validate_against_structure_node(node, edges, outputs, overrides)
            if isinstance(node, AddToListUtilityNode):
                return self._resolve_add_to_list_node(
                    node,
                    edges,
                    outputs,
                    overrides,
                    loop_list_carry=loop_list_carry,
                    for_loop_id=for_loop_id,
                )
            if isinstance(node, PrependTextUtilityNode):
                return self._resolve_prepend_text_node(node, edges, outputs, overrides)
            if isinstance(node, StringTruncUtilityNode):
                return self._resolve_string_trunc_node(node, edges, outputs, overrides)
            if isinstance(node, MessageUtilityNode):
                return self._resolve_message_utility_node(node, edges, outputs, overrides)
            if isinstance(node, AddDaysUtilityNode):
                return self._resolve_add_days_node(node, edges, outputs, overrides)
            if isinstance(node, AddIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "add")
            if isinstance(node, SubtractIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "sub")
            if isinstance(node, MultiplyIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "mul")
            if isinstance(node, DivideIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "div")
            if isinstance(node, ModuloIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "mod")
            if isinstance(node, MinIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "min")
            if isinstance(node, MaxIntsUtilityNode):
                return self._resolve_binary_int_math_node(node, edges, outputs, overrides, "max")
            if isinstance(node, BasicConditionalControlNode):
                return self._resolve_basic_conditional_node(node, edges, outputs, overrides)
            if isinstance(node, IsControlNode):
                return self._resolve_is_node(node, edges, outputs, overrides)
            if isinstance(node, IsEmptyControlNode):
                return self._resolve_is_empty_node(node, edges, outputs, overrides)
            if isinstance(node, GtControlNode):
                return self._resolve_gt_node(node, edges, outputs, overrides)
            if isinstance(node, LtControlNode):
                return self._resolve_lt_node(node, edges, outputs, overrides)
            if isinstance(node, GteControlNode):
                return self._resolve_gte_node(node, edges, outputs, overrides)
            if isinstance(node, LteControlNode):
                return self._resolve_lte_node(node, edges, outputs, overrides)
            if isinstance(node, AndControlNode):
                return self._resolve_and_node(node, edges, outputs, overrides)
            if isinstance(node, OrControlNode):
                return self._resolve_or_node(node, edges, outputs, overrides)
            if isinstance(node, XorControlNode):
                return self._resolve_xor_node(node, edges, outputs, overrides)
            if isinstance(node, NotControlNode):
                return self._resolve_not_node(node, edges, outputs, overrides)
            if isinstance(node, BetweenControlNode):
                return self._resolve_between_node(node, edges, outputs, overrides)
            if isinstance(node, WorkflowRefNode):
                return await self._resolve_workflow_node(
                    node,
                    edges,
                    outputs,
                    overrides,
                    workflow,
                    stack,
                    execution_time_zone,
                    output_overrides_map=output_overrides_map,
                )
        except Exception as exc:
            logger.error(f"WorkflowExecutor: node {node.id} failed — {exc}")
            return {"status": "error", "error": str(exc)}

        return {"status": "error", "error": f"Unknown node kind for node {node.id}"}

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    def _resolve_decision_action_primitive_node(
        self, node: DecisionActionPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Emit a validated ``DecisionAction`` string as ``StringNodeOutput`` (for ``sandbox_decision_intent``)."""
        if upstream:
            first = upstream[0]
            t = _text_from_stringish_output(first)
            if t is None and hasattr(first, "text"):
                t = getattr(first, "text", None)
            if t is None:
                return _error_with_resolved_inputs(
                    "decision_action primitive: upstream must be string-like",
                    {"from_upstream": True},
                )
            s = str(t).strip()
            if s not in DECISION_ACTION_STRINGS:
                return _error_with_resolved_inputs(
                    f"decision_action primitive: invalid action {s!r} (expected one of {sorted(DECISION_ACTION_STRINGS)})",
                    {"action": s},
                )
            return {
                "status": "ok",
                "output": StringNodeOutput(node_id=node.id, text=s),
                "details": {"resolved_inputs": {"action": s}},
            }
        raw = node.data.get("action", "wander")
        s = str(raw).strip() if raw is not None else ""
        if s not in DECISION_ACTION_STRINGS:
            return _error_with_resolved_inputs(
                f"decision_action primitive: invalid action in node data {raw!r}",
                {"action": raw},
            )
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=s),
            "details": {"resolved_inputs": {"action": s}},
        }

    def _resolve_sandbox_tick_primitive_node(
        self,
        node: SandboxTickPrimitiveNode,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Emit validated ``SandboxTickInput`` as ``DictionaryNodeOutput`` (run overrides, else wired tick)."""
        raw: dict | None = None
        ov = input_overrides.get("sandbox_tick")
        if isinstance(ov, dict) and "world" in ov and "pet" in ov and "tick" in ov:
            raw = dict(ov)
        if raw is None:
            raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                (
                    "sandbox_tick primitive: no tick — run from Sandbox (tick override), "
                    "or wire Start's sandbox_tick / a tick-shaped dictionary to input"
                ),
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_tick primitive: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        data = tick_in.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"sandbox_tick": data}},
        }

    def _resolve_string_primitive_node(
        self, node: StringPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the static string, or aggregate upstream text. When upstream exists,
        also include the node's own text so that String nodes with both incoming edges
        and user-entered content pass that content through."""
        if upstream:
            parts = []
            for out in upstream:
                if hasattr(out, "text"):
                    parts.append(out.text)
                elif hasattr(out, "data"):
                    parts.append(json.dumps(out.data))
            node_text = node.data.get("text", "").strip()
            if node_text:
                parts.append(node_text)
            text = "\n\n".join(parts)
        else:
            text = node.data.get("text", "")
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": {"text": text}},
        }

    def _resolve_list_primitive_node(self, node: ListPrimitiveNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Return the static list, or use upstream list (pass-through), or gather upstream outputs into a list."""
        if upstream:
            if len(upstream) == 1:
                out = upstream[0]
                if isinstance(out, ListNodeOutput):
                    return {
                        "status": "ok",
                        "output": ListNodeOutput(node_id=node.id, data=out.data),
                        "details": {"resolved_inputs": {"list": out.data}},
                    }
                if isinstance(out, StringNodeOutput):
                    text = (out.text or "").strip()
                    if text.startswith("["):
                        try:
                            parsed = json.loads(text)
                            if isinstance(parsed, list):
                                return {
                                    "status": "ok",
                                    "output": ListNodeOutput(node_id=node.id, data=parsed),
                                    "details": {"resolved_inputs": {"list": parsed}},
                                }
                        except (json.JSONDecodeError, TypeError):
                            pass
                if isinstance(out, StartNodeOutput):
                    for val in out.outputs.values():
                        if isinstance(val, list):
                            return {
                                "status": "ok",
                                "output": ListNodeOutput(node_id=node.id, data=val),
                                "details": {"resolved_inputs": {"list": val}},
                            }
            data = []
            for out in upstream:
                if hasattr(out, "text"):
                    data.append(out.text)
                elif hasattr(out, "data"):
                    if isinstance(getattr(out, "data"), list):
                        data.extend(getattr(out, "data"))
                    else:
                        data.append(getattr(out, "data"))
                elif hasattr(out, "value"):
                    data.append(out.value)
                else:
                    data.append(str(out))
        else:
            data = node.data if isinstance(node.data, list) else (node.data or [])
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"list": data}},
        }

    def _resolve_dictionary_primitive_node(
        self,
        node: DictionaryPrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
    ) -> Dict[str, Any]:
        """Return the static dictionary, or merge upstream dictionaries and keyed scalars.

        For each non-trigger incoming edge, merge ``DictionaryNodeOutput.data`` with
        ``dict.update``. For any other resolved output (e.g. int/string from Start slots),
        set ``data[source_handle]`` to the plain Python value (``source_handle`` is the
        Start slot key when wiring from Start). Empty ``source_handle`` uses ``\"output\"``.
        If that key already exists (e.g. several parallel wires all use ``\"output\"``),
        the key is suffixed with ``_`` + source node id so each wire contributes a distinct entry.
        """
        data_edges = [e for e in edges if e.target == node.id and (e.target_handle or "") != "trigger"]
        if not data_edges:
            static_payload = dict(node.data) if isinstance(node.data, dict) else {}
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=static_payload),
                "details": {"resolved_inputs": {"data": static_payload}},
            }
        merged: dict[str, Any] = {}
        for edge in data_edges:
            src = edge.source
            out = outputs.get(src)
            if out is None:
                continue
            slot_val = _get_slot_value(out, edge.source_handle)
            if isinstance(slot_val, DictionaryNodeOutput):
                merged.update(dict(slot_val.data))
            else:
                base_key = (edge.source_handle or "").strip() or "output"
                key = base_key
                if key in merged:
                    key = f"{base_key}_{edge.source}"
                merged[key] = node_output_to_input_override_value(slot_val)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=merged),
            "details": {"resolved_inputs": {"data": merged}},
        }

    def _resolve_boolean_primitive_node(
        self, node: BooleanPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the static boolean, or first upstream boolean."""
        if upstream:
            first = upstream[0]
            if isinstance(first, BooleanNodeOutput):
                return {
                    "status": "ok",
                    "output": BooleanNodeOutput(node_id=node.id, value=first.value),
                    "details": {"resolved_inputs": {"value": first.value}},
                }
            if hasattr(first, "text"):
                s = (first.text or "").strip().lower()
                val = s in ("true", "yes", "1") if s else False
                return {
                    "status": "ok",
                    "output": BooleanNodeOutput(node_id=node.id, value=val),
                    "details": {"resolved_inputs": {"value": val}},
                }
        val = node.data.get("value", False)
        if not isinstance(val, bool):
            val = str(val).strip().lower() in ("true", "yes", "1")
        val = bool(val)
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=val),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_int_primitive_node(self, node: IntPrimitiveNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Return the static int, or first upstream int."""
        if upstream:
            first = upstream[0]
            if isinstance(first, IntNodeOutput):
                return {
                    "status": "ok",
                    "output": IntNodeOutput(node_id=node.id, value=first.value),
                    "details": {"resolved_inputs": {"value": first.value}},
                }
            if hasattr(first, "value") and isinstance(getattr(first, "value"), int):
                v = int(getattr(first, "value"))
                return {
                    "status": "ok",
                    "output": IntNodeOutput(node_id=node.id, value=v),
                    "details": {"resolved_inputs": {"value": v}},
                }
            try:
                if hasattr(first, "text"):
                    v = int(first.text or 0)
                    return {
                        "status": "ok",
                        "output": IntNodeOutput(node_id=node.id, value=v),
                        "details": {"resolved_inputs": {"value": v}},
                    }
            except (ValueError, TypeError):
                pass
        val = node.data.get("value", 0)
        try:
            val = int(val) if val is not None else 0
        except (ValueError, TypeError):
            val = 0
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=val),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_datetime_primitive_node(
        self, node: DateTimePrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return static RFC3339 iso from data, or first upstream datetime/string."""
        if upstream:
            first = upstream[0]
            if isinstance(first, DateTimeNodeOutput):
                return {
                    "status": "ok",
                    "output": DateTimeNodeOutput(node_id=node.id, iso=first.iso),
                    "details": {"resolved_inputs": {"iso": first.iso}},
                }
            if isinstance(first, StringNodeOutput):
                norm = parse_rfc3339_datetime_string(first.text)
                if norm is not None:
                    return {
                        "status": "ok",
                        "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
                        "details": {"resolved_inputs": {"iso": norm}},
                    }
            t = _text_from_stringish_output(first)
            if t is not None:
                norm = parse_rfc3339_datetime_string(t)
                if norm is not None:
                    return {
                        "status": "ok",
                        "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
                        "details": {"resolved_inputs": {"iso": norm}},
                    }
        if bool((node.data or {}).get("use_now")):
            try:
                now_iso = utc_now_rfc3339_normalized_for_executor()
            except RuntimeError:
                return _error_with_resolved_inputs(
                    "DateTime primitive: use_now could not normalize current UTC time.",
                    {"iso": None, "use_now": True},
                )
            return {
                "status": "ok",
                "output": DateTimeNodeOutput(node_id=node.id, iso=now_iso),
                "details": {"resolved_inputs": {"iso": now_iso, "use_now": True}},
            }
        raw = (node.data or {}).get("iso")
        if raw is None:
            return _error_with_resolved_inputs(
                "DateTime primitive: set a value in the editor or wire an upstream datetime/string.",
                {"iso": None},
            )
        norm = parse_rfc3339_datetime_string(str(raw))
        if norm is None:
            return _error_with_resolved_inputs(
                "DateTime primitive: value is not a valid RFC3339 datetime.",
                {"iso": raw},
            )
        return {
            "status": "ok",
            "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
            "details": {"resolved_inputs": {"iso": norm}},
        }

    def _resolve_list_to_string_node(
        self, node: ListToStringUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Convert upstream list input to string representation for passing to prompts."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                # Start outputs dict; pick first list value or use []
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        cfg = node.data if isinstance(node.data, dict) else {}
        use_text_join = bool(cfg.get("use_text_join"))
        add_lb_raw = cfg.get("add_line_breaks_between_items")
        add_line_breaks = True if add_lb_raw is None else bool(add_lb_raw)
        if use_text_join:
            sep = "\n" if add_line_breaks else " "
            text = sep.join(_list_item_to_join_token(x) for x in data)
            resolved = {
                "list": data,
                "use_text_join": True,
                "add_line_breaks_between_items": add_line_breaks,
            }
        else:
            text = json.dumps(data, indent=2) if isinstance(data, (list, dict)) else str(data)
            resolved = {
                "list": data,
                "use_text_join": False,
                "add_line_breaks_between_items": add_line_breaks,
            }
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": resolved},
        }

    def _resolve_string_to_list_node(
        self, node: StringToListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Parse JSON array text from upstream into a list output."""
        if not upstream:
            return _error_with_resolved_inputs("String to List: no upstream input", {"upstream": False})
        first = upstream[0]
        t = _text_from_stringish_output(first)
        if t is None:
            if hasattr(first, "text"):
                t = getattr(first, "text")
            else:
                return _error_with_resolved_inputs(
                    "String to List: expected string-like upstream output (String, LLM response, or Start text)",
                    {"upstream_type": type(first).__name__},
                )
        text = (t or "").strip()
        if not text:
            return _error_with_resolved_inputs("String to List: input text is empty", {"text_chars": 0})
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            return _error_with_resolved_inputs(
                f"String to List: invalid JSON ({e})",
                {"text": text[:2048]},
            )
        if not isinstance(parsed, list):
            return _error_with_resolved_inputs(
                "String to List: JSON must be an array",
                {"text": text[:2048]},
            )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=parsed),
            "details": {"resolved_inputs": {"text": text}},
        }

    def _resolve_int_to_string_node(
        self, node: IntToStringUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Convert upstream int (or parseable string / Start int slot) to decimal string."""
        if not upstream:
            return _error_with_resolved_inputs("Int to String: no upstream input", {"upstream": False})
        first = upstream[0]
        n: Optional[int] = None
        resolved_key: Optional[str] = None
        if isinstance(first, IntNodeOutput):
            n = first.value
        elif isinstance(first, BooleanNodeOutput):
            return _error_with_resolved_inputs(
                "Int to String: boolean is not an integer",
                {"upstream_type": "BooleanNodeOutput"},
            )
        elif isinstance(first, StartNodeOutput):
            for key, val in first.outputs.items():
                if isinstance(val, bool):
                    continue
                if isinstance(val, int):
                    n = val
                    resolved_key = key
                    break
                parsed = parse_strict_int_for_slot(val, "input")
                if parsed[0] is not None:
                    n = parsed[0]
                    resolved_key = key
                    break
            if n is None:
                return _error_with_resolved_inputs(
                    "Int to String: no int-like value in Start inputs",
                    {"start_keys": list(first.outputs.keys())[:64]},
                )
        else:
            t = _text_from_stringish_output(first)
            if t is None:
                if hasattr(first, "text"):
                    t = getattr(first, "text")
            if t is None:
                return _error_with_resolved_inputs(
                    "Int to String: expected int-like upstream output (Int, Start int slot, or parseable string)",
                    {"upstream_type": type(first).__name__},
                )
            parsed = parse_strict_int_for_slot((t or "").strip(), "input")
            if parsed[0] is None:
                return _error_with_resolved_inputs(
                    f"Int to String: {parsed[1]}",
                    {"text_preview": (t or "")[:2048]},
                )
            n = parsed[0]
        text = str(n)
        details: Dict[str, Any] = {"resolved_inputs": {"value": n, "text": text}}
        if resolved_key is not None:
            details["resolved_inputs"]["start_key"] = resolved_key
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": details,
        }

    def _resolve_len_from_list_node(
        self, node: LenFromListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the length of the upstream list input."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        length = len(data)
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=length),
            "details": {"resolved_inputs": {"list": data}},
        }

    def _resolve_random_item_from_list_node(
        self, node: RandomItemFromListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return one uniformly random element from the upstream list (``secrets.randbelow`` index)."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        if len(data) == 0:
            return {"status": "error", "error": "random_item_from_list: list is empty"}
        idx = secrets.randbelow(len(data))
        item = data[idx]
        out: NodeOutputUnion
        if isinstance(item, str):
            out = StringNodeOutput(node_id=node.id, text=item)
        elif isinstance(item, list):
            out = ListNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, dict):
            out = DictionaryNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, int):
            out = IntNodeOutput(node_id=node.id, value=item)
        elif isinstance(item, bool):
            out = BooleanNodeOutput(node_id=node.id, value=item)
        else:
            out = StringNodeOutput(node_id=node.id, text=str(item))
        return {
            "status": "ok",
            "output": out,
            "details": {"resolved_inputs": {"list": data, "picked_index": idx}},
        }

    def _resolve_sandbox_tick_items_node(
        self, node: SandboxTickItemsUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return ``world.items`` as a JSON-like list from a wired tick dictionary."""
        from app.domain.sandbox.query import filter_items_by_type, item_type_literal, tick_dict_to_items

        data_cfg = node.data or {}
        raw_type_hint = data_cfg.get("item_type")
        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_tick_items: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"item_type": raw_type_hint, "sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_tick_items: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw, "item_type": raw_type_hint},
            )
        items = tick_dict_to_items(raw)
        data = data_cfg
        raw_type = data.get("item_type")
        if raw_type is None:
            item_type_sel = "all"
        else:
            s = str(raw_type).strip().lower()
            if s in ("", "all"):
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _error_with_resolved_inputs(
                        f"sandbox_tick_items: {exc}",
                        {"sandbox_tick": raw, "item_type": raw_type},
                    )
                item_type_sel = s
        if item_type_sel != "all":
            items = filter_items_by_type(items, item_type_sel)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "item_count": len(items)}},
        }

    def _resolve_sandbox_filter_items_by_type_node(
        self,
        node: SandboxFilterItemsByTypeUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import filter_items_by_type, item_type_literal

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "items", "type": "list", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["items", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        items_raw = resolved.get("items")
        if items_raw is None:
            items_raw = []
        if isinstance(items_raw, str):
            try:
                items_raw = json.loads(items_raw)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "sandbox_filter_items_by_type: items must be a list or JSON array",
                    dict(resolved),
                )
        if not isinstance(items_raw, list):
            return _error_with_resolved_inputs(
                "sandbox_filter_items_by_type: items must be a list",
                dict(resolved),
            )
        item_type = resolved.get("item_type")
        if item_type is None or (isinstance(item_type, str) and not item_type.strip()):
            item_type = "food"
        else:
            item_type = str(item_type).strip()
        try:
            item_type_literal(item_type)
        except ValueError as exc:
            return _error_with_resolved_inputs(
                f"sandbox_filter_items_by_type: {exc}",
                dict(resolved),
            )
        dict_items = [it for it in items_raw if isinstance(it, dict)]
        out = filter_items_by_type(dict_items, item_type)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=out),
            "details": {"resolved_inputs": {"item_type": item_type, "count": len(out)}},
        }

    def _resolve_sandbox_decision_intent_node(
        self,
        node: SandboxDecisionIntentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "action", "type": "string", "value": "wander"},
            {"key": "target_item_id", "type": "string", "value": None},
            {"key": "target_cell", "type": "dictionary", "value": None},
            {"key": "reason", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["action", "target_item_id", "target_cell", "reason"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        action = resolved.get("action")
        if action is None or (isinstance(action, str) and not action.strip()):
            return _error_with_resolved_inputs("sandbox_decision_intent: action is required", dict(resolved))
        action_s = str(action).strip()

        tid = resolved.get("target_item_id")
        if tid is not None:
            if isinstance(tid, str) and not tid.strip():
                tid = None
            elif tid is not None:
                tid = str(tid).strip() or None

        tc_raw = resolved.get("target_cell")
        if tc_raw is not None and tc_raw == "":
            tc_raw = None
        if isinstance(tc_raw, str):
            try:
                tc_raw = json.loads(tc_raw)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "sandbox_decision_intent: target_cell must be a JSON object or null",
                    dict(resolved),
                )
        tc: GridCell | None = None
        if tc_raw is not None:
            if not isinstance(tc_raw, dict):
                return _error_with_resolved_inputs(
                    "sandbox_decision_intent: target_cell must be a dictionary",
                    dict(resolved),
                )
            try:
                tc = GridCell.model_validate(tc_raw)
            except Exception as exc:
                return _error_with_resolved_inputs(
                    f"sandbox_decision_intent: invalid target_cell: {exc}",
                    dict(resolved),
                )

        reason = resolved.get("reason")
        if reason is not None and reason != "":
            reason = str(reason)
        else:
            reason = None

        try:
            dec = DecisionIntent.model_validate(
                {
                    "action": action_s,
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                }
            )
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_decision_intent: {exc}",
                {
                    "action": action_s,
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                },
            )
        data = dec.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_world_grid_node(
        self, node: SandboxWorldGridUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import world_grid_dimensions_from_tick

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_world_grid: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_world_grid: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        dims = world_grid_dimensions_from_tick(raw)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dims),
            "details": {"resolved_inputs": dims},
        }

    def _resolve_sandbox_available_cells_node(
        self, node: SandboxAvailableCellsUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import available_cells_from_tick_dict

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_available_cells: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_available_cells: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        cells = available_cells_from_tick_dict(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=cells),
            "details": {"resolved_inputs": {"cell_count": len(cells)}},
        }

    def _resolve_sandbox_tick_pet_node(
        self, node: SandboxTickPetUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_tick_pet: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_tick_pet: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        data = tick_in.pet.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"pet": data}},
        }

    def _resolve_sandbox_nearest_item_by_type_node(
        self,
        node: SandboxNearestItemByTypeUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import item_type_literal, nearest_item_dicts_by_type

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "sandbox_tick", "type": "dictionary", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["sandbox_tick", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("sandbox_tick")
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_nearest_item_by_type: connect sandbox_tick",
                dict(resolved),
            )
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "sandbox_nearest_item_by_type: sandbox_tick must be a JSON object or array",
                    dict(resolved),
                )
        if not isinstance(raw, dict):
            return _error_with_resolved_inputs(
                "sandbox_nearest_item_by_type: sandbox_tick must be a dictionary",
                dict(resolved),
            )
        raw_t = resolved.get("item_type")
        if raw_t is None or (isinstance(raw_t, str) and not str(raw_t).strip()):
            item_type_sel = "food"
        else:
            s = str(raw_t).strip().lower()
            if s == "all":
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _error_with_resolved_inputs(
                        f"sandbox_nearest_item_by_type: {exc}",
                        dict(resolved),
                    )
                item_type_sel = s
        try:
            out = nearest_item_dicts_by_type(raw, item_type_sel)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_nearest_item_by_type: {exc}",
                {**dict(resolved), "item_type": item_type_sel},
            )
        data = out[0] if out else {}
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "has_item": bool(out)}},
        }

    def _resolve_sandbox_closest_item_node(
        self,
        node: SandboxClosestItemUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import item_type_literal, nearest_item_dicts_by_type

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "sandbox_tick", "type": "dictionary", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["sandbox_tick", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("sandbox_tick")
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_closest_item: connect sandbox_tick",
                dict(resolved),
            )
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "sandbox_closest_item: sandbox_tick must be a JSON object or array",
                    dict(resolved),
                )
        if not isinstance(raw, dict):
            return _error_with_resolved_inputs(
                "sandbox_closest_item: sandbox_tick must be a dictionary",
                dict(resolved),
            )
        raw_t = resolved.get("item_type")
        if raw_t is None or (isinstance(raw_t, str) and not str(raw_t).strip()):
            item_type_sel = "food"
        else:
            s = str(raw_t).strip().lower()
            if s == "all":
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _error_with_resolved_inputs(
                        f"sandbox_closest_item: {exc}",
                        dict(resolved),
                    )
                item_type_sel = s
        try:
            out = nearest_item_dicts_by_type(raw, item_type_sel)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_closest_item: {exc}",
                {**dict(resolved), "item_type": item_type_sel},
            )
        data = out[0] if out else {}
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "has_item": bool(out)}},
        }

    def _resolve_sandbox_decision_move_to_node(
        self,
        node: SandboxDecisionMoveToUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_item_id", "type": "string", "value": None},
            {"key": "target_cell", "type": "dictionary", "value": None},
            {"key": "reason", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_item_id", "target_cell", "reason"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        tid = resolved.get("target_item_id")
        if tid is not None:
            if isinstance(tid, str) and not tid.strip():
                tid = None
            elif tid is not None:
                tid = str(tid).strip() or None

        tc_raw = resolved.get("target_cell")
        if tc_raw is not None and tc_raw == "":
            tc_raw = None
        if isinstance(tc_raw, str):
            try:
                tc_raw = json.loads(tc_raw)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "sandbox_decision_move_to: target_cell must be a JSON object or null",
                    dict(resolved),
                )
        tc: GridCell | None = None
        if tc_raw is not None:
            if not isinstance(tc_raw, dict):
                return _error_with_resolved_inputs(
                    "sandbox_decision_move_to: target_cell must be a dictionary",
                    dict(resolved),
                )
            try:
                tc = GridCell.model_validate(tc_raw)
            except Exception as exc:
                return _error_with_resolved_inputs(
                    f"sandbox_decision_move_to: invalid target_cell: {exc}",
                    dict(resolved),
                )

        reason = resolved.get("reason")
        if reason is not None and reason != "":
            reason = str(reason)
        else:
            reason = None

        try:
            dec = DecisionIntent.model_validate(
                {
                    "action": "move_to",
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                }
            )
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_decision_move_to: {exc}",
                {
                    "action": "move_to",
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                },
            )
        data = dec.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_starter_decision_node(
        self, node: SandboxStarterDecisionUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Same policy as legacy ``sandbox_behavior`` primitive (starter_behavior_decision)."""
        from app.domain.sandbox.starter_behavior import starter_behavior_decision

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_starter_decision: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_starter_decision: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        try:
            dec = starter_behavior_decision(tick_in)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_starter_decision: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dec.model_dump(mode="json")),
            "details": {"resolved_inputs": {"sandbox_tick": raw}},
        }

    def _resolve_sandbox_pet_hunger_node(
        self, node: SandboxPetHungerUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_hunger_from_tick_dict

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_pet_hunger: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            v = pet_hunger_from_tick_dict(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_pet_hunger: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=int(v)),
            "details": {"resolved_inputs": {"hunger": v}},
        }

    def _resolve_sandbox_pet_energy_node(
        self, node: SandboxPetEnergyUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_energy_from_tick_dict

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_pet_energy: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            v = pet_energy_from_tick_dict(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_pet_energy: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=int(v)),
            "details": {"resolved_inputs": {"energy": v}},
        }

    def _resolve_sandbox_pet_cell_node(
        self, node: SandboxPetCellUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_cell_dict_from_tick_dict

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_pet_cell: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            cell = pet_cell_dict_from_tick_dict(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_pet_cell: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=cell),
            "details": {"resolved_inputs": cell},
        }

    def _resolve_sandbox_is_nearby8_node(
        self,
        node: SandboxIsNearby8UtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import grid_cell_from_jsonable, is_nearby8

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "cell_a", "type": "dictionary", "value": None},
            {"key": "cell_b", "type": "dictionary", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["cell_a", "cell_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _coerce_cell(label: str, raw: Any) -> GridCell:
            if raw is None:
                raise ValueError(f"{label}: missing value")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ValueError(f"{label}: invalid JSON") from exc
            if isinstance(raw, dict):
                return grid_cell_from_jsonable(raw)
            raise ValueError(f"{label}: expected a dictionary")

        try:
            a = _coerce_cell("cell_a", resolved.get("cell_a"))
            b = _coerce_cell("cell_b", resolved.get("cell_b"))
            ok = is_nearby8(a, b)
        except ValueError as exc:
            return _error_with_resolved_inputs(
                f"sandbox_is_nearby8: {exc}",
                dict(resolved),
            )
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_is_nearby8: {exc}",
                dict(resolved),
            )
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=ok),
            "details": {
                "resolved_inputs": {
                    "cell_a": a.model_dump(mode="json"),
                    "cell_b": b.model_dump(mode="json"),
                }
            },
        }

    def _resolve_sandbox_first_nearby_food_node(
        self, node: SandboxFirstNearbyFoodUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import first_nearby_food_item_dicts

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_first_nearby_food: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_first_nearby_food: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        items = first_nearby_food_item_dicts(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"count": len(items)}},
        }

    def _resolve_sandbox_first_food_world_order_node(
        self, node: SandboxFirstFoodWorldOrderUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import first_food_world_order_item_dicts

        raw = _sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_first_food_world_order: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_first_food_world_order: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        items = first_food_world_order_item_dicts(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"count": len(items)}},
        }

    def _resolve_list_item_by_index_node(
        self,
        node: ListItemByIndexUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the item at the given index in the list. Raises ValueError if out of bounds."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "index", "type": "int", "value": 0},
            {"key": "list", "type": "list", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["index", "list"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw_index = resolved.get("index")
        if raw_index is None or raw_index == "":
            return _error_with_resolved_inputs("Index is required", dict(resolved))
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return _error_with_resolved_inputs("Index must be a valid integer", dict(resolved))
        if index < 0:
            return _error_with_resolved_inputs(
                f"Index {index} is out of bounds: index must be non-negative",
                dict(resolved),
            )
        data = resolved.get("list")
        if data is None:
            data = []
        if not isinstance(data, list):
            try:
                data = json.loads(data) if isinstance(data, str) else list(data)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs("List input must be a list", dict(resolved))
        if index >= len(data):
            valid_range = f"0-{len(data) - 1}" if data else "empty list has no valid indices"
            return _error_with_resolved_inputs(
                f"Index {index} is out of bounds: list has {len(data)} items (valid indices: {valid_range})",
                dict(resolved),
            )
        item = data[index]
        out: NodeOutputUnion
        if isinstance(item, str):
            out = StringNodeOutput(node_id=node.id, text=item)
        elif isinstance(item, list):
            out = ListNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, dict):
            out = DictionaryNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, int):
            out = IntNodeOutput(node_id=node.id, value=item)
        elif isinstance(item, bool):
            out = BooleanNodeOutput(node_id=node.id, value=item)
        else:
            out = StringNodeOutput(node_id=node.id, text=str(item))
        return {"status": "ok", "output": out, "details": {"resolved_inputs": {"index": index, "list": data}}}

    def _resolve_dictionary_value_by_key_node(
        self,
        node: DictionaryValueByKeyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the value for a key in a dictionary, coerced to a declared primitive output type."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "key", "type": "string", "value": ""},
            {"key": "dictionary", "type": "dictionary", "value": None},
        ]
        raw_ovt = (node.data or {}).get("output_value_type")
        output_value_type = raw_ovt if isinstance(raw_ovt, str) else "list"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int", "datetime"})
        if output_value_type not in allowed:
            return _error_with_resolved_inputs(
                f"Dictionary value by key: output_value_type must be one of {sorted(allowed)}; got {output_value_type!r}",
                {"output_value_type": output_value_type},
            )
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["key", "dictionary"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {
                "key": resolved.get("key"),
                "output_value_type": output_value_type,
            }
            rd = resolved.get("dictionary")
            if isinstance(rd, dict):
                base["dictionary_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["dictionary_input_chars"] = len(rd)
            elif rd is not None:
                base["dictionary_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("key")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _error_with_resolved_inputs("Dictionary value by key: key is required", _snap())
        key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_dict = resolved.get("dictionary")
        d: Dict[str, Any]
        if isinstance(raw_dict, dict):
            d = raw_dict
        elif isinstance(raw_dict, str):
            try:
                parsed = json.loads(raw_dict)
            except (json.JSONDecodeError, TypeError) as e:
                return _error_with_resolved_inputs(
                    f"Dictionary value by key: invalid JSON for dictionary input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _error_with_resolved_inputs(
                    "Dictionary value by key: dictionary input must be a JSON object",
                    _snap(),
                )
            d = parsed
        else:
            return _error_with_resolved_inputs(
                "Dictionary value by key: dictionary input must be a dictionary",
                _snap(),
            )

        def _matches_expected(v: Any, ovt: str) -> bool:
            if ovt == "string":
                return isinstance(v, str)
            if ovt == "list":
                return isinstance(v, list)
            if ovt == "dictionary":
                return isinstance(v, dict)
            if ovt == "boolean":
                return isinstance(v, bool)
            if ovt == "int":
                return type(v) is int or (isinstance(v, int) and not isinstance(v, bool))
            if ovt == "datetime":
                return isinstance(v, str) and parse_rfc3339_datetime_string(v) is not None
            return False

        def _resolve_optional_fallback() -> tuple[Any, str] | None:
            """
            (value, source) or None.

            Precedence: input override, wire to ``fallback`` (first upstream with output; if an edge
            exists but no output yet, fall through to static), ``data.fallback_value``, then
            ``required_inputs`` entry for key ``fallback`` (non-``None`` value).
            """
            ovr = (input_overrides or {}).get("fallback")
            if ovr is not None:
                return (ovr, "override")
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "fallback":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                return (node_output_to_input_override_value(slot), "wire")
            if "fallback_value" in (node.data or {}):
                return ((node.data or {})["fallback_value"], "data")
            for item in (node.data or {}).get("required_inputs") or []:
                if not isinstance(item, dict) or item.get("key") != "fallback":
                    continue
                v = item.get("value")
                if v is not None:
                    return (v, "required_input")
            return None

        fb = _resolve_optional_fallback()

        def _build_from_val(
            val: Any,
            *,
            from_fallback: bool,
            value_label: str,
        ) -> Dict[str, Any]:
            if not _matches_expected(val, output_value_type):
                if from_fallback:
                    return _error_with_resolved_inputs(
                        f"Dictionary value by key: fallback has wrong type for output_value_type={output_value_type!r}",
                        _snap({"value_type": type(val).__name__}),
                    )
                return _error_with_resolved_inputs(
                    f"Dictionary value by key: value for {value_label!r} has wrong type for output_value_type={output_value_type!r}",
                    _snap({"resolved_key": value_label, "value_type": type(val).__name__}),
                )

            out: NodeOutputUnion
            if output_value_type == "string":
                out = StringNodeOutput(node_id=node.id, text=val)
            elif output_value_type == "list":
                out = ListNodeOutput(node_id=node.id, data=val)
            elif output_value_type == "dictionary":
                out = DictionaryNodeOutput(node_id=node.id, data=val)
            elif output_value_type == "boolean":
                out = BooleanNodeOutput(node_id=node.id, value=val)
            elif output_value_type == "datetime":
                iso = parse_rfc3339_datetime_string(val)
                if iso is None:
                    if from_fallback:
                        return _error_with_resolved_inputs(
                            f"Dictionary value by key: fallback is not a valid RFC3339 datetime for output_value_type={output_value_type!r}",
                            _snap(),
                        )
                    return _error_with_resolved_inputs(
                        f"Dictionary value by key: value for {value_label!r} is not a valid RFC3339 datetime",
                        _snap({"resolved_key": value_label}),
                    )
                out = DateTimeNodeOutput(node_id=node.id, iso=iso)
            else:
                out = IntNodeOutput(node_id=node.id, value=int(val))

            ri: dict[str, Any] = {
                "key": key,
                "output_value_type": output_value_type,
                "dictionary_keys": list(d.keys()),
            }
            if from_fallback and fb is not None:
                ri["use_fallback"] = True
                ri["fallback_source"] = fb[1]
            return {
                "status": "ok",
                "output": out,
                "details": {"resolved_inputs": ri},
            }

        _MISSING = object()
        try:
            if key not in d:
                raw_at_key = _MISSING
            else:
                raw_at_key = d[key]
        except KeyError:
            # Rare (``in``/``get`` / dict-like edge cases); treat like missing and use optional fallback
            raw_at_key = _MISSING

        if raw_at_key is not _MISSING and raw_at_key is not None:
            return _build_from_val(
                raw_at_key,
                from_fallback=False,
                value_label=key,
            )

        if fb is not None:
            fval, _fsrc = fb
            return _build_from_val(fval, from_fallback=True, value_label="fallback")

        if raw_at_key is _MISSING:
            return _error_with_resolved_inputs(
                f"Dictionary value by key: key {key!r} is not present",
                _snap({"resolved_key": key, "dictionary_keys": list(d.keys())[:128]}),
            )
        return _error_with_resolved_inputs(
            f"Dictionary value by key: value for key {key!r} is null",
            _snap({"resolved_key": key, "dictionary_keys": list(d.keys())[:128]}),
        )

    def _resolve_dictionary_set_value_by_key_node(
        self,
        node: DictionarySetValueByKeyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Shallow-copy dictionary input and set one top-level key to value (any JSON-serializable)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "dictionary", "type": "dictionary", "value": None},
            {"key": "key", "type": "string", "value": ""},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["dictionary", "key", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        value_wired = any(e.target == node.id and e.target_handle == "value" for e in edges)
        if input_overrides.get("value") is None:
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "value":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                resolved["value"] = node_output_to_input_override_value(slot)
                break

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {"key": resolved.get("key")}
            rd = resolved.get("dictionary")
            if isinstance(rd, dict):
                base["dictionary_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["dictionary_input_chars"] = len(rd)
            elif rd is not None:
                base["dictionary_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("key")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _error_with_resolved_inputs("Dictionary set value by key: key is required", _snap())

        key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_dict = resolved.get("dictionary")
        d: Dict[str, Any]
        if isinstance(raw_dict, dict):
            d = raw_dict
        elif isinstance(raw_dict, str):
            try:
                parsed = json.loads(raw_dict)
            except (json.JSONDecodeError, TypeError) as e:
                return _error_with_resolved_inputs(
                    f"Dictionary set value by key: invalid JSON for dictionary input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _error_with_resolved_inputs(
                    "Dictionary set value by key: dictionary input must be a JSON object",
                    _snap(),
                )
            d = parsed
        else:
            return _error_with_resolved_inputs(
                "Dictionary set value by key: dictionary input must be a dictionary",
                _snap(),
            )

        raw_val = resolved.get("value")
        if not value_wired and (raw_val is None or raw_val == ""):
            return _error_with_resolved_inputs("Dictionary set value by key: value is required", _snap())

        item = raw_val
        out_dict = dict(d)
        out_dict[key] = item
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=out_dict),
            "details": {
                "resolved_inputs": {
                    "key": key,
                    "dictionary_keys": list(out_dict.keys()),
                }
            },
        }

    def _resolve_read_document_property_node(
        self,
        node: ReadDocumentPropertyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Read a named field from a Document primitive output dict (id, name, description, body)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_property", "type": "string", "value": ""},
            {"key": "document", "type": "document", "value": None},
        ]
        raw_ovt = (node.data or {}).get("output_value_type")
        output_value_type = raw_ovt if isinstance(raw_ovt, str) else "string"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int", "datetime"})
        if output_value_type not in allowed:
            return _error_with_resolved_inputs(
                f"Read document property: output_value_type must be one of {sorted(allowed)}; got {output_value_type!r}",
                {"output_value_type": output_value_type},
            )
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_property", "document"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {
                "target_property": resolved.get("target_property"),
                "output_value_type": output_value_type,
            }
            rd = resolved.get("document")
            if isinstance(rd, dict):
                base["document_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["document_input_chars"] = len(rd)
            elif rd is not None:
                base["document_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("target_property")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _error_with_resolved_inputs("Read document property: target_property is required", _snap())
        prop_key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_doc = resolved.get("document")
        d: Dict[str, Any]
        if isinstance(raw_doc, dict):
            d = raw_doc
        elif isinstance(raw_doc, str):
            try:
                parsed = json.loads(raw_doc)
            except (json.JSONDecodeError, TypeError) as e:
                return _error_with_resolved_inputs(
                    f"Read document property: invalid JSON for document input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _error_with_resolved_inputs(
                    "Read document property: document input must be a dictionary",
                    _snap(),
                )
            d = parsed
        else:
            return _error_with_resolved_inputs(
                "Read document property: document input must be a dictionary",
                _snap(),
            )

        if prop_key not in d:
            return _error_with_resolved_inputs(
                f"Read document property: property {prop_key!r} is not present",
                _snap({"resolved_property": prop_key, "document_keys": list(d.keys())[:128]}),
            )
        val = d[prop_key]
        if val is None:
            return _error_with_resolved_inputs(
                f"Read document property: value for property {prop_key!r} is null",
                _snap({"resolved_property": prop_key, "document_keys": list(d.keys())[:128]}),
            )

        def _matches_expected(v: Any, ovt: str) -> bool:
            if ovt == "string":
                return isinstance(v, str)
            if ovt == "list":
                return isinstance(v, list)
            if ovt == "dictionary":
                return isinstance(v, dict)
            if ovt == "boolean":
                return isinstance(v, bool)
            if ovt == "int":
                return type(v) is int or (isinstance(v, int) and not isinstance(v, bool))
            if ovt == "datetime":
                return isinstance(v, str) and parse_rfc3339_datetime_string(v) is not None
            return False

        if not _matches_expected(val, output_value_type):
            return _error_with_resolved_inputs(
                f"Read document property: value for {prop_key!r} has wrong type for output_value_type={output_value_type!r}",
                _snap({"resolved_property": prop_key, "value_type": type(val).__name__}),
            )

        out: NodeOutputUnion
        if output_value_type == "string":
            out = StringNodeOutput(node_id=node.id, text=val)
        elif output_value_type == "list":
            out = ListNodeOutput(node_id=node.id, data=val)
        elif output_value_type == "dictionary":
            out = DictionaryNodeOutput(node_id=node.id, data=val)
        elif output_value_type == "boolean":
            out = BooleanNodeOutput(node_id=node.id, value=val)
        elif output_value_type == "datetime":
            iso = parse_rfc3339_datetime_string(val)
            if iso is None:
                return _error_with_resolved_inputs(
                    f"Read document property: value for {prop_key!r} is not a valid RFC3339 datetime",
                    _snap({"resolved_property": prop_key}),
                )
            out = DateTimeNodeOutput(node_id=node.id, iso=iso)
        else:
            out = IntNodeOutput(node_id=node.id, value=int(val))

        return {
            "status": "ok",
            "output": out,
            "details": {
                "resolved_inputs": {
                    "target_property": prop_key,
                    "output_value_type": output_value_type,
                    "document_keys": list(d.keys()),
                }
            },
        }

    def _resolve_add_to_list_node(
        self,
        node: AddToListUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        *,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]],
        for_loop_id: Optional[str],
    ) -> Dict[str, Any]:
        """Append a value to a list (any JSON-serializable item). In a For loop body, list state carries across iterations."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "list", "type": "list", "value": None},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["list", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        value_wired = any(e.target == node.id and e.target_handle == "value" for e in edges)
        if input_overrides.get("value") is None:
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "value":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                resolved["value"] = node_output_to_input_override_value(slot)
                break

        carry_bundle = loop_list_carry
        fk = for_loop_id
        carry_key: tuple[str, str] | None = (fk, node.id) if fk and carry_bundle is not None else None
        base_list: list[Any]
        if carry_bundle is not None and carry_key is not None and carry_key in carry_bundle:
            base_list = list(carry_bundle[carry_key])
        else:
            raw_list = resolved.get("list")
            if raw_list is None or (isinstance(raw_list, str) and str(raw_list).strip() == ""):
                return {"status": "error", "error": "Add to list: list input is required"}
            if not isinstance(raw_list, list):
                return {"status": "error", "error": "Add to list: list input must be a list"}
            base_list = list(raw_list)

        raw_val = resolved.get("value")
        if not value_wired and (raw_val is None or raw_val == ""):
            return {"status": "error", "error": "Add to list: value is required"}

        item = raw_val
        new_list = base_list + [item]
        if carry_key is not None and carry_bundle is not None:
            carry_bundle[carry_key] = new_list

        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=new_list),
            "details": {
                "resolved_inputs": {
                    "list": base_list,
                    "value": item,
                    "result_length": len(new_list),
                }
            },
        }

    def _resolve_string_trunc_node(
        self,
        node: StringTruncUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return substring with inclusive ``end_index`` (0-based), or ``end_index == -1`` through end."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_string", "type": "string", "value": None},
            {"key": "start_index", "type": "int", "value": 0},
            {"key": "end_index", "type": "int", "value": -1},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_string", "start_index", "end_index"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw_target = resolved.get("target_string")
        text = raw_target if isinstance(raw_target, str) else ("" if raw_target is None else str(raw_target))

        def _err(msg: str) -> dict[str, Any]:
            return _error_with_resolved_inputs(msg, _string_trunc_error_resolved(resolved))

        raw_start = resolved.get("start_index")
        if raw_start is None or raw_start == "":
            return _err("String trunc: start_index is required")
        try:
            start_i = int(raw_start)
        except (TypeError, ValueError):
            return _err("String trunc: start_index must be a valid integer")
        if start_i < 0:
            return _err(f"String trunc: start_index must be non-negative (got {start_i})")

        raw_end = resolved.get("end_index")
        if raw_end is None or raw_end == "":
            return _err("String trunc: end_index is required")
        try:
            end_i = int(raw_end)
        except (TypeError, ValueError):
            return _err("String trunc: end_index must be a valid integer")
        if end_i < -1:
            return _err(f"String trunc: end_index must be -1 or non-negative (got {end_i})")
        if end_i >= 0 and end_i < start_i:
            return _err(f"String trunc: end_index ({end_i}) must be >= start_index ({start_i}) unless end_index is -1")

        result = text[start_i:] if end_i == -1 else text[start_i : end_i + 1]
        detail = _string_trunc_resolved_inputs_payload(text, start_i, end_i, result=result)
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=result),
            "details": {"resolved_inputs": detail},
        }

    def _resolve_prepend_text_node(
        self,
        node: PrependTextUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepend text to target string, with optional blank line between."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_string", "text_to_prepend"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        target_string = resolved.get("target_string") or ""
        text_to_prepend = resolved.get("text_to_prepend") or ""
        add_additional_line = node.data.get("add_additional_line") is True
        sep = "\n\n" if add_additional_line else ""
        output = (text_to_prepend or "") + sep + (target_string or "")
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=output),
            "details": {
                "resolved_inputs": {
                    "target_string": target_string,
                    "text_to_prepend": text_to_prepend,
                    "add_additional_line": add_additional_line,
                }
            },
        }

    def _resolve_message_utility_node(
        self,
        node: MessageUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Surface wired text to the client as ``details.user_message``; no data output (empty string)."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["message"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("message")
        text = _coerce_message_display_text(raw)
        if len(text) > MESSAGE_UTILITY_MAX_LEN:
            text = text[:MESSAGE_UTILITY_MAX_LEN]
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=""),
            "details": {
                "resolved_inputs": {"message": raw},
                "user_message": text,
            },
        }

    def _resolve_basic_conditional_node(
        self,
        node: BasicConditionalControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate condition and return ConditionalNodeOutput with branch 'true' or 'false'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["condition"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        condition_val = resolved.get("condition")
        if condition_val is None or (isinstance(condition_val, str) and condition_val.strip() == ""):
            condition_val = node.data.get("condition")
        branch = "true" if _condition_to_bool(condition_val) else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"condition": condition_val}},
        }

    def _resolve_is_node(
        self,
        node: IsControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare input_a and input_b for equality; return ConditionalNodeOutput with branch 'true' or 'false'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input_a", "input_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        input_a = resolved.get("input_a")
        input_b = resolved.get("input_b")
        branch = "true" if _values_equal(input_a, input_b) else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"input_a": input_a, "input_b": input_b}},
        }

    def _resolve_is_empty_node(
        self,
        node: IsEmptyControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """True branch when ``value`` is ``[]`` or ``{}``; false when non-empty list or dict."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        if val is None:
            return _error_with_resolved_inputs(
                "is_empty: connect value (list or dictionary)",
                dict(resolved),
            )
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return _error_with_resolved_inputs(
                    "is_empty: value must be a list or dictionary",
                    dict(resolved),
                )
        if not isinstance(val, (list, dict)):
            return _error_with_resolved_inputs(
                "is_empty: value must be a list or dictionary",
                dict(resolved),
            )
        is_empty = len(val) == 0
        branch = "true" if is_empty else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_comparison_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """Shared logic for Gt, Lt, Gte, Lte. op is 'gt', 'lt', 'gte', or 'lte'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id, ["input_a", "input_b"], edges, outputs, input_overrides, raw_inputs
        )
        input_a, input_b = resolved.get("input_a"), resolved.get("input_b")
        a_val, b_val = _to_comparable(input_a, input_b)
        if op == "gt":
            result = a_val > b_val
        elif op == "lt":
            result = a_val < b_val
        elif op == "gte":
            result = a_val >= b_val
        else:
            result = a_val <= b_val
        branch = "true" if result else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"input_a": input_a, "input_b": input_b}},
        }

    def _resolve_gt_node(
        self,
        node: GtControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "gt")

    def _resolve_lt_node(
        self,
        node: LtControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "lt")

    def _resolve_gte_node(
        self,
        node: GteControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "gte")

    def _resolve_lte_node(
        self,
        node: LteControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "lte")

    def _resolve_logical_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """Shared logic for And, Or, Xor. op is 'and', 'or', or 'xor'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id, ["input_a", "input_b"], edges, outputs, input_overrides, raw_inputs
        )
        a_bool = _condition_to_bool(resolved.get("input_a"))
        b_bool = _condition_to_bool(resolved.get("input_b"))
        if op == "and":
            result = a_bool and b_bool
        elif op == "or":
            result = a_bool or b_bool
        else:
            result = a_bool != b_bool
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=result),
            "details": {"resolved_inputs": {"input_a": resolved.get("input_a"), "input_b": resolved.get("input_b")}},
        }

    def _resolve_and_node(
        self,
        node: AndControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "and")

    def _resolve_or_node(
        self,
        node: OrControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "or")

    def _resolve_xor_node(
        self,
        node: XorControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "xor")

    def _resolve_binary_int_math_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """add | sub | mul | div | mod | min | max — two int inputs input_a, input_b → IntNodeOutput."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input_a", "type": "int", "value": 0},
            {"key": "input_b", "type": "int", "value": 0},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input_a", "input_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        a_raw, b_raw = resolved.get("input_a"), resolved.get("input_b")
        a_t = parse_strict_int_for_slot(a_raw, "input_a")
        if a_t[1] is not None:
            return {"status": "error", "error": a_t[1]}
        b_t = parse_strict_int_for_slot(b_raw, "input_b")
        if b_t[1] is not None:
            return {"status": "error", "error": b_t[1]}
        a, b = a_t[0], b_t[0]
        assert a is not None and b is not None

        if op in ("div", "mod") and b == 0:
            return {"status": "error", "error": "input_b is zero (division by zero)"}

        if op == "add":
            out = a + b
        elif op == "sub":
            out = a - b
        elif op == "mul":
            out = a * b
        elif op == "div":
            out = int(a / b)
        elif op == "mod":
            out = a % b
        elif op == "min":
            out = min(a, b)
        else:
            out = max(a, b)

        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=out),
            "details": {"resolved_inputs": {"input_a": a, "input_b": b, "op": op}},
        }

    def _resolve_add_days_node(
        self,
        node: AddDaysUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """RFC3339 instant + signed whole days → DateTimeNodeOutput (UTC timedelta days)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input", "type": "datetime", "value": None},
            {"key": "days", "type": "int", "value": 0},
        ]
        resolved_map = _resolve_inputs_by_target_handle(
            node.id,
            ["input", "days"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        dt_raw = resolved_map.get("input")
        days_raw = resolved_map.get("days")
        norm = parse_rfc3339_datetime_string(dt_raw)
        if norm is None:
            return _error_with_resolved_inputs(
                "Add days: input is not a valid RFC3339 datetime (wire a DateTime or set a static instant).",
                {"input": dt_raw, "days": days_raw},
            )
        days_t = parse_strict_int_for_slot(days_raw, "days")
        if days_t[1] is not None:
            return _error_with_resolved_inputs(
                f"Add days: {days_t[1]}",
                {"input": norm, "days": days_raw},
            )
        dcount = days_t[0]
        assert dcount is not None
        out_iso = shift_rfc3339_instant_by_days(norm, dcount)
        if out_iso is None:
            return _error_with_resolved_inputs(
                "Add days: could not shift datetime.",
                {"input": norm, "days": dcount},
            )
        return {
            "status": "ok",
            "output": DateTimeNodeOutput(node_id=node.id, iso=out_iso),
            "details": {"resolved_inputs": {"input": norm, "days": dcount}},
        }

    def _resolve_not_node(
        self,
        node: NotControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(node.id, ["input"], edges, outputs, input_overrides, raw_inputs)
        input_val = resolved.get("input")
        result = not _condition_to_bool(input_val)
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=result),
            "details": {"resolved_inputs": {"input": input_val}},
        }

    def _resolve_between_node(
        self,
        node: BetweenControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "low", "type": "int", "value": 0},
            {"key": "value", "type": "int", "value": 0},
            {"key": "high", "type": "int", "value": 0},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["low", "value", "high"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        low_t = parse_strict_int_for_slot(resolved.get("low"), "low")
        if low_t[1] is not None:
            return {"status": "error", "error": low_t[1]}
        val_t = parse_strict_int_for_slot(resolved.get("value"), "value")
        if val_t[1] is not None:
            return {"status": "error", "error": val_t[1]}
        high_t = parse_strict_int_for_slot(resolved.get("high"), "high")
        if high_t[1] is not None:
            return {"status": "error", "error": high_t[1]}
        low, value, high = low_t[0], val_t[0], high_t[0]
        assert low is not None and value is not None and high is not None
        if low > high:
            return {
                "status": "error",
                "error": f"low ({low}) must be <= high ({high})",
            }
        branch = "true" if low <= value <= high else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"low": low, "value": value, "high": high}},
        }

    def _resolve_structure_primitive_node(self, node: StructurePrimitiveNode) -> Dict[str, Any]:
        """Load Structure by structure_id and return StructureNodeOutput with parsed schema."""
        structure_id_raw = (node.data or {}).get("structure_id")
        if not structure_id_raw:
            return {
                "status": "error",
                "error": f"Structure primitive node '{node.id}' requires structure_id. Select a Structure in the Workflow Editor.",
                "details": {"resolved_inputs": {"structure_id": None}},
            }
        try:
            sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Structure primitive node '{node.id}' has invalid structure_id.",
                "details": {"resolved_inputs": {"structure_id": structure_id_raw}},
            }
        structure = self.session.exec(
            select(Structure).where(
                col(Structure.id) == sid,
                or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
            )
        ).first()
        if not structure:
            return {
                "status": "error",
                "error": f"Structure '{structure_id_raw}' not found.",
                "details": {"resolved_inputs": {"structure_id": str(sid)}},
            }
        try:
            schema = json.loads(structure.json_schema)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Structure '{structure.name}' has invalid json_schema: {e}",
                "details": {
                    "resolved_inputs": {"structure_id": str(sid), "structure_name": structure.name},
                },
            }
        return {
            "status": "ok",
            "output": StructureNodeOutput(node_id=node.id, schema_dict=schema),
            "details": {
                "resolved_inputs": {
                    "structure_id": str(sid),
                    "structure_name": structure.name,
                }
            },
        }

    def _resolve_sandbox_behavior_primitive_node(
        self, node: SandboxBehaviorPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Map ``SandboxTickInput`` (from Start) to a ``DecisionIntent`` dictionary."""
        from app.domain.sandbox.starter_behavior import starter_behavior_decision
        from app.domain.schemas.sandbox import SandboxTickInput

        raw: dict | None = None
        for out in upstream:
            if isinstance(out, DictionaryNodeOutput):
                raw = dict(out.data)
                break
            if isinstance(out, StartNodeOutput):
                st = out.outputs.get("sandbox_tick")
                if isinstance(st, dict):
                    raw = st
                    break
        if raw is None:
            return _error_with_resolved_inputs(
                "sandbox_behavior: missing sandbox_tick input",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_behavior: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        try:
            dec = starter_behavior_decision(tick_in)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"sandbox_behavior: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dec.model_dump(mode="json")),
            "details": {"resolved_inputs": {"sandbox_tick": raw}},
        }

    def _resolve_document_primitive_node(self, node: DocumentPrimitiveNode) -> Dict[str, Any]:
        """Load Document by document_id and return DocumentNodeOutput."""
        document_id_raw = (node.data or {}).get("document_id")
        if not document_id_raw:
            return {
                "status": "error",
                "error": f"Document primitive node '{node.id}' requires document_id. Select a Document in the Workflow Editor.",
                "details": {"resolved_inputs": {"document_id": None}},
            }
        try:
            did = UUID(document_id_raw) if isinstance(document_id_raw, str) else document_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Document primitive node '{node.id}' has invalid document_id.",
                "details": {"resolved_inputs": {"document_id": document_id_raw}},
            }
        doc = self.session.exec(
            select(Document).where(
                col(Document.id) == did,
                or_(col(Document.user_id) == self.user_id, col(Document.user_id).is_(None)),
            )
        ).first()
        if not doc:
            return {
                "status": "error",
                "error": f"Document '{document_id_raw}' not found.",
                "details": {"resolved_inputs": {"document_id": str(did)}},
            }
        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    "document_id": str(doc.id),
                    "document_name": doc.name,
                }
            },
        }

    def _artifact_uuid_from_image_payload(self, d: dict[str, Any]) -> Optional[UUID]:
        """Resolve artifact id from a flat ref or a ``capture_url_snapshot``-style ``data`` dict."""
        inner = d.get("image")
        if isinstance(inner, dict):
            raw: Any = inner.get("artifact_id") or inner.get("id")
        else:
            raw = d.get("artifact_id") or d.get("id")
        if raw is None:
            return None
        try:
            return UUID(str(raw).strip())
        except (ValueError, TypeError):
            return None

    def _resolve_image_primitive_node(
        self,
        node: ImagePrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """User artifact ref and/or wired image dict → normalized ``DictionaryNodeOutput`` (metadata only)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "image", "type": "dictionary", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(node.id, ["image"], edges, outputs, input_overrides, raw_inputs)
        wired = resolved.get("image")
        aid: Optional[UUID] = None
        if wired is not None and wired != "":
            if not isinstance(wired, dict):
                return _error_with_resolved_inputs(
                    "image primitive: wired `image` must be a dictionary (artifact ref or URL snapshot output).",
                    {"image": wired},
                )
            aid = self._artifact_uuid_from_image_payload(wired)
            if aid is None:
                return _error_with_resolved_inputs(
                    "image primitive: could not read artifact_id from wired image input.",
                    {"image": wired},
                )
        if aid is None:
            raw_aid = (node.data or {}).get("artifact_id")
            if raw_aid:
                try:
                    aid = UUID(str(raw_aid).strip())
                except (ValueError, TypeError):
                    return _error_with_resolved_inputs(
                        f"image primitive: invalid artifact_id in node data {raw_aid!r}",
                        {"artifact_id": raw_aid},
                    )
        if aid is None:
            return _error_with_resolved_inputs(
                "image primitive: no image — wire an upstream image output or select a file (artifact_id on the node).",
                {"artifact_id": None, "image": wired},
            )
        row = self.session.exec(
            select(UrlSnapshotArtifact).where(
                col(UrlSnapshotArtifact.id) == aid,
                col(UrlSnapshotArtifact.user_id) == self.user_id,
            )
        ).first()
        if row is None:
            return _error_with_resolved_inputs(
                f"image primitive: image artifact {aid} not found or not owned by this user.",
                {"artifact_id": str(aid)},
            )
        payload: Dict[str, Any] = {
            "artifact_id": str(row.id),
            "mime_type": (row.mime_type or "image/png").strip() or "image/png",
            "width": int(row.width),
            "height": int(row.height),
        }
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=payload),
            "details": {"resolved_inputs": {"image": payload}},
        }

    def _resolve_gmail_primitive_node(
        self,
        node: GmailPrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Static ``message`` in node data and/or wired ``gmail`` input → ``GmailNodeOutput``."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "gmail", "type": "gmail", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["gmail"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        wired = resolved.get("gmail")
        static_raw = (node.data or {}).get("message")

        def _to_plain(val: Any) -> Optional[Dict[str, Any]]:
            if val is None:
                return None
            if isinstance(val, dict):
                return dict(val)
            if isinstance(val, str) and val.strip():
                try:
                    p = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None
                return p if isinstance(p, dict) else None
            return None

        d: Optional[Dict[str, Any]] = None
        if wired is not None:
            d = _to_plain(wired)
        if d is None and static_raw is not None:
            d = _to_plain(static_raw)

        if not d:
            return _error_with_resolved_inputs(
                "Gmail primitive requires a non-empty message in node data or a wired gmail input.",
                {"gmail": wired, "has_static_message": static_raw is not None},
            )

        out = gmail_dict_to_node_output(node.id, d)
        return {
            "status": "ok",
            "output": out,
            "details": {
                "resolved_inputs": {
                    "gmail_source": "wire" if wired is not None else "data",
                }
            },
        }

    @staticmethod
    def _document_plain_dict(raw_doc: Any) -> Dict[str, Any]:
        if isinstance(raw_doc, dict):
            return raw_doc
        if isinstance(raw_doc, str):
            try:
                parsed = json.loads(raw_doc)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"document input: invalid JSON ({e})") from e
            if not isinstance(parsed, dict):
                raise ValueError("document input must be a dictionary")
            return parsed
        raise ValueError("document input must be a dictionary")

    @staticmethod
    def _document_body_text(d: Dict[str, Any]) -> str:
        if "body" in d:
            return str(d["body"])
        if "markdown" in d:
            return str(d["markdown"])
        raise ValueError("document input has no body or markdown field")

    def _resolve_load_document_node(
        self,
        node: LoadDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document_id", "type": "string", "value": None},
            {"key": "document_name", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document_id", "document_name"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        did_raw = resolved.get("document_id")
        dname_raw = resolved.get("document_name")

        def _nonempty(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, str) and not v.strip():
                return False
            return True

        id_ok = _nonempty(did_raw)
        name_ok = _nonempty(dname_raw)
        if id_ok and name_ok:
            return {
                "status": "error",
                "error": "Load document: provide exactly one of document_id or document_name, not both.",
                "details": {"resolved_inputs": {"lookup_mode": "invalid"}},
            }
        if not id_ok and not name_ok:
            return {
                "status": "error",
                "error": "Load document: document_id or document_name is required.",
                "details": {"resolved_inputs": {"document_id": None, "document_name": None}},
            }

        svc = DocumentService(self.session, self.user_id)
        doc: Optional[Document] = None
        ri: Dict[str, Any] = {"lookup_mode": "id" if id_ok else "name"}
        if id_ok:
            try:
                did = UUID(str(did_raw).strip()) if not isinstance(did_raw, UUID) else did_raw
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Load document: invalid document_id.",
                    "details": {"resolved_inputs": {"document_id": str(did_raw), "lookup_mode": "id"}},
                }
            doc = svc.get_document(did)
            ri["document_id"] = str(did)
        else:
            name = str(dname_raw).strip()
            doc = svc.get_document_by_name(name)
            ri["document_name"] = name

        if not doc:
            return {
                "status": "error",
                "error": "Load document: document not found.",
                "details": {"resolved_inputs": ri},
            }
        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    **ri,
                    "resolved_document_id": str(doc.id),
                    "resolved_document_name": doc.name,
                }
            },
        }

    def _resolve_upsert_document_node(
        self,
        node: UpsertDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "name", "type": "string", "value": ""},
            {"key": "content", "type": "string", "value": ""},
            {"key": "existing_document_id", "type": "string", "value": None},
            {"key": "write_mode", "type": "string", "value": "replace"},
        ]
        upsert_edges = _normalize_edges_for_upsert_document(node.id, edges)
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["name", "content", "existing_document_id", "write_mode"],
            upsert_edges,
            outputs,
            input_overrides,
            raw_inputs,
            implicit_null_target_wire_string_keys=frozenset({"name", "content"}),
        )
        resolved = _recover_upsert_miswired_body_into_content(node.id, upsert_edges, resolved, raw_inputs)
        name = resolved.get("name")
        content = resolved.get("content")
        if name is None or (isinstance(name, str) and not str(name).strip()):
            return {
                "status": "error",
                "error": "Upsert document: name is required.",
                "details": {"resolved_inputs": {"write_mode": resolved.get("write_mode")}},
            }
        if content is None:
            return {
                "status": "error",
                "error": "Upsert document: content is required.",
                "details": {"resolved_inputs": {"document_name": str(name).strip()}},
            }
        content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        wm_raw = resolved.get("write_mode") or "replace"
        wm = str(wm_raw).strip().lower()
        if wm not in ("replace", "append", "merge_json"):
            return {
                "status": "error",
                "error": f"Upsert document: invalid write_mode {wm_raw!r}.",
                "details": {"resolved_inputs": {"document_name": str(name).strip(), "write_mode": wm_raw}},
            }

        ex_raw = resolved.get("existing_document_id")
        ex_id: Optional[UUID] = None
        if ex_raw is not None and str(ex_raw).strip() != "":
            try:
                ex_id = UUID(str(ex_raw).strip()) if not isinstance(ex_raw, UUID) else ex_raw
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Upsert document: invalid existing_document_id.",
                    "details": {"resolved_inputs": {"document_name": str(name).strip()}},
                }

        svc = DocumentService(self.session, self.user_id)
        try:
            doc = svc.upsert_document(
                name=str(name).strip(),
                content=content_str,
                existing_document_id=ex_id,
                write_mode=cast(Literal["replace", "append", "merge_json"], wm),
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {
                    "resolved_inputs": {
                        "document_name": str(name).strip(),
                        "write_mode": wm,
                        "content_chars": len(content_str),
                    }
                },
            }

        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    "document_name": doc.name,
                    "write_mode": wm,
                    "resolved_document_id": str(doc.id),
                    "content_chars": len(content_str),
                }
            },
        }

    def _resolve_parse_document_body_node(
        self,
        node: ParseDocumentBodyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document", "type": "document", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        try:
            d = self._document_plain_dict(resolved.get("document"))
            text = self._document_body_text(d)
        except ValueError as e:
            return _error_with_resolved_inputs(str(e), dict(resolved))
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Parse document body: invalid JSON ({e})",
                "details": {"resolved_inputs": {"text_chars": len(text)}},
            }
        if isinstance(parsed, dict):
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=parsed),
                "details": {"resolved_inputs": {"json_kind": "object"}},
            }
        if isinstance(parsed, list):
            return {
                "status": "ok",
                "output": ListNodeOutput(node_id=node.id, data=parsed),
                "details": {"resolved_inputs": {"json_kind": "array"}},
            }
        return {
            "status": "error",
            "error": "Parse document body: JSON root must be an object or array.",
            "details": {"resolved_inputs": {"json_kind": type(parsed).__name__}},
        }

    def _resolve_html_parse_basic_node(
        self,
        node: HtmlParseBasicUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "html", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["html"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("html")
        if raw is None:
            html_s = ""
        elif isinstance(raw, str):
            html_s = raw
        else:
            html_s = str(raw)

        n = len(html_s)
        nd = node.data or {}
        raw_g = nd.get("granularity")
        raw_cr = nd.get("content_root_css")
        granularity: str | None = raw_g if isinstance(raw_g, str) else (str(raw_g) if raw_g is not None else None)
        content_root_css: str | None
        if isinstance(raw_cr, str):
            content_root_css = raw_cr
        elif raw_cr is None:
            content_root_css = None
        else:
            content_root_css = str(raw_cr)

        if not (html_s or "").strip():
            out_data: Dict[str, Any] = {"title": "", "text_blocks": [], "links": []}
        else:
            try:
                out_data = parse_html_basic(
                    html_s,
                    granularity=granularity,
                    content_root_css=content_root_css,
                )
            except ValueError as exc:
                return {
                    "status": "error",
                    "error": str(exc),
                    "details": {
                        "resolved_inputs": {
                            "input_chars": n,
                            "granularity": granularity,
                            "content_root_css": content_root_css,
                        }
                    },
                }

        if n <= STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
            ri: Dict[str, Any] = {
                "input_chars": n,
                "text_blocks_count": len(out_data.get("text_blocks") or []),
                "links_count": len(out_data.get("links") or []),
                "granularity": granularity,
                "content_root_css": content_root_css,
            }
        else:
            ri = {
                "input_chars": n,
                "input_truncated": True,
                "input_prefix": html_s[:STRING_TRUNC_RESOLVED_PREFIX_LEN],
                "text_blocks_count": len(out_data.get("text_blocks") or []),
                "links_count": len(out_data.get("links") or []),
                "granularity": granularity,
                "content_root_css": content_root_css,
            }
        if "segment_text_blocks" in out_data:
            ri["segment_count"] = len(out_data.get("segment_text_blocks") or [])

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dict(out_data)),
            "details": {"resolved_inputs": ri},
        }

    def _resolve_write_object_to_document_body_node(
        self,
        node: WriteObjectToDocumentBodyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        if val is None:
            return _error_with_resolved_inputs(
                "Write object to document body: value is required.",
                dict(resolved),
            )
        if not isinstance(val, (dict, list)):
            return _error_with_resolved_inputs(
                "Write object to document body: value must be a list or dictionary.",
                {**dict(resolved), "value_type": type(val).__name__},
            )
        text = deterministic_json_dumps(val)
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": {"value_kind": "list" if isinstance(val, list) else "object"}},
        }

    def _resolve_append_value_to_document_node(
        self,
        node: AppendValueToDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document", "type": "document", "value": None},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        try:
            d = self._document_plain_dict(resolved.get("document"))
            old = self._document_body_text(d)
        except ValueError as e:
            return _error_with_resolved_inputs(str(e), dict(resolved))
        val = resolved.get("value")
        if val is None:
            return {
                "status": "error",
                "error": "Append value to document: value is required.",
                "details": {"resolved_inputs": {"text_chars": len(old)}},
            }
        if isinstance(val, (dict, list)):
            chunk = deterministic_json_dumps(val)
        else:
            chunk = str(val)
        sep = "\n\n"
        new_body = chunk if not old else old + sep + chunk
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=new_body),
            "details": {
                "resolved_inputs": {
                    "prior_chars": len(old),
                    "appended_chars": len(chunk),
                }
            },
        }

    def _resolve_validate_against_structure_node(
        self,
        node: ValidateAgainstStructureUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
            {"key": "structure", "type": "structure", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value", "structure"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = (node.data or {}).get("structure_id")
        if structure_id_raw:
            try:
                sid = (
                    UUID(str(structure_id_raw).strip()) if not isinstance(structure_id_raw, UUID) else structure_id_raw
                )
                structure = self.session.exec(
                    select(Structure).where(
                        col(Structure.id) == sid,
                        or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                    )
                ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError as e:
                        return {
                            "status": "error",
                            "error": f"Validate against structure: invalid JSON schema ({e})",
                            "details": {"resolved_inputs": {"structure_id": str(sid)}},
                        }
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Validate against structure: invalid structure_id.",
                    "details": {"resolved_inputs": {"structure_id": structure_id_raw}},
                }

        if schema_dict is None:
            st = resolved.get("structure")
            if isinstance(st, dict):
                schema_dict = st
            elif isinstance(st, StructureNodeOutput):
                schema_dict = dict(st.schema_dict) if st.schema_dict else None

        if not schema_dict:
            return _error_with_resolved_inputs(
                "Validate against structure: provide structure_id on the node or wire a Structure output.",
                dict(resolved),
            )

        instance = val
        if instance is None:
            return _error_with_resolved_inputs(
                "Validate against structure: value is required.",
                dict(resolved),
            )

        try:
            Draft202012Validator(schema_dict).validate(instance)
        except ValidationError as e:
            return {
                "status": "error",
                "error": f"Validate against structure: {e.message}",
                "details": {
                    "resolved_inputs": {
                        "failed_path": list(e.path) if e.path else [],
                    }
                },
            }

        if isinstance(instance, dict):
            out: NodeOutputUnion = DictionaryNodeOutput(node_id=node.id, data=dict(instance))
        elif isinstance(instance, list):
            out = ListNodeOutput(node_id=node.id, data=list(instance))
        elif isinstance(instance, bool):
            out = BooleanNodeOutput(node_id=node.id, value=instance)
        elif isinstance(instance, int) and not isinstance(instance, bool):
            out = IntNodeOutput(node_id=node.id, value=int(instance))
        elif isinstance(instance, str):
            out = StringNodeOutput(node_id=node.id, text=instance)
        else:
            out = StringNodeOutput(node_id=node.id, text=json.dumps(instance, ensure_ascii=False))
        return {
            "status": "ok",
            "output": out,
            "details": {"resolved_inputs": {"validated": True}},
        }

    def _resolve_start_node(self, node: StartGraphNode, input_overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return StartNodeOutput from required_inputs (or legacy data.text).
        Uses input_overrides for null values.

        - raw_inputs is None: legacy path (data.text or input_overrides)
        - raw_inputs == []: no inputs; single output handle "output" with empty string
        - else: process each required input
        """
        raw_inputs = node.data.get("required_inputs")
        if raw_inputs is None:
            # Legacy: data.text as single string input
            text = node.data.get("text", "") or input_overrides.get("text", "") or input_overrides.get("user_input", "")
            legacy_outputs = {"user_input": text}
            return {
                "status": "ok",
                "output": StartNodeOutput(node_id=node.id, outputs=legacy_outputs, text=text),
                "details": {"resolved_inputs": {"user_input": text}},
            }
        if isinstance(raw_inputs, list) and len(raw_inputs) == 0:
            # Explicit no inputs: single output handle for wiring
            return {
                "status": "ok",
                "output": StartNodeOutput(node_id=node.id, outputs={"output": ""}, text=""),
                "details": {"resolved_inputs": {"output": ""}},
            }

        outputs_dict: Dict[str, Any] = {}
        text_parts: List[str] = []

        for item in raw_inputs:
            if isinstance(item, dict):
                key = item.get("key", "")
                inp_type = item.get("type", "string")
                val = item.get("value")
                if (
                    val is None
                    or (inp_type == "string" and val == "")
                    or (inp_type == "datetime" and (val is None or (isinstance(val, str) and not str(val).strip())))
                ):
                    val = input_overrides.get(key)
                if inp_type == "any":
                    if val is None:
                        return _error_with_resolved_inputs(
                            f"Start node required input '{key}' has no value and no override.",
                            {**dict(outputs_dict), "_missing_key": key},
                        )
                elif val is None and inp_type == "string":
                    val = ""
                elif val is None and inp_type == "boolean":
                    val = False
                elif val is None and inp_type == "int":
                    val = 0
                elif inp_type == "datetime" and val is not None:
                    norm = parse_rfc3339_datetime_string(str(val))
                    if norm is None:
                        return _error_with_resolved_inputs(
                            f"Start node required input '{key}' is not a valid RFC3339 datetime.",
                            {**dict(outputs_dict), key: val},
                        )
                    val = norm
                if inp_type == "gmail" and val is not None:
                    if not isinstance(val, dict):
                        return _error_with_resolved_inputs(
                            f"Start node required input '{key}' must be a JSON object for type gmail.",
                            {**dict(outputs_dict), key: val},
                        )
                    val = gmail_dict_to_node_output(node.id, val)
                if val is None:
                    return _error_with_resolved_inputs(
                        f"Start node required input '{key}' has no value and no override.",
                        {**dict(outputs_dict), "_missing_key": key},
                    )
                outputs_dict[key] = val
                if isinstance(val, str):
                    text_parts.append(val)
                elif isinstance(val, (list, dict)):
                    text_parts.append(json.dumps(val, indent=2))
                elif isinstance(val, (bool, int)):
                    text_parts.append(str(val))
                elif isinstance(val, float):
                    text_parts.append(str(val))
                else:
                    text_parts.append(str(val))
            else:
                continue

        text = "\n\n".join(text_parts)
        return {
            "status": "ok",
            "output": StartNodeOutput(node_id=node.id, outputs=outputs_dict, text=text),
            "details": {"resolved_inputs": dict(outputs_dict)},
        }

    async def _resolve_workflow_node(
        self,
        node: WorkflowRefNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        parent_workflow: Optional[WorkflowDefinition],
        execution_stack: frozenset,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the referenced sub-workflow. Build input_overrides from parent edges.
        Reject self-reference and cycles.
        """
        parent_ov = dict(input_overrides or {})
        workflow_id_raw = node.data.get("workflow_id")
        if not workflow_id_raw:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' has no workflow_id.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }
        try:
            sub_wf_id = UUID(workflow_id_raw) if isinstance(workflow_id_raw, str) else workflow_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' has invalid workflow_id.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        if parent_workflow and sub_wf_id == parent_workflow.id:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' references itself (self-reference not allowed).",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }
        if sub_wf_id in execution_stack:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' creates a cycle (workflow {sub_wf_id} already in execution stack).",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        sub_wf = WorkflowDefinitionService(self.session, self.user_id).get_workflow(sub_wf_id)
        if not sub_wf:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' references workflow {sub_wf_id} which was not found.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        overrides: Dict[str, Any] = dict(input_overrides or {})
        for edge in edges:
            if edge.target != node.id:
                continue
            key = edge.target_handle or "user_input"
            src_out = outputs.get(edge.source)
            if src_out is None:
                continue
            slot = _get_slot_value(src_out, edge.source_handle)
            overrides[key] = node_output_to_input_override_value(slot)

        new_stack = execution_stack | (frozenset({parent_workflow.id}) if parent_workflow else frozenset())
        nested_ov = filter_output_overrides_for_graph(sub_wf.graph, output_overrides_map or {})
        executor = WorkflowExecutor(
            self.session,
            self.user_id,
            default_google_workflow_connection_id=self.default_google_workflow_connection_id,
        )
        result = await executor.run(
            sub_wf,
            input_overrides=overrides,
            output_overrides_map=nested_ov,
            execution_stack=new_stack,
            execution_time_zone=execution_time_zone,
        )

        if result.status != "ok":
            failed = next((r for r in result.node_results if r.status == "error"), None)
            err_msg = failed.error if failed else f"Sub-workflow {sub_wf_id} failed with status {result.status}"
            sub_nodes = sub_wf.graph.get("nodes", [])
            node_id_to_label = {
                n["id"]: (n.get("label") or n.get("data", {}).get("label") or n["id"]) for n in sub_nodes
            }
            return {
                "status": "error",
                "error": err_msg,
                "details": {
                    "sub_workflow_id": str(sub_wf_id),
                    "sub_workflow_name": sub_wf.name,
                    "sub_workflow_node_results": [r.model_dump(mode="json") for r in result.node_results],
                    "sub_workflow_node_labels": node_id_to_label,
                    "resolved_inputs": {"input_overrides": dict(overrides)},
                },
            }

        wf_input_details: Dict[str, Any] = {"resolved_inputs": {"input_overrides": dict(overrides)}}

        stop_output_type = "string"
        sub_nodes = sub_wf.graph.get("nodes", [])
        stop_node_ids = [n["id"] for n in sub_nodes if n.get("kind") == "stop"]
        for n in sub_nodes:
            if n.get("kind") == "stop":
                req = (n.get("data") or {}).get("required_outputs") or [{"key": "output", "type": "string"}]
                stop_output_type = (req[0] or {}).get("type", "string") if req else "string"
                break

        stop_raw: NodeOutputUnion = StopNodeOutput(node_id="", text="")
        for nr in result.node_results:
            if nr.node_id in stop_node_ids and nr.output:
                stop_raw = nr.output
                break

        return {
            "status": "ok",
            "output": coerce_stop_output(node.id, stop_output_type, stop_raw),
            "details": wf_input_details,
        }

    def _resolve_stop_node(self, node: StopGraphNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Use a single upstream output as the final Stop output.

        Originally the Stop node returned only the last thing provided. When multiple
        edges connect to Stop (e.g. legacy Start->Stop plus List->Stop), concatenating
        all upstream would prepend stray output. We prefer the last upstream that
        matches the Stop's required_outputs type; otherwise use the last upstream.
        """
        req_outputs = node.data.get("required_outputs") or [{"key": "output", "type": "string"}]
        expected_type = (req_outputs[0] or {}).get("type", "string") if req_outputs else "string"
        if not upstream:
            return {
                "status": "ok",
                "output": coerce_stop_output(node.id, expected_type, StopNodeOutput(node_id=node.id, text="")),
                "details": {
                    "resolved_inputs": {
                        "upstream_output": None,
                        "expected_output_type": expected_type,
                    }
                },
            }

        def _matches_type(o: NodeOutputUnion) -> bool:
            if expected_type == "any":
                return True
            if expected_type == "list":
                if isinstance(o, ListNodeOutput):
                    return True
                if isinstance(o, DictionaryNodeOutput):
                    return isinstance(o.data.get("messages"), list)
                return False
            if expected_type == "dictionary":
                return isinstance(o, DictionaryNodeOutput)
            if expected_type == "boolean":
                return isinstance(o, BooleanNodeOutput)
            if expected_type == "int":
                return isinstance(o, IntNodeOutput)
            if expected_type == "datetime":
                return isinstance(o, DateTimeNodeOutput)
            if expected_type == "structure":
                return isinstance(o, StructureNodeOutput)
            if expected_type == "document":
                return isinstance(o, DocumentNodeOutput)
            if expected_type == "gmail":
                return isinstance(o, GmailNodeOutput)
            return isinstance(o, (StringNodeOutput, ResponseNodeOutput, StartNodeOutput))

        out = upstream[-1]
        for o in reversed(upstream):
            if _matches_type(o):
                out = o
                break

        return {
            "status": "ok",
            "output": coerce_stop_output(node.id, expected_type, out),
            "details": {
                "resolved_inputs": {
                    "upstream_output": _node_output_to_json_dict(out),
                    "expected_output_type": expected_type,
                }
            },
        }

    async def _run_simple_llm_call_node(
        self,
        node: SimpleLLMCallSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve system_prompt and user_prompt from Persona (if persona_id set),
        or from required_inputs, overrides, or upstream.
        Call LMStudioProvider and return ResponseNodeOutput.
        """
        persona_id_raw = node.data.get("persona_id")
        persona: Optional[Persona] = None
        if persona_id_raw:
            try:
                pid = UUID(persona_id_raw) if isinstance(persona_id_raw, str) else persona_id_raw
            except (ValueError, TypeError):
                pid = None
            if pid is not None:
                async with self._async_session_lock:
                    persona = self.session.exec(
                        select(Persona)
                        .where(col(Persona.id) == pid)
                        .where(or_(col(Persona.user_id) == self.user_id, col(Persona.user_id).is_(None)))
                    ).first()

        if not persona:
            return {
                "status": "error",
                "error": (
                    f"Simple LLM Call node '{node.id}' requires a Persona. "
                    "Select a Persona in the Workflow Editor before running."
                ),
            }

        # Persona required: use its system_prompt, default_model, creativity
        # Resolve additional context from node field, upstream (handles additional_context or system_prompt), overrides
        additional_from_node = (node.data.get("additional_system_prompt_context") or "").strip()
        raw_inputs = node.data.get("required_inputs") or []
        resolved_addl = _resolve_inputs_by_target_handle(
            node.id, ["additional_context", "system_prompt"], edges, outputs, {}, raw_inputs
        )
        additional_from_upstream = (
            resolved_addl.get("additional_context") or resolved_addl.get("system_prompt") or ""
        ).strip()
        additional_from_overrides = (input_overrides.get("additional_system_prompt_context") or "").strip()

        if additional_from_overrides:
            additional_context = additional_from_overrides
        elif additional_from_node and additional_from_upstream:
            additional_context = additional_from_node + "\n\n" + additional_from_upstream
        elif additional_from_node:
            additional_context = additional_from_node
        elif additional_from_upstream:
            additional_context = additional_from_upstream
        else:
            additional_context = ""

        base_prompt = (persona.system_prompt or "You are a helpful assistant.").rstrip()
        addl_stripped = (additional_context or "").strip()
        if addl_stripped:
            core_system = f"{base_prompt}\n\n{addl_stripped}"
        else:
            core_system = base_prompt
        system_prompt = core_system
        model = persona.default_model
        creativity = persona.creativity

        # user_prompt resolved from required_inputs/overrides/upstream
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["user_prompt"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        user_prompt = resolved.get("user_prompt") or "Please proceed."
        if isinstance(user_prompt, dict) and is_gmail_like_message_dict(user_prompt):
            user_message_for_model = format_gmail_message_dict_for_llm_prompt(user_prompt)
            user_prompt = user_message_for_model
        else:
            user_message_for_model = str(user_prompt)

        # Resolve structure: structure_id on node OR upstream edge (target_handle="structure")
        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = node.data.get("structure_id")
        if structure_id_raw:
            try:
                sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
            except (ValueError, TypeError):
                sid = None
            else:
                async with self._async_session_lock:
                    structure = self.session.exec(
                        select(Structure).where(
                            col(Structure.id) == sid,
                            or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                        )
                    ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError:
                        pass
        if schema_dict is None:
            resolved_struct = _resolve_inputs_by_target_handle(
                node.id, ["structure"], edges, outputs, input_overrides, raw_inputs
            )
            schema_dict = (
                resolved_struct.get("structure") if isinstance(resolved_struct.get("structure"), dict) else None
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_for_model},
        ]
        options: Dict[str, Any] = {"temperature": creativity}
        if model:
            options["model"] = model
        options.update(persona_lm_chat_options(persona))
        if schema_dict:
            normalized_schema = normalize_schema_for_structured_output(schema_dict)
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": normalized_schema,
                },
            }

        try:
            # Session is not safe for concurrent ORM use across parallel nodes; keep User read + decrypt
            # inside the same lock as other executor DB access. Refresh after run_stream's early commits
            # so api_keys is not a stale/expired in-memory JSON snapshot.
            async with self._async_session_lock:
                user_row = self.session.get(User, self.user_id)
                if user_row is not None:
                    self.session.refresh(user_row)
                decrypted_keys = decrypt_api_keys_store(user_row.api_keys if user_row else None)
                lm_token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted_keys)
            provider = LMStudioProvider(api_key=lm_token)
            response = await provider.chat(messages, options=options)
        except Exception as e:
            return {"status": "error", "error": f"SimpleLLMCall failed: {_format_exception(e)}"}

        ri_llm: Dict[str, Any] = {
            "persona_system_prompt": base_prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "additional_context": additional_context or "",
            "user_role_message": user_message_for_model,
            "model": model,
            "temperature": creativity,
            "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
        }
        if schema_dict:
            ri_llm["structure_schema"] = schema_dict
        detail_common = {"resolved_inputs": ri_llm}

        if schema_dict and response.parsed is not None:
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=response.parsed),
                "details": detail_common,
            }
        return {
            "status": "ok",
            "output": ResponseNodeOutput(
                node_id=node.id,
                text=response.raw_text or "",
            ),
            "details": detail_common,
        }

    async def _run_multimodal_llm_call_node(
        self,
        node: MultimodalLLMCallSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persona + user prompt + image artifacts → LM Studio multimodal chat → ResponseNodeOutput."""
        persona_id_raw = node.data.get("persona_id")
        persona: Optional[Persona] = None
        if persona_id_raw:
            try:
                pid = UUID(persona_id_raw) if isinstance(persona_id_raw, str) else persona_id_raw
            except (ValueError, TypeError):
                pid = None
            if pid is not None:
                async with self._async_session_lock:
                    persona = self.session.exec(
                        select(Persona)
                        .where(col(Persona.id) == pid)
                        .where(or_(col(Persona.user_id) == self.user_id, col(Persona.user_id).is_(None)))
                    ).first()

        if not persona:
            return {
                "status": "error",
                "error": (
                    f"Multimodal LLM node '{node.id}' requires a Persona. "
                    "Select a Persona in the Workflow Editor before running."
                ),
            }

        additional_from_node = (node.data.get("additional_system_prompt_context") or "").strip()
        raw_inputs = node.data.get("required_inputs") or []
        resolved_addl = _resolve_inputs_by_target_handle(
            node.id, ["additional_context", "system_prompt"], edges, outputs, {}, raw_inputs
        )
        additional_from_upstream = (
            resolved_addl.get("additional_context") or resolved_addl.get("system_prompt") or ""
        ).strip()
        additional_from_overrides = (input_overrides.get("additional_system_prompt_context") or "").strip()

        if additional_from_overrides:
            additional_context = additional_from_overrides
        elif additional_from_node and additional_from_upstream:
            additional_context = additional_from_node + "\n\n" + additional_from_upstream
        elif additional_from_node:
            additional_context = additional_from_node
        elif additional_from_upstream:
            additional_context = additional_from_upstream
        else:
            additional_context = ""

        base_prompt = (persona.system_prompt or "You are a helpful assistant.").rstrip()
        addl_stripped = (additional_context or "").strip()
        if addl_stripped:
            core_system = f"{base_prompt}\n\n{addl_stripped}"
        else:
            core_system = base_prompt
        system_prompt = core_system
        model = persona.default_model
        mo = node.data.get("model")
        if isinstance(mo, str) and mo.strip():
            model = mo.strip()
        creativity = persona.creativity

        resolved_in = _resolve_inputs_by_target_handle(
            node.id,
            ["user_prompt", "prompt", "images"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        user_prompt = resolved_in.get("user_prompt") or resolved_in.get("prompt") or "Please proceed."
        if isinstance(user_prompt, dict) and is_gmail_like_message_dict(user_prompt):
            user_message_for_model = format_gmail_message_dict_for_llm_prompt(user_prompt)
            user_prompt = user_message_for_model
        else:
            user_message_for_model = str(user_prompt)

        images_raw = resolved_in.get("images")

        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = node.data.get("structure_id")
        if structure_id_raw:
            try:
                sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
            except (ValueError, TypeError):
                sid = None
            else:
                async with self._async_session_lock:
                    structure = self.session.exec(
                        select(Structure).where(
                            col(Structure.id) == sid,
                            or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                        )
                    ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError:
                        pass
        if schema_dict is None:
            resolved_struct = _resolve_inputs_by_target_handle(
                node.id, ["structure"], edges, outputs, input_overrides, raw_inputs
            )
            schema_dict = (
                resolved_struct.get("structure") if isinstance(resolved_struct.get("structure"), dict) else None
            )

        try:
            artifact_ids = normalize_images_input(images_raw)
        except MultimodalLLMInputError as e:
            return _error_with_structured(
                e.message,
                err_type=e.code,
                retryable=e.retryable,
                resolved={"images": images_raw, "user_prompt": user_prompt},
            )

        try:
            async with self._async_session_lock:
                image_parts = build_openai_image_parts_from_artifacts(self.session, self.user_id, artifact_ids)
        except MultimodalLLMInputError as e:
            return _error_with_structured(
                e.message,
                err_type=e.code,
                retryable=e.retryable,
                resolved={
                    "user_prompt": user_prompt,
                    "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
                },
            )

        user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_message_for_model}]
        user_content.extend(image_parts)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options: Dict[str, Any] = {"temperature": creativity}
        if model:
            options["model"] = model
        options.update(persona_lm_chat_options(persona))
        if schema_dict:
            normalized_schema = normalize_schema_for_structured_output(schema_dict)
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": normalized_schema,
                },
            }

        try:
            async with self._async_session_lock:
                user_row = self.session.get(User, self.user_id)
                if user_row is not None:
                    self.session.refresh(user_row)
                decrypted_keys = decrypt_api_keys_store(user_row.api_keys if user_row else None)
                lm_token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted_keys)
            provider = LMStudioProvider(api_key=lm_token)
            response = await provider.chat(messages, options=options)
        except LMStudioModelNotMultimodalError as e:
            ri_mm: Dict[str, Any] = {
                "persona_system_prompt": base_prompt,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
                "model": model,
                "temperature": creativity,
                "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
            }
            if e.provider_detail:
                ri_mm["provider_detail"] = e.provider_detail
            return _error_with_structured(
                str(e),
                err_type="MODEL_NOT_MULTIMODAL",
                retryable=False,
                resolved=ri_mm,
            )
        except Exception as e:
            return {"status": "error", "error": f"MultimodalLLM failed: {_format_exception(e)}"}

        usage_meta: Dict[str, Any] = dict(response.usage) if isinstance(response.usage, dict) else {}
        md: Dict[str, Any] = {
            "model": model,
            "usage": usage_meta,
            "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
        }
        ri_llm: Dict[str, Any] = {
            "persona_system_prompt": base_prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "additional_context": additional_context or "",
            "user_role_message": user_message_for_model,
            "model": model,
            "temperature": creativity,
            "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
            "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
        }
        if schema_dict:
            ri_llm["structure_schema"] = schema_dict
        detail_common = {"resolved_inputs": ri_llm}

        if schema_dict and response.parsed is not None:
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=response.parsed),
                "details": detail_common,
            }
        return {
            "status": "ok",
            "output": ResponseNodeOutput(
                node_id=node.id,
                text=response.raw_text or "",
                metadata=md,
            ),
            "details": detail_common,
        }

    async def _run_text_to_speech_node(
        self,
        node: TextToSpeechSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_mid = node.data.get("tts_model_id")
        if not raw_mid:
            return _error_with_resolved_inputs(
                "Text-to-Speech requires a TTS model. Select one in the node inspector.",
                {"tts_model_id": None},
            )
        try:
            aid = UUID(str(raw_mid))
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": "Invalid tts_model_id",
                "details": {"resolved_inputs": {"tts_model_id": raw_mid}},
            }

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["text"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        text_raw = resolved.get("text")
        if text_raw is None or str(text_raw).strip() == "":
            return _error_with_resolved_inputs(
                "Text-to-Speech requires non-empty text input.",
                {"text": text_raw},
            )
        text = str(text_raw).strip()

        opt_engine = (node.data.get("engine") or "").strip() or None
        tts_opts = node.data.get("tts_options")
        if tts_opts is None:
            tts_opts = {}
        elif not isinstance(tts_opts, dict):
            return {"status": "error", "error": "tts_options must be a JSON object", "details": {}}
        tts_opts = dict(tts_opts)

        voice_sample_id_resolved: Optional[str] = None
        raw_vsid = node.data.get("voice_sample_id")
        if raw_vsid is not None and str(raw_vsid).strip() != "":
            try:
                vsid = UUID(str(raw_vsid))
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Invalid voice_sample_id",
                    "details": {"resolved_inputs": {"voice_sample_id": raw_vsid}},
                }
            voice_sample_id_resolved = str(vsid)
            async with self._async_session_lock:
                sample = self.session.get(VoiceSample, vsid)
            if sample is None or sample.user_id != self.user_id:
                return _error_with_resolved_inputs(
                    "Unknown or inaccessible voice sample.",
                    {"voice_sample_id": voice_sample_id_resolved},
                )
            tts_opts["ref_audio_base64"] = base64.b64encode(sample.ref_audio).decode("ascii")
            tts_opts["ref_text"] = sample.ref_text
            if not (tts_opts.get("language") or "").strip():
                tts_opts["language"] = sample.language

        async with self._async_session_lock:
            art = self.session.get(TtsModelArtifact, aid)
        if art is None:
            return _error_with_resolved_inputs("Unknown TTS model id.", {"tts_model_id": str(aid)})
        if art.status != "ready" or not (art.local_key or "").strip():
            return _error_with_resolved_inputs(
                f"TTS model '{art.display_name}' is not ready (status={art.status}).",
                {"tts_model_id": str(aid), "status": art.status},
            )
        engine = art.engine
        if opt_engine and opt_engine != engine:
            return {
                "status": "error",
                "error": f"Node engine override {opt_engine!r} does not match registry engine {engine!r}.",
                "details": {"resolved_inputs": {"engine": opt_engine, "registry_engine": engine}},
            }

        try:
            wav = await synthesize_wav(engine, art.local_key, text, tts_opts)
        except TtsBridgeError as e:
            ri: Dict[str, Any] = {
                "user_prompt": text,
                "tts_model_id": str(aid),
                "engine": engine,
            }
            if voice_sample_id_resolved:
                ri["voice_sample_id"] = voice_sample_id_resolved
            return {
                "status": "error",
                "error": f"Text-to-Speech failed: {e}",
                "details": {"resolved_inputs": ri},
            }

        b64 = base64.b64encode(wav).decode("ascii")
        resolved_in: Dict[str, Any] = {
            "user_prompt": text,
            "tts_model_id": str(aid),
            "engine": engine,
            "display_name": art.display_name,
        }
        if voice_sample_id_resolved:
            resolved_in["voice_sample_id"] = voice_sample_id_resolved
        return {
            "status": "ok",
            "output": AudioNodeOutput(node_id=node.id, mime_type="audio/wav", audio_base64=b64),
            "details": {"resolved_inputs": resolved_in},
        }

    async def _run_transcribe_audio_node(
        self,
        node: TranscribeAudioSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        if stream_run_id is None:
            return {
                "status": "error",
                "error": "Voice input (transcribe_audio) must run in streaming mode from the editor.",
            }
        data = node.data or {}
        iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
        key = TranscribeWaitKey(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            iteration=iter_n,
        )
        try:
            fut = register_transcribe_wait(key)
        except RuntimeError as e:
            return {
                "status": "error",
                "error": str(e) or "Duplicate transcribe wait",
            }
        self._track_transcribe_wait(key)
        self._emit_interstitial(
            {
                "event": "input_required",
                "kind": "transcribe_audio",
                "run_id": str(stream_run_id),
                "node_id": node_id,
                "for_loop_id": for_loop_id,
                "for_loop_iteration": for_loop_iteration,
            }
        )
        try:
            audio_bytes = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
        except asyncio.CancelledError:
            cancel_transcribe_wait(key)
            raise
        except asyncio.TimeoutError:
            cancel_transcribe_wait(key)
            return {
                "status": "error",
                "error": "Timed out waiting for a recording. Use Talk, then Stop, to upload audio.",
            }
        finally:
            self._untrack_transcribe_wait(key)
        return await self._transcribe_audio_upload_to_string_output(
            node_id,
            data,
            audio_bytes,
            source_type="microphone",
            empty_error="Transcription was empty. Try a clearer recording.",
        )

    async def _run_audio_file_input_node(
        self,
        node: AudioFileInputSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        data = node.data or {}
        artifact_id_raw = data.get("audio_artifact_id")
        if isinstance(artifact_id_raw, str) and artifact_id_raw.strip():
            try:
                artifact_id = uuid.UUID(artifact_id_raw.strip())
            except ValueError:
                return {
                    "status": "error",
                    "error": "Audio File Input has an invalid saved file reference.",
                    "details": {"resolved_inputs": {"audio_artifact_id": artifact_id_raw}},
                }
            async with self._async_session_lock:
                artifact = self.session.get(AudioFileArtifact, artifact_id)
                if artifact is None or artifact.user_id != self.user_id:
                    artifact = None
                else:
                    artifact = AudioFileArtifact(
                        id=artifact.id,
                        user_id=artifact.user_id,
                        filename=artifact.filename,
                        mime_type=artifact.mime_type,
                        size_bytes=artifact.size_bytes,
                        audio_bytes=bytes(artifact.audio_bytes),
                        created_at=artifact.created_at,
                        updated_at=artifact.updated_at,
                    )
            if artifact is None:
                return {
                    "status": "error",
                    "error": "Audio file not found.",
                    "details": {"resolved_inputs": {"audio_artifact_id": str(artifact_id)}},
                }
            return await self._transcribe_audio_upload_to_string_output(
                node_id,
                data,
                TranscribeUpload(
                    data=artifact.audio_bytes,
                    filename=artifact.filename,
                    content_type=artifact.mime_type,
                ),
                source_type="audio_file",
                audio_artifact_id=str(artifact.id),
                empty_error="Transcript returned empty. Please try another audio file.",
            )

        if stream_run_id is None:
            return {
                "status": "error",
                "error": "Audio File Input needs a saved file or a streaming run-time file upload.",
            }

        iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
        key = TranscribeWaitKey(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            iteration=iter_n,
        )
        try:
            fut = register_transcribe_wait(key)
        except RuntimeError as e:
            return {
                "status": "error",
                "error": str(e) or "Duplicate audio file input wait",
            }
        self._track_transcribe_wait(key)
        self._emit_interstitial(
            {
                "event": "input_required",
                "kind": "audio_file_input",
                "run_id": str(stream_run_id),
                "node_id": node_id,
                "for_loop_id": for_loop_id,
                "for_loop_iteration": for_loop_iteration,
            }
        )
        try:
            audio_upload = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
        except asyncio.CancelledError:
            cancel_transcribe_wait(key)
            raise
        except asyncio.TimeoutError:
            cancel_transcribe_wait(key)
            return {
                "status": "error",
                "error": "Timed out waiting for an audio file upload.",
            }
        finally:
            self._untrack_transcribe_wait(key)
        return await self._transcribe_audio_upload_to_string_output(
            node_id,
            data,
            audio_upload,
            source_type="audio_file",
            empty_error="Transcript returned empty. Please try another audio file.",
        )

    async def _run_transcribe_file_node(
        self,
        node: TranscribeFileSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        """Run the provider-abstracted Transcribe File skill.

        See plan section 3 for the data-shape contract. The branches:

        1. Resolve audio bytes (saved artifact or runtime upload via input_required).
        2. Resolve the speech provider via the registry; resolve the API key from
           User.api_keys then env (mirrors LM Studio's bearer resolution).
        3. Persist a transcription_jobs row, call provider.submit, persist the result.
        4. For sync providers (local_whisper) the transcript is already in hand → emit.
        5. For async providers (assemblyai) poll inline with periodic heartbeats so the
           SSE client stays attached. On client cancel, the persisted row remains in a
           non-terminal state for the lifespan poller to advance.
        """
        # Imports kept inside the method so the executor doesn't pay their cost on every
        # graph evaluation (mirrors how other heavy paths in this module are structured).
        from app.domain.audio_file_validation import ValidatedAudioFile, safe_audio_filename
        from app.domain.services.audio_file_artifact_service import AudioFileArtifactService
        from app.domain.services.transcription_job_service import TranscriptionJobService

        data = node.data or {}
        provider_id_raw = data.get("provider")
        provider_id = (
            provider_id_raw.strip().lower()
            if isinstance(provider_id_raw, str) and provider_id_raw.strip()
            else "local_whisper"
        )

        # Refuse providers the deployment hasn't enabled (e.g. assemblyai with no key plan).
        enabled = enabled_provider_ids() or ["local_whisper"]
        if provider_id not in enabled:
            return _error_with_resolved_inputs(
                f"Transcribe File: provider {provider_id!r} is not enabled in this deployment "
                f"(allowed: {sorted(enabled)}).",
                {"provider": provider_id, "audio_artifact_id": data.get("audio_artifact_id")},
            )

        try:
            provider = get_speech_provider(provider_id)
        except TranscriptionProviderError as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: {exc}",
                {"provider": provider_id, "audio_artifact_id": data.get("audio_artifact_id")},
            )

        # ----- Build TranscriptionOptions from the node data -----
        task_raw = data.get("task")
        task_norm: str = "transcribe"
        if isinstance(task_raw, str) and task_raw.strip().lower() in ("transcribe", "translate"):
            task_norm = task_raw.strip().lower()
        language_raw = data.get("language")
        language = language_raw.strip() if isinstance(language_raw, str) and language_raw.strip() else None
        prompt_raw = data.get("prompt")
        prompt = prompt_raw.strip() if isinstance(prompt_raw, str) and prompt_raw.strip() else None
        diarization_enabled = bool(data.get("diarization_enabled"))
        include_word_timestamps = bool(data.get("include_word_timestamps"))
        pm_raw = data.get("provider_model_id")
        provider_model_id = pm_raw.strip() if isinstance(pm_raw, str) and pm_raw.strip() else None
        model_desc = tuple(type(provider).model_descriptors)
        if provider_model_id and model_desc:
            allowed = {m.id for m in model_desc}
            if provider_model_id not in allowed:
                return _error_with_resolved_inputs(
                    "Transcribe File: unknown speech model "
                    f"{provider_model_id!r} for provider {provider_id!r} "
                    f"(allowed: {sorted(allowed)}).",
                    {"provider": provider_id, "provider_model_id": provider_model_id},
                )
        try:
            options = TranscriptionOptions(
                language=language,
                diarization_enabled=diarization_enabled,
                include_word_timestamps=include_word_timestamps,
                prompt=prompt,
                task=task_norm,  # type: ignore[arg-type]
                provider_model_id=provider_model_id,
            )
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: invalid options — {exc}",
                {"provider": provider_id},
            )

        # ----- Resolve audio bytes -----
        audio_artifact_id_raw = data.get("audio_artifact_id")
        artifact_path_used = isinstance(audio_artifact_id_raw, str) and bool(audio_artifact_id_raw.strip())

        artifact_id: Optional[uuid.UUID] = None
        audio_bytes: Optional[bytes] = None
        validated: Optional[ValidatedAudioFile] = None

        if artifact_path_used:
            raw_aid_local = audio_artifact_id_raw
            assert isinstance(raw_aid_local, str)
            try:
                artifact_id = uuid.UUID(raw_aid_local.strip())
            except ValueError:
                return _error_with_resolved_inputs(
                    "Transcribe File has an invalid saved file reference.",
                    {"provider": provider_id, "audio_artifact_id": audio_artifact_id_raw},
                )
            async with self._async_session_lock:
                row = self.session.get(AudioFileArtifact, artifact_id)
                if row is None or row.user_id != self.user_id:
                    return _error_with_resolved_inputs(
                        "Audio file not found.",
                        {"provider": provider_id, "audio_artifact_id": str(artifact_id)},
                    )
                audio_bytes = bytes(row.audio_bytes)
                validated = ValidatedAudioFile(
                    filename=row.filename,
                    mime_type=row.mime_type,
                    size_bytes=row.size_bytes,
                )
        else:
            if stream_run_id is None:
                return _error_with_resolved_inputs(
                    "Transcribe File needs a saved file or a streaming run-time file upload.",
                    {"provider": provider_id},
                )
            iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
            wait_key = TranscribeWaitKey(
                run_id=stream_run_id,
                node_id=node_id,
                for_loop_id=for_loop_id,
                iteration=iter_n,
            )
            try:
                fut = register_transcribe_wait(wait_key)
            except RuntimeError as exc:
                return _error_with_resolved_inputs(
                    str(exc) or "Duplicate transcribe_file wait",
                    {"provider": provider_id},
                )
            self._track_transcribe_wait(wait_key)
            self._emit_interstitial(
                {
                    "event": "input_required",
                    "kind": "transcribe_file",
                    "run_id": str(stream_run_id),
                    "node_id": node_id,
                    "for_loop_id": for_loop_id,
                    "for_loop_iteration": for_loop_iteration,
                    "provider": provider_id,
                },
            )
            try:
                upload = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
            except asyncio.CancelledError:
                cancel_transcribe_wait(wait_key)
                raise
            except asyncio.TimeoutError:
                cancel_transcribe_wait(wait_key)
                return _error_with_resolved_inputs(
                    "Timed out waiting for an audio file upload.",
                    {"provider": provider_id},
                )
            finally:
                self._untrack_transcribe_wait(wait_key)

            audio_bytes = bytes(upload.data)
            validated = ValidatedAudioFile(
                filename=safe_audio_filename(upload.filename),
                mime_type=(upload.content_type or "application/octet-stream"),
                size_bytes=len(audio_bytes),
            )

            # Spill runtime upload to a transient AudioFileArtifact so the lifespan poller
            # (and any future restart) can re-read the bytes if the cloud job needs to be
            # resubmitted. Local Whisper is sync so we skip this spill there to avoid
            # paying the storage cost for a 100% successful inline call.
            if not provider.is_synchronous:
                artifact_service = AudioFileArtifactService(self.session, self.user_id)
                async with self._async_session_lock:
                    transient = artifact_service.create_transient(audio_bytes, validated)
                artifact_id = transient.id

        if not audio_bytes or len(audio_bytes) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
            return _error_with_resolved_inputs(
                "Invalid or too large audio payload",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "size_bytes": len(audio_bytes) if audio_bytes else 0,
                },
            )

        assert validated is not None  # for mypy / readers — set by both branches above

        # ----- Resolve API key (only meaningful for non-local providers) -----
        api_key: Optional[str] = None
        if provider_id == "assemblyai":
            decrypted_keys = self._decrypted_user_api_keys()
            api_key = resolve_assemblyai_api_key(decrypted_keys)
            if not api_key:
                return _error_with_resolved_inputs(
                    "AssemblyAI provider selected but no API key found. "
                    "Add one in My Settings → API Settings, or set ASSEMBLYAI_API_KEY on the server.",
                    {"provider": provider_id},
                )

        # ----- Persist the row before the network call so a crash leaves a breadcrumb -----
        job_service = TranscriptionJobService(self.session, self.user_id)
        existing = job_service.find_existing_for_node(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            for_loop_iteration=for_loop_iteration,
        )
        if existing is not None and existing.status == "completed" and existing.transcript_json:
            # Reattach idempotency: the previous executor already submitted+completed this
            # node (e.g., a poller advanced the row, the user re-ran the workflow with the
            # same artifact). Reuse the persisted transcript instead of re-uploading.
            primitive_dict = dict(existing.transcript_json)
            return self._build_transcribe_file_success(
                node_id=node_id,
                primitive_dict=primitive_dict,
                provider_id=provider_id,
                options=options,
                validated=validated,
                artifact_id=artifact_id,
            )

        if existing is not None:
            job_row = existing
        else:
            job_row = job_service.create_pending(
                run_id=stream_run_id,
                node_id=node_id,
                for_loop_id=for_loop_id,
                for_loop_iteration=for_loop_iteration,
                provider=provider_id,
                options=options,
                audio_artifact_id=artifact_id,
                validated_audio=validated,
            )

        # ----- Submit (idempotent if we already have a provider_job_id) -----
        try:
            if not job_row.provider_job_id:
                submission = await provider.submit(
                    audio=audio_bytes,
                    filename=validated.filename,
                    content_type=validated.mime_type,
                    options=options,
                    api_key=api_key,
                )
                job_row = job_service.apply_submission(job_row, submission)
        except TranscriptionProviderError as exc:
            job_service.mark_error(job_row, str(exc))
            job_service.cleanup_transient_audio(job_row)
            return _error_with_resolved_inputs(
                f"Transcription submit failed: {exc}",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "transcribe_error": str(exc),
                },
            )
        except asyncio.CancelledError:
            # Submit was interrupted mid-flight; the row stays in 'submitting'. The poller
            # will advance it on the next pass (e.g. by retrying via the persisted bytes).
            raise

        # ----- Inline poll loop (sync providers short-circuit) -----
        if job_row.status == "completed" and job_row.transcript_json:
            primitive_dict = dict(job_row.transcript_json)
            job_service.cleanup_transient_audio(job_row)
            return self._build_transcribe_file_success(
                node_id=node_id,
                primitive_dict=primitive_dict,
                provider_id=provider_id,
                options=options,
                validated=validated,
                artifact_id=artifact_id,
            )

        if job_row.status == "error":
            err = job_row.provider_error or "Provider returned an error after submit."
            job_service.cleanup_transient_audio(job_row)
            return _error_with_resolved_inputs(
                f"Transcription failed: {err}",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "transcribe_error": err,
                },
            )

        # Async path: poll until terminal or timeout.
        poll_interval = max(0.5, float(settings.ASSEMBLYAI_POLL_INTERVAL))
        job_timeout = max(poll_interval * 2, float(settings.ASSEMBLYAI_JOB_TIMEOUT))
        deadline = time.monotonic() + job_timeout
        provider_job_id = job_row.provider_job_id
        try:
            while True:
                if not provider_job_id:
                    job_service.mark_error(job_row, "Provider returned no job id.")
                    job_service.cleanup_transient_audio(job_row)
                    return _error_with_resolved_inputs(
                        "Transcription failed: provider returned no job id.",
                        {"provider": provider_id, "transcribe_error": "missing provider_job_id"},
                    )
                if time.monotonic() > deadline:
                    job_service.mark_error(
                        job_row,
                        f"Inline poll timed out after {int(job_timeout)}s; lifespan poller will continue.",
                    )
                    return _error_with_resolved_inputs(
                        "Transcription is still in progress; reattach to the run later to view the result.",
                        {
                            "provider": provider_id,
                            "transcription_job_id": str(job_row.id),
                            "provider_job_id": provider_job_id,
                            "audio_artifact_id": str(artifact_id) if artifact_id else None,
                        },
                    )
                await asyncio.sleep(poll_interval)
                if stream_run_id is not None:
                    self._emit_interstitial(
                        {
                            "event": "transcription_job_status",
                            "node_id": node_id,
                            "run_id": str(stream_run_id),
                            "provider": provider_id,
                            "status": job_row.status,
                            "provider_job_id": provider_job_id,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
                try:
                    poll_result = await provider.poll(
                        provider_job_id=provider_job_id,
                        options=options,
                        api_key=api_key,
                    )
                except TranscriptionProviderError as exc:
                    if not exc.retryable:
                        job_service.mark_error(job_row, str(exc))
                        job_service.cleanup_transient_audio(job_row)
                        return _error_with_resolved_inputs(
                            f"Transcription poll failed: {exc}",
                            {
                                "provider": provider_id,
                                "transcribe_error": str(exc),
                                "transcription_job_id": str(job_row.id),
                            },
                        )
                    # Retryable provider error — keep looping; logger picks it up below.
                    logger.warning(
                        "transcribe_file retryable poll error provider=%s job=%s: %s",
                        provider_id,
                        provider_job_id,
                        exc,
                    )
                    continue
                job_row = job_service.apply_poll(job_row, poll_result)
                if job_row.status == "completed" and job_row.transcript_json:
                    primitive_dict = dict(job_row.transcript_json)
                    job_service.cleanup_transient_audio(job_row)
                    return self._build_transcribe_file_success(
                        node_id=node_id,
                        primitive_dict=primitive_dict,
                        provider_id=provider_id,
                        options=options,
                        validated=validated,
                        artifact_id=artifact_id,
                    )
                if job_row.status == "error":
                    err = job_row.provider_error or "Provider returned an error."
                    job_service.cleanup_transient_audio(job_row)
                    return _error_with_resolved_inputs(
                        f"Transcription failed: {err}",
                        {
                            "provider": provider_id,
                            "transcribe_error": err,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
                if job_row.status == "cancelled":
                    return _error_with_resolved_inputs(
                        "Transcription was cancelled.",
                        {
                            "provider": provider_id,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
        except asyncio.CancelledError:
            # Client disconnected. The row stays non-terminal so the lifespan poller takes over.
            raise

    def _decrypted_user_api_keys(self) -> Optional[Dict[str, Any]]:
        """Decrypt the running user's stored api_keys for provider key resolution."""
        from app.core.user_api_keys_crypto import decrypt_api_keys_store

        user = self.session.get(User, self.user_id)
        if user is None:
            return None
        try:
            return decrypt_api_keys_store(user.api_keys or {})
        except Exception:
            logger.exception("transcribe_file: failed to decrypt user api_keys")
            return None

    def _build_transcribe_file_success(
        self,
        *,
        node_id: str,
        primitive_dict: Dict[str, Any],
        provider_id: str,
        options: TranscriptionOptions,
        validated: ValidatedAudioFile,
        artifact_id: Optional[uuid.UUID],
    ) -> Dict[str, Any]:
        # Re-validate the dict so a stale/corrupt persisted blob can't poison the graph.
        from app.domain.schemas.transcript import TranscriptPrimitive

        try:
            primitive = TranscriptPrimitive.model_validate(primitive_dict)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: persisted transcript failed validation — {exc}",
                {"provider": provider_id, "audio_artifact_id": str(artifact_id) if artifact_id else None},
            )
        primitive_data = primitive.model_dump(mode="json")
        resolved: Dict[str, Any] = {
            "provider": provider_id,
            "language": options.language,
            "task": options.task,
            "diarization_enabled": options.diarization_enabled,
            "include_word_timestamps": options.include_word_timestamps,
            "prompt": options.prompt,
            "filename": validated.filename,
            "mime_type": validated.mime_type,
            "size_bytes": validated.size_bytes,
            "audio_artifact_id": str(artifact_id) if artifact_id else None,
            "transcript_chars": len(primitive.full_text),
            "duration_seconds": primitive.duration_seconds,
        }
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=primitive_data),
            "details": {
                "resolved_inputs": resolved,
                "transcript_segments_count": len(primitive.segments),
                "transcript_words_count": len(primitive.words),
            },
        }

    async def _transcribe_audio_upload_to_string_output(
        self,
        node_id: str,
        node_data: Dict[str, Any],
        audio_upload: TranscribeUpload,
        *,
        source_type: str,
        audio_artifact_id: Optional[str] = None,
        empty_error: str,
    ) -> Dict[str, Any]:
        task = (node_data.get("task") or "transcribe").strip().lower()
        if task not in ("transcribe", "translate"):
            task = "transcribe"
        lang = node_data.get("language")
        if isinstance(lang, str) and not lang.strip():
            lang = None
        elif isinstance(lang, str):
            lang = lang.strip() or None

        audio_bytes = audio_upload.data
        resolved_base: Dict[str, Any] = {
            "source_type": source_type,
            "filename": audio_upload.filename,
            "mime_type": audio_upload.content_type,
            "size_bytes": len(audio_bytes) if audio_bytes else 0,
            "task": task,
            "language": lang,
        }
        if audio_artifact_id:
            resolved_base["audio_artifact_id"] = audio_artifact_id

        if not audio_bytes or len(audio_bytes) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
            return {
                "status": "error",
                "error": "Invalid or too large audio payload",
                "details": {"resolved_inputs": resolved_base},
            }
        try:
            logger.info(
                "stt transcription starting node_id=%s source_type=%s bytes=%s filename=%s",
                node_id,
                source_type,
                len(audio_bytes),
                audio_upload.filename,
            )
            payload = await transcribe_audio_bytes(
                bytes(audio_bytes),
                task=task,
                language=lang,
                filename=audio_upload.filename,
                content_type=audio_upload.content_type,
            )
            logger.info("stt transcription completed node_id=%s source_type=%s", node_id, source_type)
        except SttBridgeHttpError as e:
            resolved = dict(resolved_base)
            resolved["transcribe_error"] = str(e)
            return {
                "status": "error",
                "error": f"Transcription failed: {e}",
                "details": {"resolved_inputs": resolved},
            }
        text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        if not text:
            return {
                "status": "error",
                "error": empty_error,
                "details": {"resolved_inputs": resolved_base},
            }
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list):
            segments = []
        tlang = payload.get("language") if isinstance(payload, dict) else None
        duration_seconds = None
        if isinstance(payload, dict) and payload.get("duration_seconds") is not None:
            try:
                duration_seconds = float(payload["duration_seconds"])
            except (TypeError, ValueError):
                duration_seconds = None
        resolved = dict(resolved_base)
        resolved.update(
            {
                "transcribe_language": tlang,
                "transcript_chars": len(text),
            }
        )
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node_id, text=text),
            "details": {
                "resolved_inputs": resolved,
                "transcribe_segments": segments,
                "duration_seconds": duration_seconds,
            },
        }

    @staticmethod
    def _coerce_int_cap(val: Any, default: int, cap: int) -> int:
        try:
            if val is None:
                return default
            n = int(val)
            if n < 1:
                return default
            return min(n, cap)
        except (TypeError, ValueError):
            return default

    async def _run_gmail_list_messages_node(
        self,
        node: GmailListMessagesSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        execution_time_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        cid_raw = node.data.get("google_connection_id")
        if not cid_raw:
            return _error_with_resolved_inputs(
                "Gmail List Messages requires a Google connection. Select one in the node inspector.",
                {"google_connection_id": None},
            )
        try:
            conn_uuid = UUID(str(cid_raw))
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": "Invalid google_connection_id",
                "details": {"resolved_inputs": {"google_connection_id": cid_raw}},
            }

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["after", "before", "unread_only", "query", "max_results"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        query_val = resolved.get("query")
        if query_val is None or str(query_val).strip() == "":
            q_inline = node.data.get("query")
            query_val = q_inline
        raw_q: Optional[str]
        if query_val is None or str(query_val).strip() == "":
            raw_q = None
        else:
            raw_q = str(query_val).strip()

        after_val = resolved.get("after")
        if after_val is None or str(after_val).strip() == "":
            after_s = node.data.get("after")
            after_rfc3339 = str(after_s).strip() if after_s else None
        else:
            after_rfc3339 = str(after_val).strip()

        before_val = resolved.get("before")
        if before_val is None or str(before_val).strip() == "":
            before_s = node.data.get("before")
            before_rfc3339 = str(before_s).strip() if before_s else None
        else:
            before_rfc3339 = str(before_val).strip()

        unread_resolved = resolved.get("unread_only")
        if unread_resolved is None:
            unread_only = coerce_bool_unread(node.data.get("unread_only"))
        else:
            unread_only = coerce_bool_unread(unread_resolved)

        if not after_rfc3339:
            after_rfc3339 = None
        if not before_rfc3339:
            before_rfc3339 = None

        user_row = self.session.get(User, self.user_id)
        acct: Dict[str, Any] = dict(user_row.settings or {}) if user_row else {}
        gmail_list_calendar_zone = _effective_gmail_calendar_zone(acct, execution_time_zone)

        try:
            base_q = build_messages_list_q(
                raw_query=raw_q,
                after_rfc3339=after_rfc3339,
                before_rfc3339=before_rfc3339,
                unread_only=unread_only,
                gmail_list_calendar_zone=gmail_list_calendar_zone,
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": f"Invalid Gmail time filter: {e}",
                "details": {
                    "resolved_inputs": {
                        "google_connection_id": str(conn_uuid),
                        "after": after_rfc3339,
                        "before": before_rfc3339,
                        "unread_only": unread_only,
                        "query": raw_q,
                        "gmail_list_calendar_zone": gmail_list_calendar_zone,
                    }
                },
            }
        skip_acct = coerce_bool_unread(node.data.get("gmail_skip_account_category_filters"))

        if "gmail_inbox_focus" in node.data:
            eff_focus = normalize_gmail_inbox_focus(node.data.get("gmail_inbox_focus"))
        elif not skip_acct:
            eff_focus = normalize_gmail_inbox_focus(acct.get("gmail_workflow_inbox_focus"))
        else:
            eff_focus = "off"

        if "gmail_exclude_categories" in node.data:
            eff_exclude = normalize_gmail_exclude_categories(node.data.get("gmail_exclude_categories"))
        elif not skip_acct:
            eff_exclude = normalize_gmail_exclude_categories(acct.get("gmail_workflow_exclude_categories"))
        else:
            eff_exclude = []

        final_q = append_category_q_clauses(
            base_q,
            inbox_focus=eff_focus,
            exclude_categories=eff_exclude,
        )

        mr_default = self._coerce_int_cap(node.data.get("max_results"), 10, 100)
        max_results = self._coerce_int_cap(resolved.get("max_results"), mr_default, 100)

        gmail_ri: Dict[str, Any] = {
            "google_connection_id": str(conn_uuid),
            "after": after_rfc3339,
            "before": before_rfc3339,
            "unread_only": unread_only,
            "query": raw_q,
            "max_results": max_results,
            "gmail_inbox_focus": eff_focus,
            "gmail_exclude_categories": eff_exclude,
            "gmail_skip_account_category_filters": skip_acct,
            "q": final_q,
            "gmail_list_calendar_zone": gmail_list_calendar_zone,
        }

        try:
            access = await ensure_workflow_google_access_token(self.session, conn_uuid, self.user_id)
            raw = await gmail_list_messages(
                access,
                max_results=max_results,
                query=final_q,
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {"resolved_inputs": gmail_ri},
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"GmailListMessages failed: {_format_exception(e)}",
                "details": {"resolved_inputs": gmail_ri},
            }

        messages = raw.get("messages") or []
        safe_list: List[Dict[str, Any]] = []
        list_refs = [m for m in messages if isinstance(m, dict)]
        attempted = sum(1 for m in list_refs if isinstance(m.get("id"), str) and str(m.get("id")).strip() != "")
        if list_refs:
            sem = asyncio.Semaphore(6)

            async def _fetch_one(ref: dict[str, Any]) -> Dict[str, Any]:
                mid = ref.get("id")
                tid = ref.get("threadId")
                if not isinstance(mid, str) or not mid.strip():
                    return {}
                mid_s = mid.strip()
                async with sem:
                    try:
                        full = await gmail_get_message_full(access, mid_s)
                        return curated_gmail_message_from_full_api(
                            full,
                            max_body_chars=GMAIL_MESSAGE_BODY_MAX_CHARS,
                        )
                    except Exception as e:
                        err = _format_exception(e)[:500]
                        err_item: Dict[str, Any] = {"id": mid_s, "fetch_error": err}
                        if isinstance(tid, str) and tid.strip():
                            err_item["threadId"] = tid.strip()
                        return err_item

            parts = await asyncio.gather(*[_fetch_one(m) for m in list_refs])
            safe_list = [p for p in parts if p]

        ok_count = sum(1 for x in safe_list if "fetch_error" not in x)
        failed_count = sum(1 for x in safe_list if "fetch_error" in x)

        diag_response, diag_truncated, diag_omitted = truncate_gmail_messages_list_response(raw)
        diag_payload: Dict[str, Any] = {
            "operation": "users.messages.list",
            "q": final_q,
            "gmail_category_filters": {
                "effective_inbox_focus": eff_focus,
                "effective_exclude_categories": eff_exclude,
                "skip_account_category_filters": skip_acct,
            },
            "response": diag_response,
            "truncated": diag_truncated,
            "omitted_message_count": diag_omitted,
            "message_gets": {
                "attempted": attempted,
                "ok": ok_count,
                "failed": failed_count,
            },
        }
        details = merge_skill_diagnostics(
            {
                "message_count": len(safe_list),
                "resolved_inputs": gmail_ri,
                "gmail_result_size_estimate": raw.get("resultSizeEstimate"),
            },
            vendor_key="gmail_v1",
            payload=diag_payload,
        )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=safe_list),
            "details": details,
        }

    async def _run_calendar_list_events_node(
        self,
        node: CalendarListEventsSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        cid_raw = node.data.get("google_connection_id")
        if not cid_raw:
            return _error_with_resolved_inputs(
                "Calendar List Events requires a Google connection. Select one in the node inspector.",
                {"google_connection_id": None},
            )
        try:
            conn_uuid = UUID(str(cid_raw))
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": "Invalid google_connection_id",
                "details": {"resolved_inputs": {"google_connection_id": cid_raw}},
            }

        cal_raw = node.data.get("calendar_id")
        calendar_id = (str(cal_raw).strip() if cal_raw else "") or "primary"

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["time_min", "time_max"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        time_min = resolved.get("time_min") or node.data.get("time_min")
        time_max = resolved.get("time_max") or node.data.get("time_max")
        if not time_min or not time_max:
            return {
                "status": "error",
                "error": "Calendar List Events requires time_min and time_max (RFC3339, e.g. 2026-03-01T00:00:00Z).",
                "details": {
                    "resolved_inputs": {
                        "google_connection_id": str(conn_uuid),
                        "calendar_id": calendar_id,
                        "time_min": time_min,
                        "time_max": time_max,
                    }
                },
            }
        t_min = str(time_min).strip()
        t_max = str(time_max).strip()

        calendar_ri: Dict[str, Any] = {
            "google_connection_id": str(conn_uuid),
            "calendar_id": calendar_id,
            "time_min": t_min,
            "time_max": t_max,
        }

        try:
            access = await ensure_workflow_google_access_token(self.session, conn_uuid, self.user_id)
            raw = await calendar_list_events(access, calendar_id, time_min=t_min, time_max=t_max)
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {"resolved_inputs": calendar_ri},
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"CalendarListEvents failed: {_format_exception(e)}",
                "details": {"resolved_inputs": calendar_ri},
            }

        events = raw.get("items") or []
        curated: List[Dict[str, Any]] = []
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                curated.append(curated_google_calendar_event(ev))

        diag_response, diag_truncated, diag_omitted = truncate_google_calendar_events_list_response(raw)
        diag_payload: Dict[str, Any] = {
            "operation": "events.list",
            "response": diag_response,
            "truncated": diag_truncated,
            "omitted_event_count": diag_omitted,
        }
        details = merge_skill_diagnostics(
            {"event_count": len(curated), "resolved_inputs": calendar_ri},
            vendor_key="google_calendar_v3",
            payload=diag_payload,
        )

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data={"events": curated}),
            "details": details,
        }

    async def _run_fetch_url_node(
        self,
        node: FetchUrlSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["url"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        url_val = resolved.get("url")
        if url_val is None or (isinstance(url_val, str) and str(url_val).strip() == ""):
            u_inline = node.data.get("url")
            url_val = u_inline
        url_s = str(url_val).strip() if url_val is not None else ""

        method_raw = node.data.get("method") or "GET"
        method_s = str(method_raw).upper().strip()

        h_raw = node.data.get("headers")
        hdrs = normalize_headers(h_raw)

        timeout_ms = node.data.get("timeout_ms")
        to_ms: Optional[int] = None
        if timeout_ms is not None:
            try:
                to_ms = int(timeout_ms)
            except (TypeError, ValueError):
                to_ms = None

        policy_raw = node.data.get("cache_policy") or "default"
        policy = str(policy_raw).lower().strip()
        if policy not in ("default", "refresh", "bypass"):
            policy = "default"

        ri: Dict[str, Any] = {
            "url": url_s,
            "method": method_s,
            "header_keys": sorted(hdrs.keys()),
            "timeout_ms": to_ms,
            "cache_policy": policy,
        }

        cache_key = compute_cache_key(url_s, method_s, hdrs)

        if policy == "default" and url_s:
            hit = get_cached_payload(self.session, self.user_id, cache_key)
            if hit is not None:
                return {
                    "status": "ok",
                    "output": DictionaryNodeOutput(node_id=node.id, data=hit),
                    "details": {"resolved_inputs": ri},
                }

        out = await perform_http_fetch(
            url=url_s,
            method=method_s,
            headers=hdrs,
            timeout_ms=to_ms,
            max_body_bytes=settings.FETCH_URL_MAX_BODY_BYTES,
        )

        cacheable = "error" not in out and "status_code" in out
        if cacheable and policy in ("default", "refresh"):
            upsert_success_cache(self.session, self.user_id, cache_key, out)

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=out),
            "details": {"resolved_inputs": ri},
        }

    async def _run_capture_url_snapshot_node(
        self,
        node: CaptureUrlSnapshotSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["url"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        url_val = resolved.get("url")
        if url_val is None or (isinstance(url_val, str) and str(url_val).strip() == ""):
            u_inline = node.data.get("url")
            url_val = u_inline
        url_s = str(url_val).strip() if url_val is not None else ""

        fp_raw = node.data.get("full_page")
        if fp_raw is None:
            full_page = True
        else:
            full_page = (
                bool(fp_raw)
                if not isinstance(fp_raw, str)
                else str(fp_raw).strip().lower()
                in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
            )

        vw = node.data.get("viewport_width")
        vh = node.data.get("viewport_height")
        try:
            viewport_w = int(vw) if vw is not None else settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH
        except (TypeError, ValueError):
            viewport_w = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH
        try:
            viewport_h = int(vh) if vh is not None else settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT
        except (TypeError, ValueError):
            viewport_h = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT

        wu = str(node.data.get("wait_until") or "load").lower().strip()
        if wu not in ("load", "domcontentloaded", "networkidle"):
            wu = "load"

        timeout_ms = node.data.get("timeout_ms")
        to_ms: Optional[int] = None
        if timeout_ms is not None:
            try:
                to_ms = int(timeout_ms)
            except (TypeError, ValueError):
                to_ms = None
        if to_ms is None or to_ms < 1:
            to_ms = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_TIMEOUT_MS

        policy_raw = node.data.get("cache_policy") or "default"
        policy = str(policy_raw).lower().strip()
        if policy not in ("default", "refresh", "bypass"):
            policy = "default"

        ri: Dict[str, Any] = {
            "url": url_s,
            "full_page": full_page,
            "viewport_width": viewport_w,
            "viewport_height": viewport_h,
            "wait_until": wu,
            "timeout_ms": to_ms,
            "cache_policy": policy,
        }

        ckey = compute_snapshot_cache_key(
            url_s,
            full_page=full_page,
            viewport_w=viewport_w,
            viewport_h=viewport_h,
            wait_until=wu,
        )

        if policy == "default" and url_s:
            hit = get_cache_artifact(self.session, self.user_id, ckey)
            if hit is not None:
                cap = hit.updated_at
                if cap is not None and cap.tzinfo is None:
                    cap = cap.replace(tzinfo=timezone.utc)
                captured_s = cap.isoformat().replace("+00:00", "Z") if cap is not None else ""
                fu = (getattr(hit, "final_url", None) or "").strip() or url_s
                return {
                    "status": "ok",
                    "output": DictionaryNodeOutput(
                        node_id=node.id,
                        data=build_success_output_from_artifact(
                            artifact_id=str(hit.id),
                            width=hit.width,
                            height=hit.height,
                            final_url=fu,
                            captured_at=captured_s,
                            duration_ms=0,
                            cached=True,
                        ),
                    ),
                    "details": {"resolved_inputs": ri},
                }

        # refresh / bypass / miss: capture (bypass and refresh skip cache read — handled above for default)
        raw = await perform_url_snapshot_capture(
            url=url_s,
            full_page=full_page,
            viewport_width=viewport_w,
            viewport_height=viewport_h,
            wait_until=wu,
            timeout_ms=to_ms,
            max_png_bytes=settings.CAPTURE_URL_SNAPSHOT_MAX_PNG_BYTES,
        )
        if "error" in raw:
            out = strip_internal_keys_for_output(raw)
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=out),
                "details": {"resolved_inputs": ri},
            }

        b = raw.get("_png_bytes")
        if not isinstance(b, (bytes, bytearray)):
            out = {
                "error": {
                    "type": "SCREENSHOT",
                    "message": "Internal capture result missing image bytes",
                    "retryable": True,
                },
                "captured_at": raw.get("captured_at", ""),
                "duration_ms": int(raw.get("duration_ms", 0)),
                "cached": False,
            }
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=out),
                "details": {"resolved_inputs": ri},
            }

        resolved_final_url = str(raw.get("final_url", url_s))
        art = create_artifact(
            self.session,
            self.user_id,
            bytes(b),
            int(raw["_width"]),
            int(raw["_height"]),
            final_url=resolved_final_url,
        )
        if policy in ("default", "refresh"):
            upsert_cache(self.session, self.user_id, ckey, art)

        data_out = build_success_output_from_artifact(
            artifact_id=str(art.id),
            width=art.width,
            height=art.height,
            final_url=resolved_final_url,
            captured_at=str(raw.get("captured_at", "")),
            duration_ms=int(raw.get("duration_ms", 0)),
            cached=False,
        )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data_out),
            "details": {"resolved_inputs": ri},
        }
